"""Contract tests that run against a *running* Mergit, not an in-process app.

    MERGIT_BASE_URL=https://mergit.onrender.com pytest test_live_deployment.py -v

Skipped entirely when `MERGIT_BASE_URL` is unset, so the normal suite is unaffected.

Two opt-in levels:

  MERGIT_BASE_URL      read-only contract checks. Safe against production: nothing here
                       writes config, and no goal is submitted.
  MERGIT_LIVE_GOAL=1   additionally submits one real goal and drives it to completion.
                       This spends provider quota and adds a permanent row to the target
                       instance's ledger, so it is off by default.

`MERGIT_ACCESS_PASSWORD` is sent as HTTP Basic when the deployment has `ACCESS_PASSWORD`
set (see access_gate.py).

Nothing in this file issues a PUT. On a deployment without an access gate, writing to
`/api/config/keys` or `/api/config/models` would overwrite live provider configuration,
and a test suite must not be the thing that does that.
"""
import json
import os
import re
import time

import httpx
import pytest

BASE_URL = os.environ.get("MERGIT_BASE_URL", "").rstrip("/")
RUN_GOAL = os.environ.get("MERGIT_LIVE_GOAL", "") not in ("", "0", "false")
PASSWORD = os.environ.get("MERGIT_ACCESS_PASSWORD", "")

pytestmark = pytest.mark.skipif(not BASE_URL, reason="set MERGIT_BASE_URL to run")

UNKNOWN = "does-not-exist-00000000"
GOAL_TIMEOUT = 480


@pytest.fixture(scope="module")
def api():
    auth = ("mergit", PASSWORD) if PASSWORD else None
    # Generous timeout: a sleeping free-tier instance takes ~70s to cold start, because
    # the chain redeploys during boot.
    with httpx.Client(base_url=BASE_URL, timeout=120, auth=auth, follow_redirects=False) as c:
        yield c


# ── the instance is actually up ─────────────────────────────────────────────────

def test_health_is_ok(api):
    r = api.get("/api/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok", "the database is not reachable from the app"
    assert body["worker"] == "running", (
        "the worker loops are not running — goals will be accepted and never planned"
    )


def test_the_chain_is_deployed_and_reports_itself(api):
    body = api.get("/api/economy/chain").json()
    assert body["status"] == "ready", f"chain not ready: {body}"
    assert body["chainId"], body
    assert set(body["contracts"]) == {
        "AgentPassport", "AuditTrail", "ProofOfWork", "ReputationRegistry",
    }, body["contracts"]


def test_the_reported_chain_matches_the_health_endpoint(api):
    """These read different objects; disagreement means one of them is guessing."""
    assert api.get("/api/health").json()["chain_id"] == api.get("/api/economy/chain").json()["chainId"]


def test_every_agent_role_has_a_passport(api):
    passports = api.get("/api/economy/passports").json()
    roles = {p["role"] for p in passports}
    assert {"orchestrator", "researcher", "writer", "coder", "integrator"} <= roles, roles
    assert all(p["soulbound"] for p in passports), "a passport is transferable"
    assert len({p["token_id"] for p in passports}) == len(passports), "duplicate token ids"


def test_the_leaderboard_is_ranked_and_consistent(api):
    rows = api.get("/api/economy/leaderboard").json()
    assert rows
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    assert [r["composite"] for r in rows] == sorted((r["composite"] for r in rows), reverse=True)
    for row in rows:
        assert 0 <= row["composite"] <= 1000, row
        assert row["badge"] in ("Gold", "Silver", "Bronze"), row


# ── every stored proof still verifies ───────────────────────────────────────────

def test_all_confirmed_proofs_verify_against_the_chain(api):
    """The ledger's core claim. Re-derives the hash for every proof on the instance."""
    proofs = api.get("/api/economy/proofs?limit=50").json()
    if not proofs:
        pytest.skip("no proofs recorded on this instance yet")

    unverified = []
    for proof in proofs:
        body = api.get(f"/api/economy/verify/{proof['task_id']}").json()
        if body["verified"] is not True:
            unverified.append((proof["task_id"], body["verified"], body["reason"]))

    assert not unverified, (
        "proofs that do not verify against the chain they claim to be on: "
        + json.dumps(unverified, indent=2)
    )


def test_verification_shows_its_working(api):
    """A verifier must be able to redo the hash by hand from what the endpoint returns."""
    import hashlib

    proofs = api.get("/api/economy/proofs?limit=1").json()
    if not proofs:
        pytest.skip("no proofs recorded on this instance yet")

    body = api.get(f"/api/economy/verify/{proofs[0]['task_id']}").json()
    assert body["hash_algorithm"] == "sha256"
    recomputed = hashlib.sha256(body["canonical_output"].encode()).hexdigest()
    assert recomputed == body["computed_hash"], (
        "the published canonical output does not hash to the published hash — "
        "the verification cannot be reproduced independently"
    )
    if body["verified"]:
        assert body["computed_hash"] == body["onchain_hash"]


# ── negative cases ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    f"/api/goals/{UNKNOWN}",
    f"/api/goals/{UNKNOWN}/tasks",
    f"/api/goals/{UNKNOWN}/stream",
    f"/api/tasks/{UNKNOWN}",
    f"/api/economy/agents/{UNKNOWN}",
    f"/api/economy/verify/{UNKNOWN}",
    f"/api/heal/attempts/{UNKNOWN}",
])
def test_unknown_ids_are_json_404s(api, path):
    r = api.get(path)
    assert r.status_code == 404, f"{path} -> {r.status_code}"
    assert "detail" in r.json()


@pytest.mark.parametrize("goal", ["", "   "])
def test_an_empty_goal_is_rejected(api, goal):
    r = api.post("/api/goals", json={"goal": goal})
    assert r.status_code == 400
    assert r.json()["detail"] == "goal must not be empty"


def test_a_malformed_goal_body_is_a_422(api):
    assert api.post("/api/goals", json={}).status_code == 422


def test_an_unknown_webhook_token_is_a_404(api):
    assert api.post(f"/api/webhooks/{UNKNOWN}", json={}).status_code == 404


# ── regressions fixed in this branch; these gate the next deploy ────────────────

@pytest.mark.parametrize("path", ["/api/nope", "/api/economy/nope", "/api/goals/a/b/c"])
def test_unmatched_api_paths_are_not_answered_by_the_spa(api, path):
    r = api.get(path)
    assert r.status_code == 404, (
        f"{path} -> {r.status_code} {r.headers.get('content-type')}; the SPA fallback is "
        "answering for the API and clients expecting JSON get HTML"
    )
    assert "text/html" not in r.headers.get("content-type", "")


@pytest.mark.parametrize("path,query", [
    ("/api/goals", "limit=-1"),
    ("/api/goals", "offset=-1"),
    ("/api/economy/proofs", "limit=-1"),
    ("/api/heal/attempts", "limit=-1"),
])
def test_negative_pagination_is_rejected(api, path, query):
    r = api.get(f"{path}?{query}")
    assert r.status_code == 422, (
        f"{path}?{query} -> {r.status_code}; SQLite reads LIMIT -1 as unbounded, so this "
        "returns the whole table from an unauthenticated endpoint"
    )


def test_an_oversized_goal_is_rejected(api):
    r = api.post("/api/goals", json={"goal": "x" * 50_000})
    assert r.status_code == 413, (
        f"a 50,000-character goal was accepted ({r.status_code}) and stored whole"
    )


def test_the_stream_of_a_finished_goal_closes(api):
    """Held open for 75 seconds and nine pings before this was fixed."""
    finished = api.get("/api/goals?status=COMPLETED&limit=1").json()["goals"]
    if not finished:
        pytest.skip("no completed goal on this instance to stream")

    goal_id = finished[0]["goal_id"]
    started = time.time()
    frames = []
    with httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(45, read=45),
                      auth=("mergit", PASSWORD) if PASSWORD else None) as c:
        with c.stream("GET", f"/api/goals/{goal_id}/stream") as r:
            assert r.status_code == 200
            for line in r.iter_lines():
                frames.append(line)
                if time.time() - started > 40:
                    pytest.fail(
                        "the stream for an already-COMPLETED goal did not close within "
                        f"40s; it emits keepalives forever. Frames: {frames[:6]}"
                    )

    assert any("goal_done" in f for f in frames), (
        f"a late subscriber was never told the goal had finished; got {frames[:6]}"
    )


# ── the whole product, on the live instance ─────────────────────────────────────

live_goal = pytest.mark.skipif(
    not RUN_GOAL, reason="set MERGIT_LIVE_GOAL=1 (spends provider quota, writes to the ledger)"
)

GOAL_TEXT = (
    "Explain what a write-ahead log is in a database, and specifically why a server "
    "application would enable it. Answer as exactly 4 short bullet points. "
    "Do not use web search — use your own knowledge."
)


@pytest.fixture(scope="module")
def completed_goal(api):
    """Submit one goal and drive it to a terminal state. Shared by the tests below."""
    if not RUN_GOAL:
        pytest.skip("set MERGIT_LIVE_GOAL=1")

    r = api.post("/api/goals", json={"goal": GOAL_TEXT})
    assert r.status_code == 202, r.text
    goal_id = r.json()["goal_id"]
    assert r.json()["status"] == "NEW"

    started = time.time()
    goal = None
    while time.time() - started < GOAL_TIMEOUT:
        time.sleep(3)
        goal = api.get(f"/api/goals/{goal_id}").json()
        if goal["status"] in ("COMPLETED", "FAILED"):
            break

    assert goal and goal["status"] == "COMPLETED", (
        f"goal ended {goal and goal['status']} after {int(time.time()-started)}s: "
        f"{goal and goal.get('error')}"
    )
    return goal


@live_goal
def test_the_goal_was_decomposed_into_a_real_dag(completed_goal):
    plan = completed_goal["plan"]
    assert plan, "the goal completed without a stored plan"
    ids = {t["id"] for t in plan["tasks"]}
    assert plan["terminal"] in ids
    for task in plan["tasks"]:
        assert task["agent"] in {"researcher", "writer", "coder", "integrator"}, task
        assert set(task["depends_on"]) <= ids, task
        assert task["id"] not in task["depends_on"], "a task depends on itself"


@live_goal
def test_every_task_finished(completed_goal):
    tasks = completed_goal["tasks"]
    assert tasks
    stuck = [(t["agent_name"], t["status"], t["error"]) for t in tasks if t["status"] != "DONE"]
    assert not stuck, f"tasks did not complete: {stuck}"


@live_goal
def test_every_template_points_at_a_task_that_produced_output(completed_goal):
    """Stored inputs keep their `{{task_id.output}}` templates on purpose — the worker
    resolves them in memory per attempt (`resolve_inputs`) and never writes the resolved
    values back, which is what lets a retry re-resolve against current outputs. So the
    checkable invariant is not "no templates remain" but "every template resolves":
    each referenced task must exist in this goal and have produced an output.
    """
    template_re = re.compile(r"\{\{(\w+)\.output(?:\.[\w\[\]\.0-9]+)?\}\}")
    by_id = {t["id"]: t for t in completed_goal["tasks"]}

    for task in completed_goal["tasks"]:
        for referenced in template_re.findall(json.dumps(task["inputs"])):
            assert referenced in by_id, (
                f"task {task['id']} references {referenced}, which is not a task on this "
                f"goal — interpolation would raise KeyError. Tasks: {list(by_id)}"
            )
            assert by_id[referenced]["output"] is not None, (
                f"task {task['id']} consumes {referenced}, which produced no output"
            )


@live_goal
def test_no_task_failed_on_interpolation(completed_goal):
    """A template the worker cannot resolve fails the task with this exact prefix."""
    broken = [
        (t["id"], t["error"]) for t in completed_goal["tasks"]
        if t["error"] and "Interpolation error" in t["error"]
    ]
    assert not broken, f"tasks failed to interpolate their inputs: {broken}"


@live_goal
def test_the_final_answer_contains_no_raw_template(completed_goal):
    """If an agent were handed an unresolved template it would tend to echo it back."""
    rendered = json.dumps(completed_goal["output"])
    assert "{{" not in rendered, f"a template leaked into the final answer: {rendered[:200]}"


@live_goal
def test_the_terminal_task_output_became_the_goal_output(completed_goal):
    plan_terminal = completed_goal["plan"]["terminal"]
    terminal = [t for t in completed_goal["tasks"] if t["id"].endswith(plan_terminal)]
    assert terminal, f"terminal task {plan_terminal} not among {[t['id'] for t in completed_goal['tasks']]}"
    assert completed_goal["output"] == terminal[0]["output"]


@live_goal
def test_every_completed_task_minted_a_verifiable_proof(api, completed_goal):
    """The end of the chain: real work → real hash → real transaction → verifies."""
    deadline = time.time() + 60  # the outbox drains on a timer
    pending = []
    while time.time() < deadline:
        pending = []
        for task in completed_goal["tasks"]:
            body = api.get(f"/api/economy/verify/{task['id']}").json()
            if body["verified"] is not True:
                pending.append((task["id"], body["verified"], body["reason"]))
        if not pending:
            break
        time.sleep(5)

    assert not pending, f"tasks whose proof never verified: {pending}"

    for task in completed_goal["tasks"]:
        body = api.get(f"/api/economy/verify/{task['id']}").json()
        assert body["computed_hash"] == body["onchain_hash"]
        assert body["tx_hash"].startswith("0x") and len(body["tx_hash"]) == 66, body["tx_hash"]
        assert body["block_number"] > 0


@live_goal
def test_the_agents_that_worked_gained_reputation(api, completed_goal):
    worked = {t["agent_name"] for t in completed_goal["tasks"]}
    leaderboard = {r["role"]: r for r in api.get("/api/economy/leaderboard").json()}
    for role in worked:
        assert role in leaderboard, f"{role} did work but is not on the leaderboard"
        assert leaderboard[role]["composite"] > 0
