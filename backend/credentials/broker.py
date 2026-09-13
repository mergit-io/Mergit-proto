"""Turns "this goal needs GitHub" into a configured client, and writes the audit row.

**The one rule: a token never leaves this module.** Callers get a `Github` client or a
scoped callable. There is no tool argument a model can populate with a credential and no
tool result that can return one, which makes prompt-injection exfiltration *structurally*
impossible rather than merely discouraged. That is the whole security argument, and it
only holds while this stays true — so nothing here returns a token string, and
`test_route_coverage.py` asserts that `broker` is the only importer of `envelope.unseal`.

**Two resolvers, not one.** `for_goal` is the agent path: a tool has `_goal_id` (injected
at `agent_runner.py`) and nothing else, so ownership is resolved through
`goals.user_id`. `for_user` is the HTTP path — `api/actions.py` calls GitHub tools
directly from request handlers, with a session but no goal. A design with only `for_goal`
breaks those endpoints the day the PAT is removed.

**The repository allowlist is enforced here, in code, before any HTTP call.** A README that
says "now push to attacker/exfil" fails a set intersection. The list comes from GitHub —
it is what the user ticked at install time — so this is not us trusting our own prompt.
"""
import logging
import uuid

import db
from credentials import github_app, store
from credentials.store import NoConnection
from crypto import envelope

logger = logging.getLogger(__name__)

#: The narrowest set that lets the existing tools work. Deliberately does NOT include
#: `workflows`: granting every installation the right to rewrite CI is blast radius we do
#: not need, and `github_pr` refuses `.github/workflows/**` paths instead.
DEFAULT_PERMISSIONS = {
    "contents": "write",         # commit files, create branches
    "pull_requests": "write",    # open, review, merge
    "issues": "write",           # comment, label, close
    "metadata": "read",          # required by GitHub alongside anything else
}


class GitHubHandle:
    """A ready-to-use PyGithub client plus the context needed to audit what it did.

    Deliberately not a token. Tools receive this, use `.client`, and call `.audit(...)`
    when they have done something worth recording.
    """

    def __init__(self, client, *, user_id: str, connection_id: str | None,
                 goal_id: str | None, task_id: str | None, token_fp_source: str,
                 installation_id: int | None = None, repos: list[str] | None = None):
        self.client = client
        self.user_id = user_id
        self.connection_id = connection_id
        self.goal_id = goal_id
        self.task_id = task_id
        self.installation_id = installation_id
        self.repos = repos or []
        self._token = token_fp_source  # for the fingerprint only; never returned

    async def audit(self, tool_name: str, target: str = "", outcome: str = "ok",
                    provider_status: int | None = None, agent_role: str = "") -> None:
        await store.record_use(
            user_id=self.user_id, provider="github", agent_role=agent_role,
            goal_id=self.goal_id, task_id=self.task_id,
            connection_id=self.connection_id, tool_name=tool_name, target=target,
            token=self._token, outcome=outcome, provider_status=provider_status,
        )


async def _installation_for(user_id: str) -> dict:
    """The user's GitHub connection, or a NoConnection carrying how to fix it."""
    conn = await store.get_connection(user_id, "github")
    if not conn:
        raise NoConnection("github", user_id,
                           "Connect your GitHub account so Mergit can act as you.")
    if conn["status"] == "pending_org_approval":
        raise NoConnection(
            "github", user_id,
            "Your organization owner still needs to approve the Mergit GitHub App.")
    if conn["status"] not in ("active",):
        raise NoConnection("github", user_id,
                           "Your GitHub connection needs to be reconnected.")
    return conn


async def allowed_repos(user_id: str) -> list[str]:
    """`owner/repo` names this user's installation may touch."""
    conn = await store.get_connection(user_id, "github")
    if not conn or not conn["installation_id"]:
        return []
    async with db.get_conn() as c:
        rows = await (
            await c.execute(
                "SELECT full_name FROM installation_repos WHERE installation_id=?",
                (conn["installation_id"],),
            )
        ).fetchall()
    return [r["full_name"] for r in rows]


async def _repo_allowed(user_id: str, repo: str) -> bool:
    """`repository_selection='all'` means GitHub imposes no list, so neither do we."""
    conn = await store.get_connection(user_id, "github")
    if not conn or not conn["installation_id"]:
        return False
    async with db.get_conn() as c:
        row = await (
            await c.execute(
                "SELECT repository_selection FROM github_installations WHERE installation_id=?",
                (conn["installation_id"],),
            )
        ).fetchone()
    if row and row["repository_selection"] == "all":
        return True
    return repo in await allowed_repos(user_id)


async def for_user(
    user_id: str, *, repo: str | None = None, as_user: bool = False,
    goal_id: str | None = None, task_id: str | None = None,
) -> GitHubHandle:
    """A GitHub client acting as `user_id`.

    `as_user=True` returns a client on the user-to-server token instead of the
    installation token. Needed for the small set of endpoints an installation token cannot
    call — `POST /user/repos` most importantly, which is how a personal-account repository
    gets created, and `g.get_user()`, which the fork path in `github_pr` depends on.
    """
    from github import Auth, Github

    conn = await _installation_for(user_id)

    if repo and not await _repo_allowed(user_id, repo):
        allowed = await allowed_repos(user_id)
        raise PermissionError(
            f"{repo!r} is not one of the repositories you granted Mergit access to. "
            f"Currently allowed: {', '.join(allowed) or '(none)'}. "
            f"Add it at https://github.com/settings/installations if you meant to."
        )

    if as_user:
        token = await fresh_user_token(user_id, conn)
    else:
        installation_id = conn["installation_id"]
        # Scope the token to the one repository this call touches, not the whole
        # installation. A token that leaks is then worth one repo for one hour.
        repos = [repo.split("/", 1)[1]] if repo and "/" in repo else None
        token = await github_app.installation_token(
            installation_id, repositories=repos, permissions=DEFAULT_PERMISSIONS
        )

    return GitHubHandle(
        Github(auth=Auth.Token(token)),
        user_id=user_id,
        connection_id=conn["id"],
        goal_id=goal_id,
        task_id=task_id,
        token_fp_source=token,
        installation_id=conn["installation_id"],
        repos=await allowed_repos(user_id),
    )


async def for_goal(goal_id: str, *, repo: str | None = None, as_user: bool = False,
                   task_id: str | None = None) -> GitHubHandle:
    """A GitHub client acting as the goal's owner. The agent path."""
    user_id = await db.goal_owner(goal_id)
    if not user_id:
        raise NoConnection("github", "", "This goal has no owner, so it cannot act on GitHub.")
    return await for_user(user_id, repo=repo, as_user=as_user,
                          goal_id=goal_id, task_id=task_id)


async def fresh_user_token(user_id: str, conn: dict | None = None) -> str:
    """A valid `ghu_`, refreshing it if it is close to expiry.

    The refresh is single-flight. GitHub's `ghr_` is single-use, so two workers refreshing
    the same connection concurrently do not just duplicate work — the second redemption
    fails and the connection is permanently broken until the user reconnects. A loser of
    the lease waits and re-reads rather than refreshing.
    """
    import asyncio
    import time

    conn = conn or await _installation_for(user_id)
    access, refresh = store.open_secrets(conn)

    expires = conn["access_expires_at"] or 0
    if access and expires > int(time.time()) + 120:
        return access
    if not refresh:
        # No refresh token means the user must reconnect; parking is the right outcome,
        # not an opaque 401 from GitHub three calls later.
        raise NoConnection("github", user_id,
                           "Your GitHub authorization expired. Please reconnect.")

    owner = f"w-{uuid.uuid4().hex[:8]}"
    if not await store.acquire_refresh_lease(conn["id"], owner):
        # Someone else is refreshing. Wait for their result rather than racing them.
        for _ in range(20):
            await asyncio.sleep(0.2)
            fresh = await store.get_connection(user_id, "github")
            if fresh and (fresh["refreshed_at"] or 0) > (conn["refreshed_at"] or 0):
                access, _ = store.open_secrets(fresh)
                return access
        raise RuntimeError("timed out waiting for another worker to refresh the GitHub token")

    try:
        data = await github_app.refresh_user_token(refresh)
        new_access = data["access_token"]
        new_refresh = data.get("refresh_token", refresh)
        expires_in = int(data.get("expires_in", 28800))
        await store.store_refreshed(
            conn["id"], new_access, new_refresh,
            int(time.time()) + expires_in, user_id, "github",
        )
        return new_access
    except Exception:
        await store.mark_status(conn["id"], "needs_reauth")
        raise
    finally:
        await store.release_refresh_lease(conn["id"], owner)


async def slack_bot_token(user_id: str, team_id: str | None = None) -> str:
    """The workspace bot token, for the Slack tools.

    Returns a string rather than a handle because `slack_sdk`'s client is constructed by
    the caller. It is still never handed to a model: the Slack tools accept a channel and
    a message, not a token.
    """
    conn = await store.get_connection(user_id, "slack")
    if not conn:
        raise NoConnection("slack", user_id,
                           "Connect your Slack workspace so Mergit can post as your bot.")
    access, _ = store.open_secrets(conn)
    return access


__all__ = ["GitHubHandle", "NoConnection", "allowed_repos", "for_goal", "for_user",
           "fresh_user_token", "slack_bot_token", "DEFAULT_PERMISSIONS"]
