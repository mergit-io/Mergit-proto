"""
Self-healing: when a developer-side error is detected, automatically:
  1. File a GitHub issue on the omniBox repo with full context
  2. Spawn a new omniBox goal to research + fix + PR the bug
"""
import logging
import os

import db
from config import settings

logger = logging.getLogger(__name__)


async def _create_github_issue(title: str, body: str) -> dict | None:
    """Open an issue on the omniBox repo. Returns {number, url} or None on failure."""
    token = os.environ.get("GITHUB_TOKEN", "") or settings.github_token
    if not token:
        logger.warning("self_heal: no GITHUB_TOKEN — cannot file issue")
        return None
    repo = settings.omnibox_repo
    if not repo:
        logger.warning("self_heal: OMNIBOX_REPO not set — cannot file issue")
        return None
    try:
        from github import Github
        g = Github(token)
        r = g.get_repo(repo)
        # Create labels if they don't exist yet
        existing = {l.name for l in r.get_labels()}
        for lname, color, desc in [
            ("bug", "d73a4a", "Something isn't working"),
            ("auto-detected", "e4e669", "Filed automatically by self-heal"),
        ]:
            if lname not in existing:
                try:
                    r.create_label(lname, color, desc)
                except Exception:
                    pass
        issue = r.create_issue(
            title=title,
            body=body,
            labels=["bug", "auto-detected"],
        )
        logger.info("self_heal: filed issue #%d on %s — %s", issue.number, repo, issue.html_url)
        return {"number": issue.number, "url": issue.html_url}
    except Exception as e:
        logger.warning("self_heal: failed to create GitHub issue: %s", e)
        return None


async def trigger(goal_id: str, goal_title: str, failed_task_agent: str,
                  error: str, error_summary: str) -> None:
    """
    Called when a developer-side error is detected.
    Files a GitHub issue and spawns a self-fix goal.
    """
    repo = settings.omnibox_repo

    issue_title = f"[auto] Bug in {failed_task_agent} agent: {error_summary[:80]}"

    issue_body = f"""## Auto-detected bug in omniBox

**Detected by**: self-heal system
**Affected goal**: `{goal_id}` — _{goal_title}_
**Failed agent**: `{failed_task_agent}`

### Error
```
{error[:2000]}
```

### Context
This issue was automatically filed because the error matches patterns of a developer-side bug
(stack trace in omniBox source files or unexpected Python exception) rather than an external
failure (rate limits, bad credentials, user input).

### Expected fix
- Identify the root cause in the relevant source file
- Write a targeted fix
- Open a PR with tests if applicable
"""

    issue = await _create_github_issue(issue_title, issue_body)
    if not issue:
        return

    # Spawn a self-fix goal using the existing researcher→coder→integrator pipeline
    fix_goal_text = (
        f"Fix bug in the omniBox repository ({repo}).\n\n"
        f"Issue #{issue['number']}: {issue_title}\n"
        f"Issue URL: {issue['url']}\n\n"
        f"Error that occurred:\n{error[:1000]}\n\n"
        f"The error happened in the '{failed_task_agent}' agent during goal execution.\n\n"
        "Steps:\n"
        "1. Read the omniBox repository structure to understand the codebase\n"
        "2. Read the specific file(s) mentioned in the error traceback\n"
        "3. Identify the root cause of the bug\n"
        "4. Write a minimal, targeted fix — do not refactor unrelated code\n"
        "5. Create a pull request on the repository with the fix\n"
        "6. Post a comment on the issue with the PR link and a one-line explanation of the fix\n"
    )

    fix_goal = await db.create_goal(fix_goal_text)
    logger.info(
        "self_heal: spawned fix goal %s for issue #%d",
        fix_goal.id, issue["number"],
    )
