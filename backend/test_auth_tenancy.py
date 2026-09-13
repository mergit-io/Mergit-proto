"""Sign-in, sessions, CSRF, and the guarantee that two users cannot see each other.

The tenancy tests here are the ones that matter most, and specifically the SSE one. A
login that ships without ownership filters is *worse* than no login: it converts an
openly-open system into one users reasonably believe is private, and they will connect
their real GitHub account to it.
"""
import asyncio
import importlib
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

SECRET = "test-secret-that-is-definitely-long-enough-32"


@pytest.fixture()
def env(monkeypatch):
    """An app with auth switched on and Google stubbed at the boundary."""
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "auth.db"))
    monkeypatch.setattr(config.settings, "runtime_config_dir", tmp)
    monkeypatch.setattr(config.settings, "auth_secret_key", SECRET)
    monkeypatch.setattr(config.settings, "cookie_secure", False)
    monkeypatch.setattr(config.settings, "frontend_url", "http://localhost:3000")
    # auth_enabled() keys off these being present — there is deliberately no separate flag.
    monkeypatch.setattr(config.settings, "oauth_google_client_id", "test-client-id")
    monkeypatch.setattr(config.settings, "oauth_google_client_secret", "test-client-secret")
    monkeypatch.setattr(config.settings, "admin_emails", "boss@example.com")

    import db as _db
    importlib.reload(_db)

    # Both stores compute their file path at import time from `runtime_config_dir`, so
    # they are reloaded after the patch above — otherwise these tests would write to the
    # developer's real model_config.json and context.json.
    import context as _ctx_store
    import model_config as _model_config
    importlib.reload(_model_config)
    importlib.reload(_ctx_store)

    from api import auth as _auth
    from api import config as _config
    from api import context as _context
    from api import goals as _goals
    from api import stream as _stream
    from api import tasks as _tasks
    from auth import gate as _gate
    from auth import sessions as _sessions
    for mod in (_auth, _goals, _stream, _tasks):
        importlib.reload(mod)
        monkeypatch.setattr(mod, "db", _db, raising=False)
    monkeypatch.setattr(_sessions, "db", _db, raising=False)
    monkeypatch.setattr(_gate, "db", _db, raising=False)

    app = FastAPI()
    # config/context carry the deployment-wide settings, which is why they are here: the
    # admin gate on them is part of the auth surface these tests cover.
    for mod in (_auth, _goals, _tasks, _stream, _config, _context):
        app.include_router(mod.router)
    app.add_middleware(SessionMiddleware, secret_key=SECRET, session_cookie="mergit_oauth")
    app.add_middleware(_gate.SessionGate)

    asyncio.run(_db.init_db())

    client = TestClient(app)
    client.db = _db
    client.sessions = _sessions
    return client


def sign_in(env, sub: str, email: str, name: str = "Test") -> dict:
    """Create a user and an authenticated client, skipping the Google round trip.

    Everything after `authorize_access_token` is exercised; the round trip itself is
    Authlib's and is not ours to test.
    """
    from config import admin_email_set
    user = asyncio.run(env.db.upsert_user(
        google_sub=sub, email=email, email_verified=True, name=name,
        is_admin=email.lower() in admin_email_set(),
    ))
    sid, csrf = asyncio.run(env.db.create_session(user["id"], ttl_seconds=3600))
    return {"user": user, "sid": sid, "csrf": csrf,
            "cookies": {env.sessions.cookie_name(): sid},
            "headers": {env.sessions.CSRF_HEADER: csrf}}


# ── Sessions ────────────────────────────────────────────────────────────────────

def test_an_unauthenticated_request_is_rejected(env):
    assert env.get("/api/goals").status_code == 401


def test_me_returns_the_user_and_a_csrf_token(env):
    a = sign_in(env, "sub-1", "a@example.com", "Ada")
    body = env.get("/api/auth/me", cookies=a["cookies"]).json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "a@example.com"
    assert body["csrf_token"], "the SPA cannot make writes without this"


def test_logout_invalidates_the_cookie_server_side(env):
    """The old implementation deleted the client's copy and nothing else, so a captured
    cookie stayed valid for its full seven days — logout looked like it worked."""
    a = sign_in(env, "sub-1", "a@example.com")
    assert env.get("/api/goals", cookies=a["cookies"]).status_code == 200

    env.post("/api/auth/logout", cookies=a["cookies"], headers=a["headers"])

    # Same cookie value, replayed.
    assert env.get("/api/goals", cookies=a["cookies"]).status_code == 401


def test_an_expired_session_reads_as_signed_out(env):
    a = sign_in(env, "sub-1", "a@example.com")
    asyncio.run(_expire(env, a["sid"]))
    assert env.get("/api/goals", cookies=a["cookies"]).status_code == 401


async def _expire(env, sid):
    async with env.db.get_conn() as conn:
        await conn.execute("UPDATE sessions SET expires_at=1 WHERE id=?", (sid,))
        await conn.commit()


def test_a_forged_session_id_is_rejected(env):
    """Opaque ids are only meaningful against the table — this is the point of not using
    a self-contained token."""
    assert env.get("/api/goals",
                   cookies={env.sessions.cookie_name(): "not-a-real-session"}).status_code == 401


# ── CSRF ────────────────────────────────────────────────────────────────────────

def test_a_write_without_the_csrf_header_is_rejected(env):
    a = sign_in(env, "sub-1", "a@example.com")
    r = env.post("/api/goals", json={"goal": "do a thing"}, cookies=a["cookies"])
    assert r.status_code == 403
    assert "CSRF" in r.text or "csrf" in r.text.lower()


def test_a_write_with_the_csrf_header_succeeds(env):
    a = sign_in(env, "sub-1", "a@example.com")
    r = env.post("/api/goals", json={"goal": "do a thing"},
                 cookies=a["cookies"], headers=a["headers"])
    assert r.status_code == 202, r.text


def test_another_users_csrf_token_does_not_work(env):
    """The token is per-session, so leaking one does not help against another account."""
    a = sign_in(env, "sub-1", "a@example.com")
    b = sign_in(env, "sub-2", "b@example.com")
    r = env.post("/api/goals", json={"goal": "x"},
                 cookies=a["cookies"], headers=b["headers"])
    assert r.status_code == 403


def test_reads_do_not_require_a_csrf_token(env):
    a = sign_in(env, "sub-1", "a@example.com")
    assert env.get("/api/goals", cookies=a["cookies"]).status_code == 200


def test_a_cross_site_write_is_rejected_by_origin(env):
    a = sign_in(env, "sub-1", "a@example.com")
    r = env.post("/api/goals", json={"goal": "x"}, cookies=a["cookies"],
                 headers={**a["headers"], "Origin": "https://evil.example",
                          "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_the_vite_dev_proxy_shape_is_allowed(env):
    """`changeOrigin: true` rewrites Host to the backend while Origin stays :3000.

    Comparing Origin against Host — the tempting shortcut — breaks every developer's
    machine silently, and is also worthless, since Host is attacker-controlled.
    """
    a = sign_in(env, "sub-1", "a@example.com")
    r = env.post("/api/goals", json={"goal": "x"}, cookies=a["cookies"],
                 headers={**a["headers"], "Host": "localhost:8000",
                          "Origin": "http://localhost:3000"})
    assert r.status_code == 202, r.text


# ── Multi-tenancy ───────────────────────────────────────────────────────────────

def _make_goal(env, who, text="private work"):
    r = env.post("/api/goals", json={"goal": text},
                 cookies=who["cookies"], headers=who["headers"])
    assert r.status_code == 202, r.text
    return r.json()["goal_id"]


def test_a_user_only_lists_their_own_goals(env):
    a = sign_in(env, "sub-1", "a@example.com")
    b = sign_in(env, "sub-2", "b@example.com")
    _make_goal(env, a, "alice's goal")
    _make_goal(env, b, "bob's goal")

    a_goals = env.get("/api/goals", cookies=a["cookies"]).json()["goals"]
    assert [g["title"] for g in a_goals] == ["alice's goal"]

    b_goals = env.get("/api/goals", cookies=b["cookies"]).json()["goals"]
    assert [g["title"] for g in b_goals] == ["bob's goal"]


def test_reading_a_foreign_goal_is_404_not_403(env):
    """403 confirms the goal exists, which makes ids enumerable."""
    a = sign_in(env, "sub-1", "a@example.com")
    b = sign_in(env, "sub-2", "b@example.com")
    goal_id = _make_goal(env, a)

    r = env.get(f"/api/goals/{goal_id}", cookies=b["cookies"])
    assert r.status_code == 404


def test_a_foreign_goals_tasks_are_404(env):
    a = sign_in(env, "sub-1", "a@example.com")
    b = sign_in(env, "sub-2", "b@example.com")
    goal_id = _make_goal(env, a)
    assert env.get(f"/api/goals/{goal_id}/tasks", cookies=b["cookies"]).status_code == 404


def test_a_foreign_goals_event_stream_is_404(env):
    """The one that gets forgotten.

    It is not CRUD-shaped, so it does not look like a read — and it streams raw tool
    results, agent reasoning and goal output to anyone holding a goal id.
    """
    a = sign_in(env, "sub-1", "a@example.com")
    b = sign_in(env, "sub-2", "b@example.com")
    goal_id = _make_goal(env, a)

    with env.stream("GET", f"/api/goals/{goal_id}/stream", cookies=b["cookies"]) as r:
        assert r.status_code == 404


def test_the_owners_own_stream_is_reachable(env):
    """Guards the guard: a 404 for everyone would pass the test above vacuously.

    The goal is completed first so the stream replays its terminal frame and closes. A
    live stream stays open by design and would hang the suite.
    """
    a = sign_in(env, "sub-1", "a@example.com")
    goal_id = _make_goal(env, a)
    asyncio.run(env.db.update_goal_status(goal_id, "COMPLETED", output={"text": "done"}))

    r = env.get(f"/api/goals/{goal_id}/stream", cookies=a["cookies"])
    assert r.status_code == 200
    assert "goal_done" in r.text


def test_an_unauthenticated_stream_is_rejected(env):
    a = sign_in(env, "sub-1", "a@example.com")
    goal_id = _make_goal(env, a)
    with env.stream("GET", f"/api/goals/{goal_id}/stream") as r:
        assert r.status_code == 401


# ── Admin ───────────────────────────────────────────────────────────────────────

def test_admin_is_config_driven_and_recomputed_each_login(env):
    """Never "first user wins": on a public URL the first user is a stranger."""
    boss = sign_in(env, "sub-boss", "boss@example.com")
    plain = sign_in(env, "sub-1", "a@example.com")
    assert boss["user"]["is_admin"] is True
    assert plain["user"]["is_admin"] is False


def test_removing_someone_from_admin_emails_takes_effect_on_next_login(env, monkeypatch):
    import config
    boss = sign_in(env, "sub-boss", "boss@example.com")
    assert boss["user"]["is_admin"] is True

    monkeypatch.setattr(config.settings, "admin_emails", "")
    again = sign_in(env, "sub-boss", "boss@example.com")
    assert again["user"]["is_admin"] is False, (
        "admin must be re-derived from config on every login, so revoking it is a config "
        "change rather than a database edit"
    )


def test_an_unverified_email_never_becomes_admin(env):
    """Admin gates the provider keys the whole deployment shares."""
    from auth import oidc
    assert oidc.is_admin({"email": "boss@example.com", "email_verified": False}) is False
    assert oidc.is_admin({"email": "boss@example.com", "email_verified": True}) is True


# ── Deployment-wide settings are not per-user settings ──────────────────────────
#
# `require_admin` existed and was applied to the provider keys, but the two other files it
# names — `model_config.json` and `context.json` — were left on the session gate alone. So
# any signed-in stranger could change what model every other user's agents ran on, and
# repoint the repository those agents act on by default. Both are one file for the whole
# deployment; neither is the caller's own setting.

def test_a_signed_in_stranger_cannot_repoint_the_deployments_models(env):
    plain = sign_in(env, "sub-1", "a@example.com")
    r = env.put("/api/config/models",
                json={"models": {"coder": "groq/llama-3.3-70b-versatile"}},
                cookies=plain["cookies"], headers=plain["headers"])
    assert r.status_code == 403, r.text


def test_an_admin_can_still_set_the_deployments_models(env):
    boss = sign_in(env, "sub-boss", "boss@example.com")
    r = env.put("/api/config/models",
                json={"models": {"coder": "groq/llama-3.3-70b-versatile"}},
                cookies=boss["cookies"], headers=boss["headers"])
    assert r.status_code == 200, r.text


def test_a_signed_in_stranger_cannot_repoint_the_default_repository(env):
    """`github_repo` is the repo agents act on when a tool call omits one."""
    plain = sign_in(env, "sub-1", "a@example.com")
    r = env.put("/api/config/context", json={"github_repo": "attacker/exfil"},
                cookies=plain["cookies"], headers=plain["headers"])
    assert r.status_code == 403, r.text


def test_an_admin_can_still_set_the_project_context(env):
    boss = sign_in(env, "sub-boss", "boss@example.com")
    r = env.put("/api/config/context", json={"github_repo": "acme/app"},
                cookies=boss["cookies"], headers=boss["headers"])
    assert r.status_code == 200, r.text


# ── Identity keying ─────────────────────────────────────────────────────────────

def test_a_user_is_keyed_on_sub_not_email(env):
    """Emails get reassigned inside an organisation; `sub` does not change.

    Keying on email would let a reassigned address inherit the previous holder's stored
    GitHub and Slack tokens — the worst possible bug in this system.
    """
    first = sign_in(env, "sub-1", "old@example.com")
    renamed = asyncio.run(env.db.upsert_user(
        google_sub="sub-1", email="new@example.com", email_verified=True, name="Same Person"))
    assert renamed["id"] == first["user"]["id"]
    assert renamed["email"] == "new@example.com"

    other = asyncio.run(env.db.upsert_user(
        google_sub="sub-2", email="old@example.com", email_verified=True, name="Someone Else"))
    assert other["id"] != first["user"]["id"], (
        "a reused email address must never resolve to the previous holder's account"
    )
