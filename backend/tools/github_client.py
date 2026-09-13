"""Which GitHub identity is this tool call acting as, and is it authorised?

Every one of the twenty GitHub tools funnels through here, which makes this the single
place where per-user delegated authority is enforced. Three resolution paths, in order:

1. **The goal's owner** — the agent path. `agent_runner` injects `_goal_id` into every
   tool call, so `goals.user_id` names the human whose GitHub connection should be used.
2. **An explicit caller** — the HTTP path. `api/actions.py` calls GitHub tools directly
   from request handlers, which have a session but no goal. Without this, those endpoints
   break the day the shared token is removed.
3. **The shared token** — single-tenant fallback. A laptop, or a deployment that has not
   configured the GitHub App, keeps working exactly as before.

Path 3 is a deliberate transitional affordance and a deliberate risk: a silent fallback is
how a scoping bug comes to look like it worked. It applies **only** when the deployment has
no GitHub App configured at all — never as a per-request rescue when a user's connection is
missing, because that would let one user's goal quietly run on another identity.

When nothing resolves, the tool returns a `WAITING_CREDENTIAL` sentinel rather than an
error. That parks the task, the UI shows "Connect GitHub", and the *same run* continues
after the user authorises. A failed goal would have to be started again from scratch.
"""
import logging
import os
from typing import Any

from config import settings
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL

logger = logging.getLogger(__name__)


def _missing(credential: str, message: str, connect_url: str = "") -> dict[str, Any]:
    """The park sentinel.

    Built per call rather than shared as a module constant. The old `TOKEN_MISSING` dict
    was returned by reference from twenty call sites with `"credential": "GITHUB_TOKEN"`
    hardcoded, so it could not name *which user* needs to connect — and the resume key has
    to be per-user, or one person connecting releases everybody's parked tasks.
    """
    return {
        WAITING_CREDENTIAL_SENTINEL: True,
        "credential": credential,
        "provider": "github",
        "message": message,
        "connect_url": connect_url,
    }


#: Kept for the single-tenant fallback path and for tests that assert the old shape.
TOKEN_MISSING: dict[str, Any] = _missing(
    "GITHUB_TOKEN",
    "GitHub access is required. Connect your GitHub account, or set GITHUB_TOKEN.",
    "/app/connections?connect=github",
)


def github_token() -> str:
    """The shared, deployment-wide token. **Not** a user's credential.

    Still read from both places it can legitimately live, because they disagree: `os.environ`
    is written by `PUT /api/config/keys` at runtime, while `settings.github_token` comes from
    `backend/.env` via pydantic-settings, which never touches `os.environ`.
    """
    return os.environ.get("GITHUB_TOKEN", "") or settings.github_token or ""


def app_configured() -> bool:
    from credentials import github_app
    return github_app.configured()


async def _resolve_user(args: dict) -> str | None:
    """Whose GitHub connection should this call use, if anyone's."""
    if args.get("_user_id"):
        return args["_user_id"]
    goal_id = args.get("_goal_id")
    if goal_id:
        import db
        return await db.goal_owner(goal_id)
    return None


async def credential_check(args: dict) -> dict | None:
    """None if the call may proceed; the park sentinel if it may not.

    Called at the top of every GitHub tool, replacing the old `_require_token()` guard.
    Doing the check here rather than inside `client()` keeps the tools' existing
    `try/except Exception -> {"ok": False}` blocks intact — a `NoConnection` raised inside
    that try would be swallowed into an ordinary error and the task would fail instead of
    parking.
    """
    from credentials import store

    user_id = await _resolve_user(args)

    if app_configured() and user_id:
        conn = await store.get_connection(user_id, "github")
        if conn and conn["status"] == "active":
            return None
        if conn and conn["status"] == "pending_org_approval":
            return _missing(
                f"conn:github:{user_id}",
                "Your organization owner still needs to approve the Mergit GitHub App.",
                "/app/connections?connect=github",
            )
        return _missing(
            f"conn:github:{user_id}",
            "Connect your GitHub account so Mergit can act on your behalf.",
            "/app/connections?connect=github",
        )

    # Single-tenant fallback. Only when no GitHub App exists at all.
    if github_token():
        return None

    return TOKEN_MISSING


async def client(args: dict | None = None, *, as_user: bool = False):
    """A PyGithub client for this call.

    `as_user=True` selects the user-to-server token instead of the installation token,
    which a small number of endpoints require — notably `POST /user/repos` (creating a
    repository on a personal account) and `g.get_user()`, which the fork path depends on.
    An installation token simply cannot call those.
    """
    from github import Auth, Github

    args = args or {}
    user_id = await _resolve_user(args)

    if app_configured() and user_id:
        from credentials import broker
        handle = await broker.for_user(
            user_id, repo=args.get("repo"), as_user=as_user,
            goal_id=args.get("_goal_id"),
        )
        return handle.client

    token = github_token()
    if not token:
        from credentials.store import NoConnection
        raise NoConnection("github", user_id or "", "No GitHub credential is available.")
    return Github(auth=Auth.Token(token))


def resolve_repo(args: dict) -> str:
    """Repo from the tool args, falling back to the configured default."""
    return (
        args.get("repo")
        or os.environ.get("GITHUB_DEFAULT_REPO", "")
        or settings.github_default_repo
    )


async def audit(args: dict, tool_name: str, target: str = "", outcome: str = "ok") -> None:
    """Record that a credential was used, if one belonging to a user was.

    Never raises: an audit failure must not take down a goal. Skipped entirely on the
    shared-token path, where there is no user to attribute the action to.
    """
    try:
        user_id = await _resolve_user(args)
        if not user_id or not app_configured():
            return
        from credentials import store
        conn = await store.get_connection(user_id, "github")
        await store.record_use(
            user_id=user_id, provider="github", goal_id=args.get("_goal_id"),
            connection_id=conn["id"] if conn else None,
            tool_name=tool_name, target=target, outcome=outcome,
        )
    except Exception as e:
        logger.debug("audit write skipped: %s", e)
