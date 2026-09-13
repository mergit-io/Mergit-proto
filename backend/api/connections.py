"""Connect and disconnect the accounts Mergit acts on your behalf with.

One route pair per provider, because that is the actual shape of the problem: there is no
"connect everything" and there cannot be. Each provider is its own authorization server
with its own consent screen, its own scopes and its own token. Signing in with Google
establishes *who you are*; these routes establish *what Mergit may do as you*, once per
provider.
"""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

import db
from auth.gate import require_user
from config import settings
from credentials import github_app, store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/connections", tags=["connections"])

#: How long a connect handshake may take. Long enough to read a consent screen, short
#: enough that a `state` captured from a browser history is useless later.
STATE_TTL = 900


def _sign_state(user_id: str, provider: str, goal_id: str = "") -> str:
    """A signed, expiring, user-bound `state`.

    Carries who started the flow so the callback can attribute it without trusting a
    session that may have changed, and it is what stops an attacker completing *their*
    consent into *your* account.
    """
    expires = int(time.time()) + STATE_TTL
    payload = f"{user_id}:{provider}:{goal_id}:{expires}"
    sig = hmac.new(settings.auth_secret_key.encode(), payload.encode(),
                   hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def _verify_state(state: str) -> dict | None:
    try:
        user_id, provider, goal_id, expires, sig = state.rsplit(":", 4)
    except ValueError:
        return None
    payload = f"{user_id}:{provider}:{goal_id}:{expires}"
    expected = hmac.new(settings.auth_secret_key.encode(), payload.encode(),
                        hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    if int(expires) < int(time.time()):
        return None
    return {"user_id": user_id, "provider": provider, "goal_id": goal_id}


def _done(provider: str, status: str, goal_id: str = "") -> RedirectResponse:
    """Send the browser back where the user started.

    Back to the goal when the connection was prompted mid-run, so the paused goal is on
    screen when it resumes; otherwise to the Connections page.
    """
    if goal_id:
        return RedirectResponse(f"{settings.frontend_url}/app/goals/{goal_id}?{provider}={status}")
    return RedirectResponse(f"{settings.frontend_url}/app/connections?{provider}={status}")


@router.get("")
async def list_connections(request: Request) -> JSONResponse:
    """What Mergit can currently do as this user.

    Metadata only — no token, not even masked. There is nothing here for the user to copy,
    so showing a masked secret would only imply otherwise.
    """
    user = require_user(request)
    conns = await store.list_connections(user["id"])
    repos = []
    gh = next((c for c in conns if c["provider"] == "github"), None)
    if gh and gh["installation_id"]:
        async with db.get_conn() as c:
            rows = await (
                await c.execute(
                    "SELECT full_name FROM installation_repos WHERE installation_id=?",
                    (gh["installation_id"],),
                )
            ).fetchall()
        repos = [r["full_name"] for r in rows]
    return JSONResponse({
        "connections": conns,
        "github_repositories": repos,
        "available": {
            "github": github_app.configured(),
            "slack": bool(settings.slack_client_id and settings.slack_client_secret),
        },
    })


# ── GitHub ──────────────────────────────────────────────────────────────────────

@router.post("/github/start")
async def github_start(request: Request, goal_id: str = Query("")) -> JSONResponse:
    """Where to send the user to install the Mergit GitHub App.

    Returns a URL rather than redirecting, because this is called by `fetch` from the SPA
    and a 302 to github.com would be swallowed by CORS.
    """
    user = require_user(request)
    if not github_app.configured():
        raise HTTPException(
            status_code=503,
            detail="The GitHub App is not configured on this deployment "
                   "(set GITHUB_APP_ID, GITHUB_APP_CLIENT_ID, GITHUB_APP_CLIENT_SECRET "
                   "and GITHUB_APP_PRIVATE_KEY).",
        )
    state = _sign_state(user["id"], "github", goal_id)
    url = (f"https://github.com/apps/{settings.github_app_slug}/installations/new"
           f"?state={state}")
    return JSONResponse({"url": url})


@router.get("/github/callback")
async def github_callback(
    code: str = Query(""),
    state: str = Query(""),
    installation_id: int | None = Query(None),
    setup_action: str = Query(""),
):
    """Complete a GitHub App installation.

    The step that matters is the verification against `GET /user/installations`. GitHub's
    own documentation says: *"Bad actors can hit this URL with a spoofed installation_id.
    Therefore, you should not rely on the validity of the installation_id parameter."*
    Trusting the query parameter would let an attacker attach someone else's installation
    to their own Mergit account and drive that person's repositories.
    """
    parsed = _verify_state(state)
    if not parsed:
        logger.warning("GitHub callback with bad or expired state")
        return _done("github", "failed")

    user_id, goal_id = parsed["user_id"], parsed["goal_id"]

    # An org that requires owner approval sends the user back with setup_action=request
    # and nothing is installed yet. Recording this is what gives them a screen that
    # explains the wait, instead of a Connections page that looks like it silently failed.
    if setup_action == "request":
        logger.info("GitHub install pending org approval for user=%s", user_id)
        return _done("github", "pending_org_approval", goal_id)

    if not code:
        return _done("github", "failed", goal_id)

    try:
        token_data = await github_app.exchange_code(
            code, f"{settings.frontend_url}/api/connections/github/callback")
        user_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 28800))

        # ★ The authorization check. Only an installation the USER can see is recorded.
        visible = await github_app.user_installations(user_token)
        visible_ids = {int(i["id"]) for i in visible}
        if installation_id is not None and int(installation_id) not in visible_ids:
            logger.warning("rejected spoofed installation_id=%s for user=%s",
                           installation_id, user_id)
            return _done("github", "failed", goal_id)

        chosen = None
        for inst in visible:
            if installation_id is None or int(inst["id"]) == int(installation_id):
                chosen = inst
                break
        if not chosen:
            return _done("github", "failed", goal_id)

        account = chosen.get("account") or {}
        gh_user = await github_app.whoami(user_token)
        now = int(time.time())

        await _record_installation(chosen, account, user_id, now)

        inst_token = await github_app.installation_token(int(chosen["id"]))
        repos = await github_app.installation_repositories(inst_token)
        await _record_repos(int(chosen["id"]), repos)

        await store.upsert_connection(
            user_id=user_id,
            provider="github",
            external_account_id=gh_user.get("login", ""),
            access_token=user_token,
            refresh_token=refresh_token,
            display_name=gh_user.get("name") or gh_user.get("login", ""),
            scopes=list((chosen.get("permissions") or {}).keys()),
            installation_id=int(chosen["id"]),
            account_type=account.get("type", "User"),
            access_expires_at=now + expires_in,
        )
    except Exception as e:
        logger.exception("GitHub connection failed for user=%s: %s", user_id, e)
        return _done("github", "failed", goal_id)

    # Release every task this user parked waiting for GitHub. Scoped to the user — the
    # old env-var keying released everyone's tasks whenever anyone saved a token.
    resumed = await db.resume_credential_tasks(f"conn:github:{user_id}")
    if resumed:
        import events
        for task in resumed:
            events.emit(task["goal_id"], "task_update",
                        {"task_id": task["id"], "status": "READY",
                         "agent": task["agent_name"]})
        logger.info("resumed %d task(s) after user=%s connected GitHub", len(resumed), user_id)

    return _done("github", "connected", goal_id)


async def _record_installation(inst: dict, account: dict, user_id: str, now: int) -> None:
    """Store the installation, and the join row that authorises this user to use it."""
    async with db.get_conn() as conn:
        await conn.execute(
            """INSERT INTO github_installations
                 (installation_id, account_login, account_type, repository_selection,
                  owner_user_id, permissions_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(installation_id) DO UPDATE SET
                 account_login=excluded.account_login,
                 account_type=excluded.account_type,
                 repository_selection=excluded.repository_selection,
                 permissions_json=excluded.permissions_json,
                 updated_at=excluded.updated_at""",
            (int(inst["id"]), account.get("login", ""), account.get("type", "User"),
             inst.get("repository_selection", "selected"), user_id,
             json.dumps(inst.get("permissions") or {}), now, now),
        )
        # The join that IS the authorization check. Written only after
        # GET /user/installations confirmed the pair.
        await conn.execute(
            """INSERT OR REPLACE INTO user_installations
                 (user_id, installation_id, verified_at) VALUES (?,?,?)""",
            (user_id, int(inst["id"]), now),
        )
        await conn.commit()


async def _record_repos(installation_id: int, repos: list[dict]) -> None:
    """Refresh the allowlist. Replaced wholesale, so removing a repo on GitHub removes it here."""
    async with db.get_conn() as conn:
        await conn.execute(
            "DELETE FROM installation_repos WHERE installation_id=?", (installation_id,))
        for repo in repos:
            await conn.execute(
                """INSERT OR IGNORE INTO installation_repos
                     (installation_id, full_name, repo_id) VALUES (?,?,?)""",
                (installation_id, repo["full_name"], repo.get("id")),
            )
        await conn.commit()


# ── Slack ───────────────────────────────────────────────────────────────────────

#: What a generated bot needs to do its job. `channels:manage` is what lets the smoke test
#: create and archive its own scratch channel rather than posting into a real one.
SLACK_BOT_SCOPES = [
    "chat:write", "chat:write.public", "channels:read", "channels:history",
    "channels:manage", "groups:read", "users:read", "app_mentions:read", "commands",
]
#: A user token, so the smoke test can post *as the installing human* and prove the bot
#: really receives an event from Slack rather than only replying to itself.
SLACK_USER_SCOPES = ["chat:write"]


@router.post("/slack/start")
async def slack_start(request: Request, goal_id: str = Query("")) -> JSONResponse:
    user = require_user(request)
    if not (settings.slack_client_id and settings.slack_client_secret):
        raise HTTPException(
            status_code=503,
            detail="Slack is not configured on this deployment "
                   "(set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET).",
        )
    query = urlencode({
        "client_id": settings.slack_client_id,
        "scope": ",".join(SLACK_BOT_SCOPES),
        "user_scope": ",".join(SLACK_USER_SCOPES),
        "redirect_uri": f"{settings.frontend_url}/api/connections/slack/callback",
        "state": _sign_state(user["id"], "slack", goal_id),
    })
    return JSONResponse({"url": f"https://slack.com/oauth/v2/authorize?{query}"})


@router.get("/slack/callback")
async def slack_callback(code: str = Query(""), state: str = Query("")):
    """Complete a Slack workspace install.

    The parsing below is the single most common Slack integration bug, so it is spelled
    out rather than inlined: the **bot** token is at the response root, and the **user**
    token is nested under `authed_user`. Reading `authed_user.access_token` as "the token"
    yields an `xoxp-` that cannot act as the bot, and the failure appears later as
    confusing permission errors rather than as a wrong-token error.
    """
    parsed = _verify_state(state)
    if not parsed or not code:
        return _done("slack", "failed")
    user_id, goal_id = parsed["user_id"], parsed["goal_id"]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data={
                    "client_id": settings.slack_client_id,
                    "client_secret": settings.slack_client_secret,
                    "code": code,
                    "redirect_uri": f"{settings.frontend_url}/api/connections/slack/callback",
                },
            )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("Slack rejected the code: %s", data.get("error"))
            return _done("slack", "failed", goal_id)

        bot_token = data["access_token"]                       # xoxb- — at the ROOT
        user_token = (data.get("authed_user") or {}).get("access_token", "")  # xoxp- — NESTED
        team = data.get("team") or {}

        await store.upsert_connection(
            user_id=user_id,
            provider="slack",
            external_account_id=team.get("id", ""),
            access_token=bot_token,
            # The user token rides in the refresh column: it is the second credential this
            # connection holds, it is long-lived, and it is bound by its own AAD purpose.
            refresh_token=user_token,
            display_name=team.get("name", ""),
            scopes=(data.get("scope") or "").split(","),
        )
    except Exception as e:
        logger.exception("Slack connection failed for user=%s: %s", user_id, e)
        return _done("slack", "failed", goal_id)

    resumed = await db.resume_credential_tasks(f"conn:slack:{user_id}")
    if resumed:
        import events
        for task in resumed:
            events.emit(task["goal_id"], "task_update",
                        {"task_id": task["id"], "status": "READY",
                         "agent": task["agent_name"]})

    return _done("slack", "connected", goal_id)


# ── Disconnect ──────────────────────────────────────────────────────────────────

@router.delete("/{provider}")
async def disconnect(provider: str, request: Request) -> JSONResponse:
    """Withdraw Mergit's authority for one provider.

    Order is deliberate: tell the provider first, then forget our copy. Backwards, we
    destroy the only handle we have on a token that is still live under Mergit's client
    id — the user believes they revoked it and nothing was withdrawn.
    """
    user = require_user(request)
    if provider not in ("github", "slack"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider!r}")

    conn = await store.get_connection(user["id"], provider)
    if not conn:
        return JSONResponse({"ok": True, "already_disconnected": True})

    try:
        access, _refresh = store.open_secrets(conn)
        if provider == "slack" and access:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post("https://slack.com/api/auth.revoke",
                                  headers={"Authorization": f"Bearer {access}"})
        # GitHub App: the installation is removed by the user on GitHub, not by us. We
        # drop our stored user token and say so in the UI, with a link to do the rest.
    except Exception as e:
        # A provider that will not accept the revocation must not prevent us forgetting
        # the credential — the user asked us to stop holding it.
        logger.warning("provider-side revoke failed for %s/%s: %s", user["id"], provider, e)

    await store.revoke_connection(user["id"], provider)
    logger.info("user=%s disconnected %s", user["id"], provider)
    return JSONResponse({
        "ok": True,
        "provider": provider,
        "note": ("Also remove the Mergit app at https://github.com/settings/installations "
                 "to fully revoke access." if provider == "github" else ""),
    })


@router.get("/audit")
async def audit(request: Request, limit: int = Query(100, ge=1, le=500)) -> JSONResponse:
    """Which agent used which of my connections, to do what, on which artifact."""
    user = require_user(request)
    return JSONResponse({"uses": await store.list_uses(user["id"], limit)})
