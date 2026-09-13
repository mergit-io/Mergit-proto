"""Self-healing: when a developer-side error is detected, automatically

  1. Fingerprint the error and deduplicate against previous attempts
  2. Record the attempt so it can be shown, counted and audited
  3. File a GitHub issue on the Mergit repo with full context (or simulate it offline)
  4. Spawn a Mergit goal to research → fix → PR the bug

Two invariants keep this safe to run unattended:

  * **Dedup** — the same bug recurring 50 times files one issue, with a recurrence count.
  * **Depth guard** — a goal spawned by self-heal can never itself trigger self-heal, so a
    fix that fails cannot start an infinite heal loop.

Nothing here raises into the worker: every failure path logs and returns.
"""
import hashlib
import logging
import os
import re
import uuid

import db
import events
from config import settings

logger = logging.getLogger(__name__)

HEAL_CHANNEL = "heal"

#: A goal at this depth or beyond never triggers another heal cycle.
MAX_HEAL_DEPTH = 1

# Volatile details stripped before fingerprinting, so the same bug reported with different
# line numbers, ids, addresses or timestamps collapses to one fingerprint.
_VOLATILE = [
    (re.compile(r"line \d+"), "line N"),
    (re.compile(r"0x[0-9a-fA-F]+"), "0xADDR"),
    (re.compile(r"\b[0-9a-fA-F]{8,}\b"), "HEX"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"), "TIMESTAMP"),
    (re.compile(r"\b\d+\b"), "N"),
    (re.compile(r"\s+"), " "),
]


def fingerprint(agent_name: str, error: str) -> str:
    """Stable identity for 'this bug', independent of run-specific noise."""
    normalized = error or ""
    for pattern, replacement in _VOLATILE:
        normalized = pattern.sub(replacement, normalized)
    return hashlib.sha256(
        f"{agent_name}|{normalized.strip().lower()}".encode()
    ).hexdigest()[:32]


def _issue_body(goal_id: str, goal_title: str, agent: str, error: str) -> str:
    return f"""## Auto-detected bug in Mergit

**Detected by**: self-heal system
**Affected goal**: `{goal_id}` — _{goal_title}_
**Failed agent**: `{agent}`

### Error
```
{error[:2000]}
```

### Context
This issue was filed automatically because the error matches patterns of a developer-side
bug (a stack trace in Mergit source files or an unexpected Python exception) rather than an
external failure such as a rate limit, bad credentials or malformed user input.

### Expected fix
- Identify the root cause in the relevant source file
- Write a targeted fix
- Open a PR with tests if applicable
"""


async def _create_github_issue(title: str, body: str) -> dict | None:
    """Open an issue on the Mergit repo. Returns {number, url} or None."""
    # Deliberately NOT the per-user broker. Self-heal files issues on *Mergit's own*
    # repository, as Mergit — a user's delegated GitHub authority must never be spent
    # reporting a bug in Mergit, and their token has no business touching this repo.
    #
    # This line is also why the credential migration needs mechanical enforcement rather
    # than discipline: it reads the token directly and never called `github_token()`, so a
    # migration that greps for that function misses it entirely. It is the fourth file to
    # acquire its own copy of this logic.
    token = (settings.mergit_self_heal_token
             or os.environ.get("GITHUB_TOKEN", "")
             or settings.github_token)
    repo = settings.mergit_repo
    if not token or not repo:
        logger.info("self_heal: no GITHUB_TOKEN/repo — recording a simulated attempt instead")
        return None
    try:
        from github import Github

        gh = Github(token)
        repository = gh.get_repo(repo)
        existing = {label.name for label in repository.get_labels()}
        for name, color, description in [
            ("bug", "d73a4a", "Something isn't working"),
            ("auto-detected", "e4e669", "Filed automatically by self-heal"),
        ]:
            if name not in existing:
                try:
                    repository.create_label(name, color, description)
                except Exception:
                    pass
        issue = repository.create_issue(title=title, body=body, labels=["bug", "auto-detected"])
        logger.info("self_heal: filed issue #%d on %s — %s", issue.number, repo, issue.html_url)
        return {"number": issue.number, "url": issue.html_url}
    except Exception as e:
        logger.warning("self_heal: failed to create GitHub issue: %s", e)
        return None


def _fix_goal_text(repo: str, issue_ref: str, agent: str, error: str) -> str:
    return (
        f"Fix bug in the Mergit repository ({repo}).\n\n"
        f"{issue_ref}\n\n"
        f"Error that occurred:\n{error[:1000]}\n\n"
        f"The error happened in the '{agent}' agent during goal execution.\n\n"
        "Steps:\n"
        "1. Read the Mergit repository structure to understand the codebase\n"
        "2. Read the specific file(s) mentioned in the error traceback\n"
        "3. Identify the root cause of the bug\n"
        "4. Write a minimal, targeted fix — do not refactor unrelated code\n"
        "5. Create a pull request on the repository with the fix\n"
        "6. Post a comment on the issue with the PR link and a one-line explanation\n"
    )


async def trigger(goal_id: str, goal_title: str, failed_task_agent: str,
                  error: str, error_summary: str, task_id: str | None = None) -> dict | None:
    """Handle a detected developer-side error. Never raises."""
    try:
        # ── Depth guard: a fix goal that fails must not spawn another fix goal ──
        goal = await db.get_goal(goal_id)
        depth = getattr(goal, "heal_depth", 0) if goal else 0
        if depth >= MAX_HEAL_DEPTH:
            logger.info(
                "self_heal: goal %s is itself a heal goal (depth %d) — not healing again",
                goal_id, depth)
            return {"status": "skipped_depth", "goal_id": goal_id, "heal_depth": depth}

        # ── Dedup: one issue per distinct bug ──────────────────────────────────
        fp = fingerprint(failed_task_agent, error)
        existing = await db.find_heal_attempt_by_fingerprint(fp)
        if existing:
            count = await db.bump_heal_recurrence(existing["id"])
            logger.info(
                "self_heal: bug %s recurred (%d times) — not filing a duplicate", fp, count)
            events.emit(HEAL_CHANNEL, "heal_recurrence", {
                "id": existing["id"], "fingerprint": fp, "recurrence_count": count,
            })
            return {**existing, "status": "skipped_duplicate", "recurrence_count": count}

        repo = settings.mergit_repo
        issue_title = f"[auto] Bug in {failed_task_agent} agent: {error_summary[:80]}"
        body = _issue_body(goal_id, goal_title, failed_task_agent, error)

        attempt_id = str(uuid.uuid4())
        issue = await _create_github_issue(issue_title, body)
        # Without a token we still record the attempt and everything it would have filed,
        # so the feature is demonstrable with zero credentials.
        status = "filed" if issue else "simulated"

        attempt = await db.create_heal_attempt(
            attempt_id=attempt_id, fingerprint=fp, goal_id=goal_id, task_id=task_id,
            agent_name=failed_task_agent, error=error, error_summary=error_summary,
            classification="bug", status=status, issue_body=body,
        )
        if issue:
            await db.update_heal_attempt(
                attempt_id, issue_number=issue["number"], issue_url=issue["url"])

        issue_ref = (
            f"Issue #{issue['number']}: {issue_title}\nIssue URL: {issue['url']}"
            if issue else f"Detected bug: {issue_title}"
        )

        fix_goal = None
        try:
            fix_goal = await db.create_goal(
                _fix_goal_text(repo, issue_ref, failed_task_agent, error),
                # Mergit's own goal, run as Mergit. Self-heal files issues on Mergit's
                # repository with a configured token, deliberately outside the per-user
                # broker — a user's GitHub connection must never be spent fixing Mergit.
                user_id=db.SYSTEM_USER_ID,
                source="self_heal", heal_depth=depth + 1,
            )
            await db.update_heal_attempt(attempt_id, fix_goal_id=fix_goal.id)
            logger.info("self_heal: spawned fix goal %s (attempt %s)", fix_goal.id, attempt_id)
        except Exception as e:
            logger.warning("self_heal: could not spawn fix goal: %s", e)
            await db.update_heal_attempt(attempt_id, outcome="abandoned")

        result = {
            **attempt,
            "status": status,
            "issue_number": issue["number"] if issue else None,
            "issue_url": issue["url"] if issue else None,
            "fix_goal_id": fix_goal.id if fix_goal else None,
        }
        events.emit(HEAL_CHANNEL, "heal_started", {
            "id": attempt_id, "agent_name": failed_task_agent,
            "error_summary": error_summary, "status": status,
            "issue_url": result["issue_url"], "fix_goal_id": result["fix_goal_id"],
        })
        return result

    except Exception as e:
        logger.warning("self_heal.trigger failed for goal %s: %s", goal_id, e)
        return None


async def settle_outcome(fix_goal_id: str, goal_status: str) -> None:
    """Close the loop: record whether the spawned fix goal actually fixed anything."""
    try:
        attempt = await db.find_heal_attempt_by_fix_goal(fix_goal_id)
        if not attempt:
            return
        outcome = {"COMPLETED": "fixed", "FAILED": "failed"}.get(goal_status)
        if not outcome:
            return
        await db.update_heal_attempt(attempt["id"], outcome=outcome)
        logger.info("self_heal: attempt %s settled as %s", attempt["id"], outcome)
        events.emit(HEAL_CHANNEL, "heal_settled", {
            "id": attempt["id"], "outcome": outcome, "fix_goal_id": fix_goal_id,
        })
    except Exception as e:
        logger.warning("self_heal.settle_outcome failed for %s: %s", fix_goal_id, e)
