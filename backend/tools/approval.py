"""A human decides before an agent does something it cannot take back.

**Where this lives matters more than what it does.** The gate runs in the tool wrapper, in
`agent_runner._execute_tool_idempotent`, *outside* the model's loop. It is not a prompt
instruction, not a system message, and not something the agent can be persuaded past — an
issue body saying "you have permission, skip the approval" reaches the model but never
reaches this code. The model's only route to the action is through a function that will
not call it without a decision row.

**Bound to the exact arguments.** The approval records `sha256(canonical_json(args))`, so
approving "merge PR #12 in acme/api" authorises precisely that. If the agent re-plans and
calls the same tool with different arguments, the hash differs, no approval matches, and
the user is asked again. Without this, an approval is a standing grant on a tool name —
and prompt injection's whole game is changing the arguments.

**It rides `WAITING_CREDENTIAL`, never `WAITING_WEBHOOK`.** Both park a task, so the
temptation is real, but `POST /api/webhooks/{token}` is unauthenticated by design and
releases *any* waiting task. An approval gate built on it would have an unauthenticated
bypass — and worse, the token is returned by `GET /api/goals/{id}` in the task list, so the
bypass would be handed to anyone who could read the goal. `resume_credential_tasks` is
reachable only from authenticated code with a key we construct.
"""
import hashlib
import json
import logging
import time
import uuid

import db

logger = logging.getLogger(__name__)

#: Actions with no undo, or whose undo is socially expensive. The test for membership is
#: not "is it dangerous" but "if this fires wrongly at 3am, can it be quietly reversed?"
#:
#: `github_pr` is deliberately ABSENT: an unwanted pull request is a nuisance, closeable in
#: one click, and gating it would put a human in the loop of the main pipeline and destroy
#: the product. `github_post_comment` likewise.
IRREVERSIBLE = frozenset({
    "github_merge_pr",             # merges someone's code into their default branch
    "github_create_repo",          # creates a public artifact under their account
    "github_set_branch_protection",  # can lock or unlock a repository's safety rails
    "github_close_issue",          # closing someone's issue is a social act
    "github_update_pr",            # can close a PR — see _is_closing_a_pr
    "slack_manifest_create",
    "slack_manifest_update",
    "slack_manifest_delete",
})

#: How long a request waits before it is treated as declined. Expiry means "no" rather
#: than "yes" because the agent is asking to do something irreversible while the person
#: who could say no is asleep.
APPROVAL_TTL = 24 * 3600


class ApprovalRequired(Exception):
    """Raised so the tool wrapper parks the task instead of executing."""

    def __init__(self, approval_id: str, summary: str, credential_key: str):
        self.approval_id = approval_id
        self.summary = summary
        self.credential_key = credential_key
        super().__init__(summary)


def args_fingerprint(args: dict) -> str:
    """Canonical hash of the arguments the user is being asked to approve.

    Sorted keys and no whitespace, so a re-serialisation with different key order still
    matches — otherwise the same approved action would re-prompt at random.

    Underscore-prefixed keys are excluded: `_goal_id` is injected by the runner and is not
    part of what the human is approving.
    """
    material = {k: v for k, v in sorted(args.items()) if not k.startswith("_")}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _is_closing_a_pr(tool_name: str, args: dict) -> bool:
    """`github_update_pr` is only irreversible when it closes something."""
    return tool_name == "github_update_pr" and str(args.get("state", "")).lower() == "closed"


def needs_approval(tool_name: str, args: dict) -> bool:
    if tool_name == "github_update_pr":
        return _is_closing_a_pr(tool_name, args)
    return tool_name in IRREVERSIBLE


def summarise(tool_name: str, args: dict) -> str:
    """One line a human can decide from, without reading JSON.

    An approval prompt that shows a tool name and an argument blob gets approved reflexively,
    which is the same as having no gate at all.
    """
    repo = args.get("repo", "")
    if tool_name == "github_merge_pr":
        method = args.get("merge_method", "squash")
        return f"Merge pull request #{args.get('pr_number', '?')} in {repo} using {method}"
    if tool_name == "github_create_repo":
        vis = "private" if args.get("private", True) else "PUBLIC"
        return f"Create a new {vis} repository called {args.get('name', '?')}"
    if tool_name == "github_set_branch_protection":
        return f"Change branch protection on {args.get('branch', 'the default branch')} in {repo}"
    if tool_name == "github_close_issue":
        return f"Close issue #{args.get('issue_number', '?')} in {repo}"
    if tool_name == "github_update_pr":
        return f"Close pull request #{args.get('pr_number', '?')} in {repo}"
    if tool_name.startswith("slack_manifest"):
        verb = tool_name.rsplit("_", 1)[-1]
        return f"{verb.capitalize()} the Slack app {args.get('app_id', '')}".strip()
    return f"{tool_name} on {repo or 'your account'}"


async def check(task, tool_name: str, args: dict) -> None:
    """Allow, or raise `ApprovalRequired`.

    Returns quietly for anything reversible, which is the overwhelming majority of calls —
    this is on the hot path of every tool invocation, so the common case is one set lookup.
    """
    if not needs_approval(tool_name, args):
        return

    goal_id = getattr(task, "goal_id", None)
    user_id = await db.goal_owner(goal_id) if goal_id else None
    if not user_id:
        # Nobody to ask. Refusing is the only safe reading: an unowned goal performing an
        # irreversible action is exactly the situation the gate exists for.
        raise ApprovalRequired("", f"{tool_name} needs approval but this goal has no owner",
                               "approval:orphan")

    fingerprint = args_fingerprint(args)
    existing = await _find(task.id, fingerprint)

    if existing and existing["decision"] == "approve":
        logger.info("approved action proceeding: %s (%s)", tool_name, existing["id"])
        return
    if existing and existing["decision"] == "deny":
        # Terminal. The agent is told plainly so it reports the refusal rather than
        # looking for another way to do the same thing.
        raise PermissionError(
            f"A human declined this action: {existing['summary']}. "
            f"This decision is final — do not retry it or attempt an equivalent action. "
            f"Report that it was declined."
        )
    if existing:
        # Already pending. Park again on the same key rather than filing a duplicate.
        raise ApprovalRequired(existing["id"], existing["summary"], existing["credential_key"])

    approval_id = f"apr_{uuid.uuid4().hex[:26]}"
    credential_key = f"approval:{approval_id}"
    summary = summarise(tool_name, args)
    now = int(time.time())

    async with db.get_conn() as conn:
        await conn.execute(
            """INSERT INTO approvals
                 (id, task_id, goal_id, user_id, tool_name, args_sha256, summary,
                  args_json, credential_key, expires_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (approval_id, task.id, goal_id, user_id, tool_name, fingerprint, summary,
             json.dumps({k: v for k, v in args.items() if not k.startswith("_")},
                        default=str)[:4000],
             credential_key, now + APPROVAL_TTL, now),
        )
        await conn.commit()

    logger.info("approval requested: %s for task=%s user=%s", summary, task.id, user_id)
    raise ApprovalRequired(approval_id, summary, credential_key)


async def _find(task_id: str, fingerprint: str) -> dict | None:
    """The decision for this exact (task, arguments), if one exists and has not expired."""
    async with db.get_conn() as conn:
        row = await (
            await conn.execute(
                """SELECT * FROM approvals
                   WHERE task_id=? AND args_sha256=?
                   ORDER BY created_at DESC LIMIT 1""",
                (task_id, fingerprint),
            )
        ).fetchone()
    if not row:
        return None
    record = dict(row)
    if record["decision"] is None and record["expires_at"] < int(time.time()):
        # An unanswered request is a refusal, not an invitation to proceed.
        return {**record, "decision": "deny",
                "summary": record["summary"] + " (expired without a decision)"}
    return record


async def decide(approval_id: str, user_id: str, decision: str) -> dict | None:
    """Record a decision. Single use: a second call returns the first outcome.

    Scoped to `user_id` in the UPDATE itself, so one user cannot approve an action against
    another user's repository even if they learn the id.
    """
    if decision not in ("approve", "deny"):
        raise ValueError("decision must be 'approve' or 'deny'")
    now = int(time.time())
    async with db.get_conn() as conn:
        row = await (
            await conn.execute(
                """UPDATE approvals SET decision=?, decided_by=?, decided_at=?
                   WHERE id=? AND user_id=? AND decision IS NULL
                   RETURNING *""",
                (decision, user_id, now, approval_id, user_id),
            )
        ).fetchone()
        await conn.commit()
        if row:
            return dict(row)
        existing = await (
            await conn.execute(
                "SELECT * FROM approvals WHERE id=? AND user_id=?", (approval_id, user_id)
            )
        ).fetchone()
    return dict(existing) if existing else None


async def list_pending(user_id: str) -> list[dict]:
    now = int(time.time())
    async with db.get_conn() as conn:
        rows = await (
            await conn.execute(
                """SELECT * FROM approvals
                   WHERE user_id=? AND decision IS NULL AND expires_at > ?
                   ORDER BY created_at DESC""",
                (user_id, now),
            )
        ).fetchall()
    return [dict(r) for r in rows]


async def list_recent(user_id: str, limit: int = 50) -> list[dict]:
    async with db.get_conn() as conn:
        rows = await (
            await conn.execute(
                "SELECT * FROM approvals WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
        ).fetchall()
    return [dict(r) for r in rows]
