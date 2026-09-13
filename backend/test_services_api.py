"""The services page tells the truth about what landed on each app.

Two things are being defended here, and they are the two ways this page could quietly
become decorative:

1. **A call that did not work must not be counted as one that did.** A refusal settles as
   `SUCCESS`, and Slack answers HTTP 200 with `{"ok": false}`. Read the row's status alone
   and the page reports a clean sweep across four services while nothing was posted —
   which is precisely the failure mode the project exists to catch.
2. **One tenant must not see another's runs.** `tool_calls` has no `user_id`; ownership
   derives through `tasks.goal_id → goals.user_id`, so the join *is* the tenancy check.
"""
import asyncio
import importlib
import json
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

SECRET = "test-secret-services"


@pytest.fixture()
def env(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "services.db"))
    monkeypatch.setattr(config.settings, "auth_secret_key", SECRET)
    monkeypatch.setattr(config.settings, "cookie_secure", False)
    monkeypatch.setattr(config.settings, "oauth_google_client_id", "test-client-id")
    monkeypatch.setattr(config.settings, "oauth_google_client_secret", "test-client-secret")

    import db as _db
    importlib.reload(_db)

    from api import services as _services
    from auth import gate as _gate
    from auth import sessions as _sessions
    from credentials import store as _store
    importlib.reload(_services)
    for mod in (_services, _sessions, _gate, _store):
        monkeypatch.setattr(mod, "db", _db, raising=False)

    app = FastAPI()
    app.include_router(_services.router)
    app.add_middleware(SessionMiddleware, secret_key=SECRET, session_cookie="mergit_oauth")
    app.add_middleware(_gate.SessionGate)

    asyncio.run(_db.init_db())
    client = TestClient(app)
    client.db = _db
    client.sessions = _sessions
    client.services = _services
    return client


def sign_in(env, sub: str, email: str) -> dict:
    user = asyncio.run(env.db.upsert_user(google_sub=sub, email=email,
                                          email_verified=True, name="Test"))
    sid, _csrf = asyncio.run(env.db.create_session(user["id"], ttl_seconds=3600))
    return {"user": user, "cookies": {env.sessions.cookie_name(): sid}}


def seed_call(env, *, user_id: str, tool: str, status: str = "SUCCESS",
              result: dict | None = None, title: str = "Ship the fix") -> str:
    """One goal, one task, one settled tool call — the smallest thing this page reads."""
    goal = asyncio.run(env.db.create_goal(f"{title} [{tool}]", user_id))
    tasks = asyncio.run(env.db.create_tasks(
        [{"id": f"t_{tool}_{goal.id[:6]}", "agent": "integrator", "description": tool,
          "inputs": {}, "depends_on": [], "status": "COMPLETED"}],
        goal.id, goal.trace_id))
    ikey = f"ik_{tool}_{goal.id[:8]}"
    asyncio.run(env.db.create_tool_call(tasks[0].id, tool, "{}", "hash", ikey))
    asyncio.run(env.db.settle_tool_call(
        ikey, json.dumps(result) if result is not None else None, status))
    return goal.id


# ── Reading an outcome from the body, not the row ───────────────────────────────

def test_a_refusal_is_not_counted_as_a_successful_call(env):
    """The approval gate and the guards settle as SUCCESS. They did not do the work."""
    from api.services import outcome_of
    assert outcome_of("SUCCESS", json.dumps(
        {"ok": False, "refused": True, "error": "needs approval"})) == "refused"


def test_slacks_two_hundred_with_ok_false_is_a_failure(env):
    """Slack's whole API answers HTTP 200 and puts the failure in the body."""
    from api.services import outcome_of
    assert outcome_of("SUCCESS", json.dumps({"ok": False, "error": "channel_not_found"})) == "failed"
    assert outcome_of("SUCCESS", json.dumps({"ok": True, "ts": "1.2"})) == "ok"


def test_an_unsettled_or_failed_row_reads_as_such(env):
    from api.services import outcome_of
    assert outcome_of("PENDING", None) == "pending"
    assert outcome_of("FAILED", None) == "failed"
    # Unparseable JSON must not read as success-with-no-error.
    assert outcome_of("SUCCESS", "{not json") == "ok"


def test_a_provider_is_read_from_the_tool_name_prefix(env):
    from api.services import provider_of
    assert provider_of("github_pr") == "github"
    assert provider_of("slack_reply_in_thread") == "slack"
    assert provider_of("linear_create_issue") == "linear"
    assert provider_of("notion_append_blocks") == "notion"
    # Not a service call — it must not be attributed to one.
    assert provider_of("web_search") == ""
    assert provider_of("code_exec") == ""


# ── Artifacts ───────────────────────────────────────────────────────────────────

def test_every_service_tool_is_named_provider_underscore_verb(env):
    """The SQL filter and `provider_of` must agree about what a service call is.

    `provider_of` splits on the first underscore, so a tool registered as bare `notion`
    would be attributed to Notion in Python and skipped by `instr(name, 'notion_') = 1` in
    the query — present in the counts on one path and missing on the other. Nothing is
    named that way today; this is what keeps it so.
    """
    from api.services import PROVIDERS, provider_of
    from tools import TOOL_REGISTRY
    keys = {p["key"] for p in PROVIDERS}
    for name in TOOL_REGISTRY:
        if provider_of(name):
            assert name.startswith(tuple(f"{k}_" for k in keys)), name


def test_a_call_with_no_link_contributes_no_artifact(env):
    """No plausible-looking URL assembled from parts. A read leaves nothing behind."""
    from api.services import artifact_of
    assert artifact_of("slack_read_thread", json.dumps({"ok": True, "messages": []})) is None
    assert artifact_of("linear_list_teams", json.dumps({"ok": True, "teams": ["ENG"]})) is None


def test_an_artifact_carries_the_name_the_service_gave_it(env):
    from api.services import artifact_of
    linear = artifact_of("linear_create_issue", json.dumps(
        {"ok": True, "identifier": "ENG-12", "url": "https://linear.app/x/issue/ENG-12"}))
    assert linear == {"provider": "linear", "tool": "linear_create_issue",
                      "url": "https://linear.app/x/issue/ENG-12", "label": "ENG-12"}
    pr = artifact_of("github_pr", json.dumps(
        {"action": "create_pr", "result": 44, "url": "https://github.com/a/b/pull/44"}))
    assert pr["label"] == "#44"


# ── The endpoint ────────────────────────────────────────────────────────────────

def test_every_provider_is_listed_even_with_no_calls(env):
    """A service with nothing on it is a fact worth showing, not a row to omit."""
    me = sign_in(env, "u1", "a@example.com")
    body = env.get("/api/services", cookies=me["cookies"]).json()
    assert [p["key"] for p in body["providers"]] == ["slack", "github", "linear", "notion"]
    for p in body["providers"]:
        assert p["calls"] == {"ok": 0, "failed": 0, "refused": 0, "pending": 0}
        assert p["last_used_at"] is None
        assert p["tools"] > 0          # every provider ships tools, counted from the registry


def test_calls_are_counted_per_provider_by_real_outcome(env):
    me = sign_in(env, "u1", "a@example.com")
    uid = me["user"]["id"]
    seed_call(env, user_id=uid, tool="slack_post_message",
              result={"ok": True, "url": "https://slack.com/archives/C1/p1"})
    seed_call(env, user_id=uid, tool="slack_reply_in_thread",
              result={"ok": False, "error": "channel_not_found"})
    seed_call(env, user_id=uid, tool="github_pr",
              result={"ok": True, "result": 44, "url": "https://github.com/a/b/pull/44"})
    seed_call(env, user_id=uid, tool="notion_create_page", status="FAILED")

    body = env.get("/api/services", cookies=me["cookies"]).json()
    by_key = {p["key"]: p for p in body["providers"]}
    assert by_key["slack"]["calls"]["ok"] == 1
    assert by_key["slack"]["calls"]["failed"] == 1
    assert by_key["github"]["calls"]["ok"] == 1
    assert by_key["notion"]["calls"]["failed"] == 1
    assert by_key["linear"]["calls"]["ok"] == 0
    assert by_key["github"]["last_artifact"]["label"] == "#44"
    # The failed Slack call must not be the one we advertise as the last thing that worked.
    assert by_key["slack"]["last_artifact"]["url"] == "https://slack.com/archives/C1/p1"


def test_a_run_lists_the_services_it_actually_touched(env):
    """The cross-app claim, made from evidence: one goal, four services, four rows."""
    me = sign_in(env, "u1", "a@example.com")
    uid = me["user"]["id"]
    goal = asyncio.run(env.db.create_goal("Fix the crash reported in Slack", uid))
    tasks = asyncio.run(env.db.create_tasks(
        [{"id": "t1", "agent": "integrator", "description": "do it", "inputs": {},
          "depends_on": [], "status": "COMPLETED"}], goal.id, goal.trace_id))
    for i, (tool, result) in enumerate([
        ("slack_read_thread", {"ok": True, "messages": [{"text": "it crashes"}]}),
        ("github_pr", {"ok": True, "result": 44, "url": "https://github.com/a/b/pull/44"}),
        ("linear_create_issue", {"ok": True, "identifier": "ENG-12",
                                 "url": "https://linear.app/x/issue/ENG-12"}),
        ("notion_create_page", {"ok": True, "title": "Incident",
                                "url": "https://notion.so/p1"}),
        ("slack_reply_in_thread", {"ok": True, "url": "https://slack.com/archives/C1/p2"}),
    ]):
        ikey = f"ik{i}"
        asyncio.run(env.db.create_tool_call(tasks[0].id, tool, "{}", "h", ikey))
        asyncio.run(env.db.settle_tool_call(ikey, json.dumps(result), "SUCCESS"))

    body = env.get("/api/services", cookies=me["cookies"]).json()
    run = next(r for r in body["runs"] if r["goal_id"] == goal.id)
    assert sorted(run["providers"]) == ["github", "linear", "notion", "slack"]
    # The read left nothing behind; the four writes each left one link.
    assert sorted(a["url"] for a in run["artifacts"]) == [
        "https://github.com/a/b/pull/44",
        "https://linear.app/x/issue/ENG-12",
        "https://notion.so/p1",
        "https://slack.com/archives/C1/p2",
    ]
    assert run["failures"] == 0


def test_calls_that_are_not_service_calls_are_never_read(env):
    """`result_json` is the expensive column and most of it belongs to calls this page
    discards. Filtering them out in the loop rather than the query made every poll pay to
    read and parse bodies it then threw away."""
    me = sign_in(env, "u1", "a@example.com")
    seed_call(env, user_id=me["user"]["id"], tool="web_search", result={"ok": True})
    seed_call(env, user_id=me["user"]["id"], tool="code_exec", result={"ok": True})
    seed_call(env, user_id=me["user"]["id"], tool="slack_post_message",
              result={"ok": True, "url": "https://x.slack.com/archives/C1/p1"})

    assert env.get("/api/services", cookies=me["cookies"]).json()["calls_read"] == 1


def test_runs_are_ordered_by_when_they_started(env):
    """The column says "Started", so the order has to be by start.

    The rows arrive in newest-*call* order, which is not the same thing: an old goal that
    receives one new call would otherwise sit above a goal that began yesterday.
    """
    me = sign_in(env, "u1", "a@example.com")
    uid = me["user"]["id"]
    old = seed_call(env, user_id=uid, tool="slack_post_message",
                    result={"ok": True, "url": "https://x.slack.com/archives/C1/p1"})
    new = seed_call(env, user_id=uid, tool="linear_create_issue",
                    result={"ok": True, "identifier": "ENG-1",
                            "url": "https://linear.app/x/issue/ENG-1"})

    async def _age(goal_id, started, called):
        async with env.db.get_conn() as c:
            await c.execute("UPDATE goals SET created_at=? WHERE id=?", (started, goal_id))
            await c.execute(
                """UPDATE tool_calls SET created_at=?
                    WHERE task_id IN (SELECT id FROM tasks WHERE goal_id=?)""",
                (called, goal_id))
            await c.commit()

    # The older goal has the newer call — the exact case the sort exists for.
    asyncio.run(_age(old, 1000, 9000))
    asyncio.run(_age(new, 5000, 2000))

    runs = env.get("/api/services", cookies=me["cookies"]).json()["runs"]
    assert [r["goal_id"] for r in runs] == [new, old]


def test_one_user_cannot_see_anothers_service_calls(env):
    """`tool_calls` has no owner of its own — the join through `goals` is the check."""
    mine = sign_in(env, "u1", "a@example.com")
    theirs = sign_in(env, "u2", "b@example.com")
    seed_call(env, user_id=theirs["user"]["id"], tool="slack_post_message",
              result={"ok": True, "url": "https://slack.com/archives/C9/p9"})

    body = env.get("/api/services", cookies=mine["cookies"]).json()
    assert body["runs"] == []
    assert {p["key"]: p["calls"]["ok"] for p in body["providers"]}["slack"] == 0

    activity = env.get("/api/services/activity", cookies=mine["cookies"]).json()
    assert activity["uses"] == []


def test_activity_omits_the_tools_that_are_not_service_calls(env):
    me = sign_in(env, "u1", "a@example.com")
    uid = me["user"]["id"]
    seed_call(env, user_id=uid, tool="web_search", result={"ok": True})
    seed_call(env, user_id=uid, tool="linear_comment",
              result={"ok": True, "url": "https://linear.app/x/issue/ENG-12#c"})

    uses = env.get("/api/services/activity", cookies=me["cookies"]).json()["uses"]
    assert [u["tool"] for u in uses] == ["linear_comment"]
    assert uses[0]["outcome"] == "ok"
    assert uses[0]["goal_id"]


def test_the_page_is_behind_the_session_gate(env):
    assert env.get("/api/services").status_code == 401
    assert env.get("/api/services/activity").status_code == 401


def test_a_link_with_no_name_is_called_what_the_tool_made(env):
    """A Slack permalink ends in a timestamp. `p1789062420467499` names nothing."""
    from api.services import artifact_of
    slack = artifact_of("slack_post_message", json.dumps(
        {"ok": True, "url": "https://x.slack.com/archives/C1/p1789062420467499"}))
    assert slack["label"] == "message"
    # A tool with no entry still gets something rather than an empty cell.
    other = artifact_of("github_update_pr", json.dumps(
        {"ok": True, "url": "https://github.com/a/b/pull/44"}))
    assert other["label"] == "44"
