"""Which identity does a non-GitHub tool call act as, and is it authorised?

`github_client.py` answers that question for the twenty-four GitHub tools. This is the
same answer for the three services that came after it — Slack, Linear and Notion — and it
exists so that answer is written once. All three authenticate identically: one opaque
string in one header. Nothing about that is worth triplicating.

Resolution order matches GitHub's exactly, and for the same reasons:

1. **The goal's owner.** `agent_runner` injects `_goal_id` into every tool call, so
   `goals.user_id` names the human whose connection should be used. The token is fetched
   through `credentials.broker`, never through `store`, because `broker` is the only
   module permitted to decrypt (`test_route_coverage.py` asserts it).
2. **An explicit caller** — `_user_id`, for HTTP handlers that have a session but no goal.
3. **The deployment token** — `SLACK_BOT_TOKEN`, `LINEAR_API_KEY`, `NOTION_API_KEY`.
   Single-tenant fallback, and like GitHub's it applies **only** when `oauth_configured()`
   is false for that provider — that is, when this deployment cannot ask the user to
   connect for themselves. A silent fallback when a *particular* user's connection is
   missing would run one person's goal on another person's identity, which is the bug that
   shape of code always turns out to be.

When nothing resolves the tool returns the `WAITING_CREDENTIAL` sentinel rather than an
error, so the task parks and resumes on the same run once the human connects — a failed
goal would have to start again from scratch.
"""
import logging
import os
from typing import Any

from config import settings
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL

logger = logging.getLogger(__name__)

#: Everything this module knows how to authenticate. `env` is the single-tenant fallback
#: variable; `label` is what a human is told to connect.
PROVIDERS: dict[str, dict[str, str]] = {
    "slack":  {"env": "SLACK_BOT_TOKEN", "label": "Slack"},
    "linear": {"env": "LINEAR_API_KEY",  "label": "Linear"},
    "notion": {"env": "NOTION_API_KEY",  "label": "Notion"},
}


def _missing(provider: str, credential: str, message: str) -> dict[str, Any]:
    """The park sentinel, built per call so it can name the user who must connect.

    `credential` is the **resume key**, and getting it wrong is worse than it looks. The
    task is parked under this string, and `api/connections.py` releases parked tasks by
    calling `db.resume_credential_tasks("conn:<provider>:<user_id>")` after a successful
    connect. Park under the environment variable name instead and the two never meet: the
    user connects, the UI says connected, and the goal waits forever.

    So it is `conn:<provider>:<user_id>` whenever a user could connect and we know who they
    are, and the environment variable name only on the single-tenant path where there is
    no user and no connect flow to wait for.

    Returned by value, never shared as a module constant — see the same note in
    `github_client._missing`. A shared dict cannot carry a per-user resume key, and without
    one the first person to connect releases everybody's parked tasks.
    """
    return {
        WAITING_CREDENTIAL_SENTINEL: True,
        "credential": credential,
        "provider": provider,
        "message": message,
        # Only offered when there is something to click. `/app/connections` renders a card
        # per provider the deployment can actually start a flow for, so linking a user to
        # `?connect=linear` on a box with no Linear OAuth app sends them to a page with no
        # Linear on it. A link that goes nowhere is worse than no link: it says the fix is
        # self-service when the fix is an operator setting an environment variable.
        "connect_url": (f"/app/connections?connect={provider}"
                        if oauth_configured(provider) else ""),
    }


def oauth_configured(provider: str) -> bool:
    """True when this deployment can ask *this user* to connect `provider` themselves.

    The hinge of the fallback rule below. `github_client.app_configured()` plays the same
    part for GitHub.
    """
    prefix = provider  # slack_client_id, linear_client_id, notion_client_id
    return bool(getattr(settings, f"{prefix}_client_id", "")
                and getattr(settings, f"{prefix}_client_secret", ""))


def deployment_token(provider: str) -> str:
    """The shared, deployment-wide token for `provider`. **Not** a user's credential.

    Read from both places it can legitimately live, because they disagree: `os.environ` is
    what `PUT /api/config/keys` writes at runtime, while `settings` comes from
    `backend/.env` through pydantic-settings, which never touches `os.environ`.
    """
    env_name = PROVIDERS[provider]["env"]
    return os.environ.get(env_name, "") or getattr(settings, env_name.lower(), "") or ""


async def _resolve_user(args: dict) -> str | None:
    """Whose connection should this call use, if anyone's."""
    if args.get("_user_id"):
        return args["_user_id"]
    goal_id = args.get("_goal_id")
    if goal_id:
        import db
        return await db.goal_owner(goal_id)
    return None


async def _stored_token(provider: str, args: dict) -> str:
    """The calling user's stored token, or "" if there is no active connection."""
    user_id = await _resolve_user(args)
    if not user_id:
        return ""
    try:
        from credentials import broker
        return await broker.service_token(user_id, provider)
    except Exception:
        # NoConnection is the ordinary case and is not worth a stack trace; anything else
        # (a KEK rotation that lost a key, a corrupt row) must not crash the tool either,
        # because the caller's next step is to park the task and ask a human — which is
        # the correct response to both.
        return ""


async def credential_check(provider: str, args: dict) -> dict | None:
    """None if the call may proceed; the park sentinel if it may not.

    Called at the top of every Slack/Linear/Notion tool, mirroring
    `github_client.credential_check`. Doing it here rather than inside `token()` keeps the
    tools' `try/except Exception -> {"ok": False}` blocks intact: an exception raised
    inside that try would be swallowed into an ordinary error, and the task would fail
    where it should have parked.
    """
    if await _stored_token(provider, args):
        return None

    label = PROVIDERS[provider]["label"]
    user_id = await _resolve_user(args)

    # The deployment token is a single-tenant affordance, and it stops being one the moment
    # this deployment can ask a user to connect for themselves. Falling back here when a
    # *particular* user has no connection would run their goal on somebody else's identity
    # — posting to the operator's Slack, filing in the operator's Linear — while every log
    # line still named the right user. `github_client.credential_check` draws the same line
    # for the same reason.
    if oauth_configured(provider) and user_id:
        return _missing(
            provider,
            f"conn:{provider}:{user_id}",
            f"Connect your {label} account so Mergit can act on your behalf.",
        )

    if deployment_token(provider):
        return None

    return _missing(
        provider,
        PROVIDERS[provider]["env"],
        f"{label} access is required. Connect {label}, or set "
        f"{PROVIDERS[provider]['env']} on the deployment.",
    )


async def token(provider: str, args: dict) -> str:
    """The token this call should use. Assumes `credential_check` already passed.

    Prefers the user's connection over the deployment token, so a multi-tenant deployment
    that still has a leftover `.env` key does not quietly act as the wrong identity.
    """
    return await _stored_token(provider, args) or deployment_token(provider)


async def cache_scope(provider: str, args: dict) -> str:
    """Who a per-process lookup cache entry belongs to.

    Slack channel ids and Linear team ids are stable and worth caching, and both were
    cached in a plain module-level dict keyed by name alone. That is correct for exactly
    one workspace. With two connected users, the first workspace's `#eng-bugs` answers for
    the second — a message posted to a channel in someone else's Slack, from a lookup that
    never hit the network and so never had a chance to fail.

    The user id is the right scope because `store.get_connection` returns one active
    connection per provider per user, so a user maps to exactly one workspace. Calls on the
    deployment token share a scope because they share a workspace.
    """
    user_id = await _resolve_user(args)
    return user_id or "__deployment__"


async def audit(provider: str, args: dict, tool_name: str,
                target: str = "", outcome: str = "ok") -> None:
    """Record that a user's credential was used. Never raises.

    An audit write that fails must not take down a goal, and there is nothing to attribute
    on the deployment-token path, so both cases return quietly.
    """
    try:
        user_id = await _resolve_user(args)
        if not user_id:
            return
        from credentials import store
        conn = await store.get_connection(user_id, provider)
        if not conn:
            return
        await store.record_use(
            user_id=user_id, provider=provider, goal_id=args.get("_goal_id"),
            connection_id=conn["id"], tool_name=tool_name, target=target, outcome=outcome,
        )
    except Exception as e:
        logger.debug("audit write skipped for %s: %s", provider, e)
