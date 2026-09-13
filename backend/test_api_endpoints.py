"""Contract tests for the routers that had none: health, config, keys, context,
webhooks, the GitHub receiver, actions and self-heal.

Of thirteen routers only `api/economy.py` was covered before this file. Everything here
runs against an isolated temp DB and a temp runtime-config directory, so no test can
touch a real `.env`, `context.json` or `model_config.json`.
"""
import asyncio
import hashlib
import hmac
import importlib
import json
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def env(monkeypatch):
    """Isolated DB + runtime config dir, with every module that caches a path reloaded."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("config.settings.db_path", os.path.join(tmp, "api.db"))
    monkeypatch.setattr("config.settings.runtime_config_dir", tmp)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", GH_SECRET)

    import db as _db
    importlib.reload(_db)

    # These read settings.runtime_config_dir at import time, so they must be reloaded
    # after the monkeypatch or they would write into the developer's real config.
    import context as _context
    import model_config as _model_config
    import model_health as _model_health
    importlib.reload(_context)
    importlib.reload(_model_config)
    _model_health._cooldowns.clear()

    from api import actions as _actions
    from api import config as _config
    from api import context as _ctx_api
    from api import github_webhook as _gh
    from api import heal as _heal
    from api import health as _health
    from api import keys as _keys
    from api import webhooks as _webhooks
    for mod in (_actions, _config, _ctx_api, _gh, _heal, _health, _keys, _webhooks):
        importlib.reload(mod)
    for mod in (_gh, _heal, _health, _keys, _webhooks):
        monkeypatch.setattr(mod, "db", _db, raising=False)
    monkeypatch.setattr(_ctx_api, "ctx_store", _context)
    monkeypatch.setattr(_config, "model_config", _model_config)
    monkeypatch.setattr(_config, "model_health", _model_health)

    app = FastAPI()
    for mod in (_health, _config, _ctx_api, _keys, _gh, _webhooks, _actions, _heal):
        app.include_router(mod.router)

    asyncio.run(_db.init_db())
    client = TestClient(app)
    client.db = _db
    client.tmp = tmp
    client.mods = {"keys": _keys, "actions": _actions, "model_config": _model_config,
                   "model_health": _model_health}
    return client


# ── /api/health ─────────────────────────────────────────────────────────────────

def test_health_reports_db_worker_and_chain(env):
    body = env.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["worker"] in ("running", "stopped")
    assert isinstance(body["ts"], int)
    assert "chain" in body and "chain_id" in body


def test_health_reports_the_worker_as_stopped_when_it_is(env, monkeypatch):
    import worker
    monkeypatch.setattr(worker, "_running", False)
    assert env.get("/api/health").json()["worker"] == "stopped"


def test_health_reports_a_degraded_db_instead_of_crashing(env, monkeypatch):
    """The container HEALTHCHECK hits this endpoint; it must answer even when broken."""
    from api import health as health_api

    class Boom:
        def __call__(self, *a, **k):
            raise RuntimeError("database is locked")

    monkeypatch.setattr(health_api.db, "get_conn", Boom())
    body = env.get("/api/health").json()
    assert body["db"] == "error"
    assert body["status"] == "ok", "health must still answer 200 so the container is not killed"


# ── /api/config/models ──────────────────────────────────────────────────────────

def test_model_config_lists_current_available_and_defaults(env):
    body = env.get("/api/config/models").json()
    assert set(body["models"]) == set(body["defaults"])
    assert body["available"], "the model picker has nothing to offer"
    assert all({"id", "label", "provider"} <= set(m) for m in body["available"])


def test_updating_a_role_persists_and_is_read_back(env):
    target = env.get("/api/config/models").json()["available"][1]["id"]
    r = env.put("/api/config/models", json={"models": {"coder": target}})
    assert r.status_code == 200
    assert r.json()["models"]["coder"] == target
    assert env.get("/api/config/models").json()["models"]["coder"] == target


def test_an_unknown_role_does_not_disturb_the_config(env):
    before = env.get("/api/config/models").json()["models"]
    r = env.put("/api/config/models", json={"models": {"not-a-role": "groq/llama-3.3-70b-versatile"}})
    assert r.status_code == 200
    assert r.json()["models"] == before


def test_an_empty_model_id_is_rejected(env):
    assert env.put("/api/config/models", json={"models": {"coder": ""}}).status_code == 400


def test_a_model_that_does_not_exist_is_rejected(env):
    """Saving an unknown id bricks every goal with an opaque provider error later, and
    this endpoint is unauthenticated."""
    r = env.put("/api/config/models", json={"models": {"orchestrator": "totally/made-up-model"}})
    assert r.status_code == 400, (
        "an unknown model id was accepted; the next goal fails with a provider error "
        "that names nothing the operator configured"
    )
    assert env.get("/api/config/models").json()["models"]["orchestrator"] != "totally/made-up-model"


def test_model_health_reports_cooldowns(env):
    env.mods["model_health"].mark_unhealthy("groq/llama-3.3-70b-versatile", 120)
    body = env.get("/api/config/model-health").json()
    assert body["all_healthy"] is False
    assert "groq/llama-3.3-70b-versatile" in body["unhealthy"]


# ── /api/config/context ─────────────────────────────────────────────────────────

def test_context_round_trips(env):
    assert env.get("/api/config/context").json()["github_repo"] == ""

    payload = {"github_repo": "acme/widget", "description": "a widget",
               "tech_stack": "python", "notes": "be careful"}
    r = env.put("/api/config/context", json=payload)
    assert r.status_code == 200 and r.json()["ok"] is True

    body = env.get("/api/config/context").json()
    assert {k: body[k] for k in payload} == payload


def test_context_ignores_unknown_fields(env):
    env.put("/api/config/context", json={"github_repo": "a/b", "evil": "x"})
    assert "evil" not in env.get("/api/config/context").json()


# ── /api/config/keys ────────────────────────────────────────────────────────────

def test_keys_are_reported_masked_never_in_full(env, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_abcdefghijklmnop1234")
    body = env.get("/api/config/keys").json()

    assert body["groq"]["set"] is True
    assert body["groq"]["masked"] == "gsk_ab...1234"
    assert "abcdefghijklmnop" not in json.dumps(body), "the raw key leaked in the response"


def test_an_unset_key_is_reported_as_unset(env, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    body = env.get("/api/config/keys").json()
    assert body["tavily"]["set"] is False
    assert body["tavily"]["masked"] is None


def test_an_unknown_provider_is_rejected(env):
    r = env.put("/api/config/keys", json={"provider": "skynet", "key": "x"})
    assert r.status_code == 400
    assert "skynet" in r.json()["detail"]


def test_an_empty_key_is_rejected(env):
    assert env.put("/api/config/keys", json={"provider": "groq", "key": "  "}).status_code == 400


def test_setting_a_key_writes_the_env_file_and_resumes_waiting_tasks(env):
    """The credential-resume side effect is the reason this endpoint exists."""
    async def setup():
        goal = await env.db.create_goal("needs a token", user_id="usr_legacy_demo")
        await env.db.create_tasks(
            [{"id": "t1", "agent": "integrator", "description": "open a PR",
              "inputs": {}, "depends_on": []}],
            goal.id, goal.trace_id,
        )
        await env.db.set_task_waiting_credential("t1", "GITHUB_TOKEN")
        return goal

    asyncio.run(setup())
    assert asyncio.run(env.db.get_task("t1")).status == "WAITING_CREDENTIAL"

    r = env.put("/api/config/keys", json={"provider": "github", "key": "ghp_secretvalue123"})
    assert r.status_code == 200
    assert r.json()["resumed_tasks"] == 1
    assert r.json()["masked"] == "ghp_se...e123"
    assert "ghp_secretvalue123" not in r.text, "the endpoint echoed the key back"

    assert asyncio.run(env.db.get_task("t1")).status == "READY"

    written = os.path.join(env.tmp, ".env")
    assert os.path.exists(written), "the key was never persisted"
    assert "GITHUB_TOKEN" in open(written).read()


# ── /api/webhooks/{token} ───────────────────────────────────────────────────────

def test_an_unknown_webhook_token_is_a_404(env):
    r = env.post("/api/webhooks/no-such-token", json={"any": "thing"})
    assert r.status_code == 404
    assert r.json()["detail"] == "No task waiting for this webhook token"


def test_a_webhook_resumes_the_waiting_task(env):
    async def setup():
        goal = await env.db.create_goal("waits for a callback", user_id="usr_legacy_demo")
        await env.db.create_tasks(
            [{"id": "w1", "agent": "integrator", "description": "wait",
              "inputs": {}, "depends_on": []}],
            goal.id, goal.trace_id,
        )
        await env.db.set_task_waiting_webhook("w1", "tok-abc")

    asyncio.run(setup())
    assert asyncio.run(env.db.get_task("w1")).status == "WAITING_WEBHOOK"

    r = env.post("/api/webhooks/tok-abc", json={"deployment": "green"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "task_id": "w1", "error": None}
    assert asyncio.run(env.db.get_task("w1")).status == "READY"


def test_replaying_a_webhook_does_not_resume_twice(env):
    async def setup():
        goal = await env.db.create_goal("waits once", user_id="usr_legacy_demo")
        await env.db.create_tasks(
            [{"id": "w2", "agent": "integrator", "description": "wait",
              "inputs": {}, "depends_on": []}],
            goal.id, goal.trace_id,
        )
        await env.db.set_task_waiting_webhook("w2", "tok-once")

    asyncio.run(setup())
    assert env.post("/api/webhooks/tok-once", json={}).status_code == 200
    assert env.post("/api/webhooks/tok-once", json={}).status_code == 404


def test_a_webhook_with_no_body_is_still_accepted(env):
    """Senders that post an empty body must not wedge the task forever."""
    async def setup():
        goal = await env.db.create_goal("empty callback", user_id="usr_legacy_demo")
        await env.db.create_tasks(
            [{"id": "w3", "agent": "integrator", "description": "wait",
              "inputs": {}, "depends_on": []}],
            goal.id, goal.trace_id,
        )
        await env.db.set_task_waiting_webhook("w3", "tok-empty")

    asyncio.run(setup())
    r = env.post("/api/webhooks/tok-empty", content=b"", headers={"content-type": "application/json"})
    assert r.status_code == 200


# ── /api/webhooks/github ────────────────────────────────────────────────────────

ISSUE_EVENT = {
    "action": "opened",
    "issue": {"number": 7, "title": "calculate() returns None for zero",
              "body": "It should return 0.", "html_url": "https://github.com/acme/widget/issues/7"},
    "repository": {"full_name": "acme/widget", "default_branch": "main"},
}

PR_EVENT = {
    "action": "opened",
    "pull_request": {"number": 11, "title": "Add caching", "body": "Speeds things up",
                     "user": {"login": "someone", "type": "User"},
                     "head": {"ref": "feat/cache"}, "base": {"ref": "main"},
                     "html_url": "https://github.com/acme/widget/pull/11"},
    "repository": {"full_name": "acme/widget", "default_branch": "main"},
}


#: The receiver fails closed, so every webhook test signs unless it is specifically
#: testing what happens when it does not. Passing `secret=None` sends it unsigned.
GH_SECRET = "s3cret"


def _post_gh(env, payload, event, secret=GH_SECRET):
    body = json.dumps(payload).encode()
    headers = {"X-GitHub-Event": event, "content-type": "application/json"}
    if secret:
        headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return env.post("/api/webhooks/github", content=body, headers=headers)


def test_an_opened_issue_creates_a_goal_carrying_the_issue_details(env):
    r = _post_gh(env, ISSUE_EVENT, "issues")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["event"] == "issue_opened"
    assert body["issue_number"] == 7 and body["repo"] == "acme/widget"

    goal = asyncio.run(env.db.get_goal(body["goal_id"]))
    for expected in ("acme/widget", "Issue #7", "calculate() returns None", "It should return 0."):
        assert expected in goal.goal_text, f"{expected!r} missing from the generated goal"


def test_an_opened_pr_creates_a_review_goal(env):
    r = _post_gh(env, PR_EVENT, "pull_request")
    body = r.json()
    assert body["event"] == "pr_opened" and body["pr_number"] == 11
    goal = asyncio.run(env.db.get_goal(body["goal_id"]))
    assert "Review the pull request" in goal.goal_text
    assert "feat/cache" in goal.goal_text


def test_a_bot_pr_is_skipped(env):
    """Otherwise Mergit reviews its own automated PRs in a loop."""
    payload = json.loads(json.dumps(PR_EVENT))
    payload["pull_request"]["user"]["type"] = "Bot"
    body = _post_gh(env, payload, "pull_request").json()
    assert body["status"] == "skipped"
    assert asyncio.run(env.db.list_goals()) == []


def test_a_closed_issue_is_ignored(env):
    payload = json.loads(json.dumps(ISSUE_EVENT))
    payload["action"] = "closed"
    body = _post_gh(env, payload, "issues").json()
    assert body["status"] == "ignored"
    assert asyncio.run(env.db.list_goals()) == []


def test_a_ping_is_acknowledged(env):
    body = _post_gh(env, {"zen": "Non-blocking is better than blocking."}, "ping").json()
    assert body["ok"] is True
    assert body["zen"] == "Non-blocking is better than blocking."


def test_malformed_json_is_a_400(env):
    # Signed, so the request gets past verification and fails on the JSON instead — the
    # signature is over bytes and does not care whether they parse.
    body = b"{not json"
    sig = "sha256=" + hmac.new(GH_SECRET.encode(), body, hashlib.sha256).hexdigest()
    r = env.post("/api/webhooks/github", content=body,
                 headers={"X-GitHub-Event": "issues", "content-type": "application/json",
                          "X-Hub-Signature-256": sig})
    assert r.status_code == 400


def test_a_valid_signature_is_accepted(env, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    assert _post_gh(env, ISSUE_EVENT, "issues", secret="s3cret").status_code == 200


def test_a_bad_signature_is_rejected(env, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    assert _post_gh(env, ISSUE_EVENT, "issues", secret="wrong").status_code == 401
    assert asyncio.run(env.db.list_goals()) == [], "a forged webhook created a goal"


def test_a_missing_signature_is_rejected_when_a_secret_is_set(env, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    assert _post_gh(env, ISSUE_EVENT, "issues", secret=None).status_code == 401


# ── /api/actions ────────────────────────────────────────────────────────────────

def test_listing_workflows_passes_the_repo_through(env, monkeypatch):
    seen = {}

    async def fake(args):
        seen.update(args)
        return {"ok": True, "repo": args["repo"], "workflows": [{"name": "ci"}]}

    monkeypatch.setattr(env.mods["actions"], "github_list_workflows", fake)
    body = env.get("/api/actions/workflows?repo=acme/widget").json()
    # `_user_id` rides along so the credential broker can resolve this caller's
    # GitHub connection: this route has a session but no goal, so the goal-based
    # resolver cannot serve it.
    assert seen["repo"] == "acme/widget"
    assert seen["_user_id"] == "usr_legacy_demo"
    assert body["workflows"] == [{"name": "ci"}]


def test_a_tool_failure_becomes_a_400_with_its_reason(env, monkeypatch):
    async def fake(args):
        return {"ok": False, "error": "GITHUB_TOKEN not set"}

    monkeypatch.setattr(env.mods["actions"], "github_list_workflows", fake)
    r = env.get("/api/actions/workflows?repo=acme/widget")
    assert r.status_code == 400
    assert r.json()["detail"] == "GITHUB_TOKEN not set"


def test_a_missing_repo_parameter_is_a_422(env):
    assert env.get("/api/actions/workflows").status_code == 422


def test_an_action_goal_is_created_with_the_instruction_inside(env):
    r = env.post("/api/actions/goal", json={"repo": "acme/widget", "instruction": "require CI to pass"})
    assert r.status_code == 200
    goal = asyncio.run(env.db.get_goal(r.json()["goal_id"]))
    assert "acme/widget" in goal.goal_text
    assert "require CI to pass" in goal.goal_text


# ── /api/heal ───────────────────────────────────────────────────────────────────

def test_heal_stats_are_zero_on_a_fresh_ledger(env):
    body = env.get("/api/heal/stats").json()
    assert body["total"] == 0 and body["fixed"] == 0


def test_heal_attempts_start_empty(env):
    assert env.get("/api/heal/attempts").json() == []


def test_an_unknown_heal_attempt_is_a_404(env):
    r = env.get("/api/heal/attempts/nope")
    assert r.status_code == 404
    assert r.json()["detail"] == "Unknown heal attempt"


@pytest.mark.parametrize("query", ["limit=-1", "limit=0", "limit=99999"])
def test_heal_attempts_pagination_is_bounded(env, query):
    assert env.get(f"/api/heal/attempts?{query}").status_code == 422


def test_the_secret_is_honoured_when_only_pydantic_settings_knows_about_it(env, monkeypatch):
    """A secret in backend/.env reaches `settings` but never `os.environ`.

    This is the third time this exact split has bitten this repo: `tools/github_client.py`
    exists because of it, and the webhook receiver had it too — it read only `os.environ`,
    so an operator who followed the documented setup got a receiver that silently failed
    OPEN. Render injects real env vars, which hid it in the one place it mattered most.

    Setting *only* the settings field is the whole point of the test. Using
    `monkeypatch.setenv` here would pass against the broken implementation.
    """
    import config
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(config.settings, "github_webhook_secret", "from-dotenv")

    assert _post_gh(env, ISSUE_EVENT, "issues", secret=None).status_code == 401
    assert _post_gh(env, ISSUE_EVENT, "issues", secret="wrong").status_code == 401
    assert _post_gh(env, ISSUE_EVENT, "issues", secret="from-dotenv").status_code == 200


def test_an_unset_secret_rejects_in_production_and_allows_in_debug(env, monkeypatch):
    """Fail closed is the whole point; DEBUG is the documented escape hatch for a laptop."""
    import config
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(config.settings, "github_webhook_secret", "")

    monkeypatch.setattr(config.settings, "debug", False)
    assert _post_gh(env, ISSUE_EVENT, "issues", secret=None).status_code == 401
    assert asyncio.run(env.db.list_goals()) == [], "an unsigned webhook created a goal"

    monkeypatch.setattr(config.settings, "debug", True)
    assert _post_gh(env, ISSUE_EVENT, "issues", secret=None).status_code == 200


def test_simulating_an_issue_does_not_go_through_the_webhook(env):
    """The Automate page's Simulate button has its own route, and it must keep working.

    Fail-closing the receiver without moving this would have broken the deployed demo:
    `frontend/src/pages/Webhooks.tsx` posted a hand-built payload at /api/webhooks/github
    with no signature at all. The goal text is built by the same function the real
    receiver uses, so the two paths cannot drift.
    """
    r = env.post("/api/actions/simulate-issue", json={
        "repo": "acme/widget", "title": "calculate() returns None for zero",
        "body": "It should return 0.", "issue_number": 7,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["simulated"] is True

    goals = asyncio.run(env.db.list_goals())
    assert len(goals) == 1
    text = goals[0].goal_text
    assert "acme/widget" in text and "Issue #7" in text
    assert "calculate() returns None for zero" in text
