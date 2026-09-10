"""Connecting Slack has to actually release the work that was waiting for it.

The park-and-resume design is the reason a missing credential is not a failure: the tool
returns a sentinel, the task stops in `WAITING_CREDENTIAL`, the human clicks Connect, and
the *same run* carries on. It only works if two strings agree — the key the task is parked
under, and the key `api/connections.py` passes to `db.resume_credential_tasks` after a
successful connect.

They did not agree. `service_client` parked under `SLACK_BOT_TOKEN` while the callback
released `conn:slack:<user_id>`, so a user could connect Slack, see the UI say connected,
and watch the goal wait forever. Nothing logged an error, because from each side's point of
view nothing went wrong.

This walks the whole path with Slack's token exchange stubbed: a parked task, a callback,
a stored connection, and the task running again on the user's own token rather than the
deployment's.
"""
import asyncio
import json
import os
import tempfile
import time

import pytest

import api.connections as connections
import db
import tools.service_client as svc
from credentials import broker, store
from crypto import envelope

USER = "u-alice"
GOAL = "g-1"
TASK = "g-1_t3"

#: What Slack answers `oauth.v2.access` with. The bot token is at the ROOT and the user
#: token is NESTED under `authed_user` — reading the nested one as "the token" yields an
#: `xoxp-` that cannot act as the bot.
SLACK_OAUTH_RESPONSE = {
    "ok": True,
    "access_token": "xoxb-alice-workspace",
    "scope": "chat:write,channels:history",
    "team": {"id": "T_ALICE", "name": "Alice Co"},
    "authed_user": {"id": "U_ALICE", "access_token": "xoxp-alice-user"},
}


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, _url, **_kw):
        return _Resp(self._payload)


@pytest.fixture()
def wired(monkeypatch):
    """A temp database with one parked task, and a key set to seal credentials with."""
    monkeypatch.setenv("MERGIT_KEK_CURRENT", "dGVzdC1rZXktMzItYnl0ZXMtbG9uZy0hISEhISEh")
    envelope._KEYS.clear()
    envelope.load_keys_and_scrub_env()

    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(db, "_db_path", os.path.join(tmp, "connect.db"))

    monkeypatch.setattr(connections.settings, "slack_client_id", "cid", raising=False)
    monkeypatch.setattr(connections.settings, "slack_client_secret", "sec", raising=False)
    monkeypatch.setattr(svc.settings, "slack_client_id", "cid", raising=False)
    monkeypatch.setattr(svc.settings, "slack_client_secret", "sec", raising=False)
    monkeypatch.setattr(connections.settings, "auth_secret_key", "test-secret", raising=False)

    async def _seed():
        await db.init_db()
        now = int(time.time())
        async with db.get_conn() as conn:
            await conn.execute(
                """INSERT INTO users (id, google_sub, email, email_verified, name,
                                      created_at, last_seen_at)
                   VALUES (?,?,?,1,?,?,?)""",
                (USER, "google-sub-alice", "alice@example.com", "Alice", now, now))
            await conn.execute(
                """INSERT INTO goals (id, title, goal_text, status, trace_id,
                                      created_at, updated_at, user_id)
                   VALUES (?,?,?,'RUNNING',?,?,?,?)""",
                (GOAL, "close the loop", "close the loop", "tr", now, now, USER))
            await conn.execute(
                """INSERT INTO tasks (id, goal_id, agent_name, description, status,
                                      trace_id, created_at, updated_at, waiting_credential)
                   VALUES (?,?,?,?, 'WAITING_CREDENTIAL', ?,?,?,?)""",
                (TASK, GOAL, "integrator", "reply in the thread", "tr", now, now,
                 f"conn:slack:{USER}"))
            await conn.commit()

    asyncio.run(_seed())
    yield
    envelope._KEYS.clear()


def _task_status() -> str:
    async def _read():
        async with db.get_conn() as conn:
            row = await (await conn.execute(
                "SELECT status FROM tasks WHERE id=?", (TASK,))).fetchone()
        return row["status"]
    return asyncio.run(_read())


def test_the_key_a_task_parks_under_is_the_key_connecting_releases(wired):
    """The bug this file exists for, stated as one assertion."""
    parked = asyncio.run(svc.credential_check("slack", {"_goal_id": GOAL}))
    assert parked is not None, "no connection yet, so the tool must park"
    assert parked["credential"] == f"conn:slack:{USER}"

    released = asyncio.run(db.resume_credential_tasks(parked["credential"]))
    assert [r["id"] for r in released] == [TASK]


def test_connecting_slack_stores_the_bot_token_and_resumes_the_goal(wired, monkeypatch):
    monkeypatch.setattr(connections.httpx, "AsyncClient",
                        lambda *a, **kw: _FakeClient(SLACK_OAUTH_RESPONSE))

    assert _task_status() == "WAITING_CREDENTIAL"

    state = connections._sign_state(USER, "slack", GOAL)
    response = asyncio.run(connections.slack_callback(code="the-code", state=state))
    assert response.status_code in (302, 307)
    assert "slack=connected" in response.headers["location"]

    # The bot token, not the user token: `authed_user.access_token` is an xoxp- that cannot
    # act as the bot, and the failure would surface later as confusing permission errors.
    assert asyncio.run(broker.service_token(USER, "slack")) == "xoxb-alice-workspace"

    conn = asyncio.run(store.get_connection(USER, "slack"))
    assert conn["external_account_id"] == "T_ALICE"
    assert conn["display_name"] == "Alice Co"
    assert "chat:write" in json.loads(conn["scopes"])

    assert _task_status() == "READY", "connecting must release the parked task"


def test_the_users_own_token_is_used_not_the_deployments(wired, monkeypatch):
    """The whole point of connecting: alice's goal acts as alice's workspace."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-the-deployments-own")
    monkeypatch.setattr(connections.httpx, "AsyncClient",
                        lambda *a, **kw: _FakeClient(SLACK_OAUTH_RESPONSE))

    state = connections._sign_state(USER, "slack", GOAL)
    asyncio.run(connections.slack_callback(code="the-code", state=state))

    assert asyncio.run(svc.credential_check("slack", {"_goal_id": GOAL})) is None
    assert asyncio.run(svc.token("slack", {"_goal_id": GOAL})) == "xoxb-alice-workspace"


def test_a_tampered_state_connects_nothing(wired, monkeypatch):
    """`state` is HMAC-signed. Without that, a link in an email connects an attacker's
    workspace to whichever account happens to be signed in."""
    monkeypatch.setattr(connections.httpx, "AsyncClient",
                        lambda *a, **kw: _FakeClient(SLACK_OAUTH_RESPONSE))

    good = connections._sign_state(USER, "slack", GOAL)
    tampered = good[:-4] + ("aaaa" if not good.endswith("aaaa") else "bbbb")

    response = asyncio.run(connections.slack_callback(code="the-code", state=tampered))
    assert "slack=failed" in response.headers["location"]
    assert asyncio.run(store.get_connection(USER, "slack")) is None
    assert _task_status() == "WAITING_CREDENTIAL"
