"""
GitHub webhook receiver — creates goals autonomously from GitHub events.

Setup in GitHub: Settings → Webhooks → Add webhook
  Payload URL: https://your-server/api/webhooks/github
  Content type: application/json
  Events: Issues, Pull requests (or "Send me everything")
"""
import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request

import db
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _webhook_secret() -> str:
    """Both places the secret can legitimately live, in the order that makes runtime edits work.

    Reading only `os.environ` was the bug: `GITHUB_WEBHOOK_SECRET` set the documented way
    (`backend/.env`, loaded by pydantic-settings, which never touches `os.environ`) left
    this function seeing nothing and failing open. Hosts that inject real env vars, such
    as Render, hid it completely. This is the same split `tools/github_client.py` exists
    to fix, and it had already reappeared here.
    """
    return os.environ.get("GITHUB_WEBHOOK_SECRET", "") or settings.github_webhook_secret


def _verify_signature(body: bytes, signature: str | None) -> bool:
    """Verify GitHub's HMAC-SHA256 webhook signature. **Fails closed.**

    An unverified receiver is not a minor gap: this endpoint creates goals, and a forged
    `issues.opened` carries an attacker-controlled `repository.full_name`, which points
    the agent pipeline — holding real GitHub write authority — at a repository of the
    attacker's choosing.

    With no secret configured we allow the request only in `DEBUG`, so a laptop keeps
    working and a deployment does not. Production had no secret at all, so it was open.
    """
    secret = _webhook_secret()
    if not secret:
        if settings.debug:
            logger.warning("GITHUB_WEBHOOK_SECRET is unset — accepting unsigned webhook (DEBUG only)")
            return True
        logger.error("GITHUB_WEBHOOK_SECRET is unset — rejecting webhook. Set it to receive events.")
        return False
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _hint(payload: dict) -> dict:
    """Provenance carried on the goal, so a later reader can see where it came from."""
    return {
        "source": "github_webhook",
        "installation_id": (payload.get("installation") or {}).get("id"),
        "repo": (payload.get("repository") or {}).get("full_name", ""),
        "sender": (payload.get("sender") or {}).get("login", ""),
    }


async def _owner_for_event(payload: dict) -> str:
    """Whose credentials should this goal run with?

    An installation on an organisation can be connected by several colleagues, so
    "look up the installation" returns a set, not an answer. Whoever gets picked owns the
    goal, sees its stream, receives its approval prompts, and has their name in the audit
    log for an action they may not have initiated — so the rule has to be deliberate:

    1. **The sender**, if they are a Mergit user with this installation. The person who
       opened the issue is the closest thing to an intent-holder.
    2. Otherwise the **recorded installation owner** — the user who first verified it, and
       changeable from the Connections page. This is the common case, because most issues
       are filed by outside contributors who have never heard of Mergit.
    3. Otherwise the legacy sentinel, so the goal still runs single-tenant rather than
       being dropped. It will park on a credential if it needs one, which is honest.
    """
    installation_id = (payload.get("installation") or {}).get("id")
    sender = (payload.get("sender") or {}).get("login", "")

    if not installation_id:
        return db.LEGACY_USER_ID

    async with db.get_conn() as conn:
        if sender:
            row = await (
                await conn.execute(
                    """SELECT c.user_id FROM connections c
                       JOIN user_installations ui
                         ON ui.user_id = c.user_id AND ui.installation_id = ?
                       WHERE c.provider='github' AND c.external_account_id = ?
                         AND c.revoked_at IS NULL
                       LIMIT 1""",
                    (int(installation_id), sender),
                )
            ).fetchone()
            if row:
                return row["user_id"]

        row = await (
            await conn.execute(
                "SELECT owner_user_id FROM github_installations WHERE installation_id=?",
                (int(installation_id),),
            )
        ).fetchone()
        if row and row["owner_user_id"]:
            return row["owner_user_id"]

    logger.warning("webhook for unknown installation %s — goal owned by the legacy user",
                   installation_id)
    return db.LEGACY_USER_ID


def build_issue_goal(payload: dict) -> str:
    issue = payload["issue"]
    repo = payload["repository"]
    default_branch = repo.get("default_branch", "main")
    body = (issue.get("body") or "").strip() or "No description provided."
    return (
        f"Fix GitHub issue in repository {repo['full_name']}.\n\n"
        f"Issue #{issue['number']}: {issue['title']}\n\n"
        f"Description:\n{body}\n\n"
        f"Repository: {repo['full_name']}\n"
        f"Issue URL: {issue['html_url']}\n"
        f"Default branch: {default_branch}\n\n"
        "Steps to complete:\n"
        "1. Read the repository structure (root directory listing)\n"
        "2. Find and read the files most likely relevant to the issue\n"
        "3. Write a code fix for the described problem\n"
        "4. Create a pull request on the repository with the fixed file(s)\n"
        "5. Post a comment on the issue with the PR link and a brief explanation"
    )


def _build_pr_review_goal(payload: dict) -> str:
    pr = payload["pull_request"]
    repo = payload["repository"]
    body = (pr.get("body") or "").strip() or "No description provided."
    return (
        f"Review the pull request in repository {repo['full_name']}.\n\n"
        f"PR #{pr['number']}: {pr['title']}\n"
        f"Author: {pr['user']['login']}\n"
        f"Branch: {pr['head']['ref']} → {pr['base']['ref']}\n\n"
        f"Description:\n{body}\n\n"
        f"Repository: {repo['full_name']}\n"
        f"PR URL: {pr['html_url']}\n\n"
        "Steps to complete:\n"
        f"1. Read the actual diff of PR #{pr['number']} — every changed file and its patch\n"
        "2. Read the surrounding code in the base repository for the files this PR touches, "
        "so the review judges the change in context\n"
        "3. Write a detailed code review: correctness, style, potential bugs, suggestions. "
        "Quote the specific lines you are commenting on — do not review from the PR title\n"
        f"4. Submit it as a review on PR #{pr['number']}"
    )


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
):
    body = await request.body()

    if not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        import json
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = x_github_event or "unknown"
    action = payload.get("action", "")
    repo_name = payload.get("repository", {}).get("full_name", "unknown")

    logger.info("GitHub webhook: event=%s action=%s repo=%s", event, action, repo_name)

    # ── Issue opened → fix it ────────────────────────────────────────────────────
    if event == "issues" and action == "opened":
        issue = payload["issue"]
        goal_text = build_issue_goal(payload)
        owner = await _owner_for_event(payload)
        goal = await db.create_goal(goal_text, user_id=owner,
                                    connection_hint=_hint(payload))
        logger.info("Created goal %s for issue #%s in %s", goal.id, issue["number"], repo_name)
        return {
            "ok": True,
            "goal_id": goal.id,
            "event": "issue_opened",
            "issue_number": issue["number"],
            "repo": repo_name,
        }

    # ── PR opened → review it ────────────────────────────────────────────────────
    if event == "pull_request" and action == "opened":
        pr = payload["pull_request"]
        # Skip PRs opened by bots (e.g. our own automated fixes)
        if pr["user"].get("type") == "Bot":
            return {"ok": True, "status": "skipped", "reason": "bot PR"}
        goal_text = _build_pr_review_goal(payload)
        owner = await _owner_for_event(payload)
        goal = await db.create_goal(goal_text, user_id=owner,
                                    connection_hint=_hint(payload))
        logger.info("Created goal %s for PR #%s in %s", goal.id, pr["number"], repo_name)
        return {
            "ok": True,
            "goal_id": goal.id,
            "event": "pr_opened",
            "pr_number": pr["number"],
            "repo": repo_name,
        }

    # ── Ping (webhook configured) ────────────────────────────────────────────────
    if event == "ping":
        return {"ok": True, "message": "Mergit webhook connected ✓", "zen": payload.get("zen", "")}

    return {"ok": True, "status": "ignored", "event": event, "action": action}
