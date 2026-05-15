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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _verify_signature(body: bytes, signature: str | None) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature. Passes if no secret configured."""
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return True  # no secret configured — allow all (useful for local dev/demo)
    if not signature or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _build_issue_goal(payload: dict) -> str:
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
        "1. Read the base repository structure to understand the codebase\n"
        "2. Read the files changed in this PR\n"
        "3. Write a detailed code review: correctness, style, potential bugs, suggestions\n"
        "4. Post the review as a comment on the PR"
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
        goal_text = _build_issue_goal(payload)
        goal = await db.create_goal(goal_text)
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
        goal = await db.create_goal(goal_text)
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
        return {"ok": True, "message": "omniBox webhook connected ✓", "zen": payload.get("zen", "")}

    return {"ok": True, "status": "ignored", "event": event, "action": action}
