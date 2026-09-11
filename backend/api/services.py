"""What Mergit has actually done on each connected service.

`api/connections.py` answers "what may Mergit do as me" — consent, granted and revoked.
This answers the different question a multi-app agent has to answer out loud: *did the
work land on every service it claimed?* The two are deliberately separate pages because
they fail separately. A connection can be healthy while every call through it is being
refused, and that gap is exactly where a silent failure lives.

Everything here is derived from `tool_calls`, never from an agent's own account of its
run. The row is written before the call is dispatched and settled with the provider's
answer, so a service that shows a successful write here has one — and a run that says it
posted to Slack with no Slack row on this page is caught by the difference.

One subtlety worth stating, because it is the difference between this page being honest
and being decorative: `status='SUCCESS'` is not the same as the call having worked. A
refused tool call — the approval gate, the grounding guard, the placeholder guard —
settles as SUCCESS carrying `{"ok": false, "refused": true}`, because a refusal is a
legitimate terminal outcome rather than an error to retry. Slack goes further and answers
HTTP 200 with `{"ok": false}` for a bad channel. So the outcome of a call is read from the
result body, not from the row's status.
"""
import json
import time
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

import db
from auth.gate import require_user
from credentials import store
from tools import TOOL_REGISTRY, github_client
from tools.service_client import PROVIDERS as SERVICE_PROVIDERS
from tools.service_client import deployment_token, oauth_configured

router = APIRouter(prefix="/api/services", tags=["services"])

#: How many recent tool calls this page reads. Counts are reported as "recent" in the UI
#: rather than as an all-time total, because that is what this window can honestly claim.
WINDOW = 1000

#: Providers in the order they enter a run: the thread comes in, the fix goes out, the
#: ticket and the note follow.
PROVIDERS: tuple[dict[str, str], ...] = (
    {"key": "slack",  "label": "Slack",  "does": "Reads the thread a problem is reported in, and replies in it."},
    {"key": "github", "label": "GitHub", "does": "Reads the repository, commits a fix on a branch and opens a pull request."},
    {"key": "linear", "label": "Linear", "does": "Files the issue, moves it, and comments the outcome on it."},
    {"key": "notion", "label": "Notion", "does": "Writes the incident note the fix is explained in."},
)

#: Result keys that carry a link to the thing that was created, in preference order.
_URL_KEYS = ("url", "html_url", "permalink", "page_url")
#: Result keys that name it. `identifier` is Linear's ENG-12; `title` is Notion's page.
_LABEL_KEYS = ("identifier", "title", "channel_name")

#: What to call the artifact when the service hands back a link but no name for it. A
#: Slack permalink ends in `p1789062420467499`, which is a timestamp and tells a reader
#: nothing; the tool that made it knows what it is.
_TOOL_LABELS: dict[str, str] = {
    "slack_post_message": "message",
    "slack_reply_in_thread": "thread reply",
    "github_pr": "pull request",
    "github_post_comment": "comment",
    "github_create_issue": "issue",
    "github_review_pr": "review",
    "github_merge_pr": "merge",
    "github_create_repo": "repository",
    "notion_create_page": "page",
    "notion_append_blocks": "page update",
    "linear_create_issue": "issue",
    "linear_comment": "comment",
}


def provider_of(tool_name: str) -> str:
    """`slack_reply_in_thread` → `slack`. `github_pr` → `github`.

    A prefix match rather than a registry lookup so a tool call recorded before a tool was
    renamed still attributes, and so a call to a tool that has since been removed does not
    vanish from the history it is evidence of.
    """
    head = tool_name.split("_", 1)[0]
    return head if head in {p["key"] for p in PROVIDERS} else ""


def outcome_of(status: str, result_json: str | None) -> str:
    """`ok` | `refused` | `failed` | `pending`, read from the body and not just the row.

    See the module docstring: SUCCESS means "we got an answer", not "it worked".
    """
    if status == "PENDING":
        return "pending"
    if status != "SUCCESS":
        return "failed"
    body = _body(result_json)
    if body.get("refused"):
        return "refused"
    if body.get("ok") is False or body.get("error"):
        return "failed"
    return "ok"


def _body(result_json: str | None) -> dict[str, Any]:
    if not result_json:
        return {}
    try:
        parsed = json.loads(result_json)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def artifact_of(tool_name: str, result_json: str | None) -> dict[str, str] | None:
    """The thing a call left behind, if it left one: a link and what to call it.

    Only real links. A tool that returns no URL — every read, and the writes that answer
    with an id alone — contributes nothing here rather than a plausible-looking URL
    assembled from parts, which is the failure mode this whole project exists to catch.
    """
    body = _body(result_json)
    url = next((body[k] for k in _URL_KEYS if isinstance(body.get(k), str) and body[k].startswith("http")), "")
    if not url:
        return None
    label = next((str(body[k]) for k in _LABEL_KEYS if body.get(k)), "")
    if not label and isinstance(body.get("result"), int):
        label = f"#{body['result']}"           # github_pr returns the PR number as `result`
    if not label:
        label = _TOOL_LABELS.get(tool_name, "") or url.rsplit("/", 1)[-1]
    return {
        "provider": provider_of(tool_name),
        "tool": tool_name,
        "url": url,
        "label": label[:80],
    }


async def _recent_calls(user_id: str, limit: int) -> list[dict]:
    """The user's own tool calls, newest first.

    Ownership derives through `tasks.goal_id → goals.user_id`, which is where it lives —
    `tool_calls` deliberately has no `user_id` of its own (see `migrations.py`), so this
    join *is* the tenancy check, and dropping it would show one tenant another's run.
    """
    async with db.get_conn() as conn:
        rows = await (
            await conn.execute(
                """SELECT tc.tool_name, tc.status, tc.result_json, tc.created_at,
                          t.goal_id, g.title AS goal_title, g.status AS goal_status,
                          g.created_at AS goal_created_at
                     FROM tool_calls tc
                     JOIN tasks t ON t.id = tc.task_id
                     JOIN goals g ON g.id = t.goal_id
                    WHERE g.user_id = ?
                 ORDER BY tc.created_at DESC
                    LIMIT ?""",
                (user_id, limit),
            )
        ).fetchall()
    return [dict(r) for r in rows]


def _tool_count(key: str) -> int:
    return sum(1 for name in TOOL_REGISTRY if provider_of(name) == key)


async def _access(user_id: str, key: str) -> dict[str, Any]:
    """How this deployment is authorised to act on a service, for this user.

    Four states, and the distinction between the middle two is the one that matters: a
    service Mergit is acting on with a *deployment* token works for this user and would
    not work for a second one, so it must not be reported the same way as a connection
    this user granted.
    """
    conn = await store.get_connection(user_id, key)
    if conn and conn["status"] == "active":
        # A raw connections row, so the account is `external_account_id` — `store.list_uses`
        # is the one that renames it to `account`.
        account = conn["display_name"] or conn["external_account_id"] or ""
        return {"access": "connected", "account": account, "connectable": True}
    if key == "github":
        connectable = github_client.app_configured()
        shared = bool(github_client.github_token())
    else:
        connectable = oauth_configured(key)
        shared = bool(deployment_token(key))
    if connectable:
        return {"access": "available", "account": "", "connectable": True}
    if shared:
        return {"access": "deployment", "account": "", "connectable": False}
    return {"access": "unconfigured", "account": "", "connectable": False}


@router.get("")
async def list_services(request: Request, runs: int = Query(8, ge=1, le=50)) -> JSONResponse:
    """Per-service reach, and the runs that prove it end to end."""
    user = require_user(request)
    calls = await _recent_calls(user["id"], WINDOW)

    stats: dict[str, dict] = {
        p["key"]: {"ok": 0, "failed": 0, "refused": 0, "pending": 0,
                   "last_used_at": None, "last_artifact": None}
        for p in PROVIDERS
    }
    # Goal id → what that run touched. Insertion order is the query's order, which is
    # newest first, so slicing the head takes the most recent runs without a second sort.
    by_goal: dict[str, dict] = {}

    for row in calls:
        key = provider_of(row["tool_name"])
        if not key:
            continue                      # web_search, code_exec, file_ops — not a service
        outcome = outcome_of(row["status"], row["result_json"])
        stat = stats[key]
        stat[outcome] += 1
        if stat["last_used_at"] is None:
            stat["last_used_at"] = row["created_at"]
        artifact = artifact_of(row["tool_name"], row["result_json"])
        if artifact and stat["last_artifact"] is None and outcome == "ok":
            stat["last_artifact"] = artifact

        run = by_goal.setdefault(row["goal_id"], {
            "goal_id": row["goal_id"], "title": row["goal_title"],
            "status": row["goal_status"], "created_at": row["goal_created_at"],
            "providers": [], "artifacts": [], "failures": 0,
        })
        if key not in run["providers"]:
            run["providers"].append(key)
        if outcome in ("failed", "refused"):
            run["failures"] += 1
        if artifact and outcome == "ok" and not any(a["url"] == artifact["url"] for a in run["artifacts"]):
            run["artifacts"].append(artifact)

    providers = []
    for meta in PROVIDERS:
        stat = stats[meta["key"]]
        providers.append({
            **meta,
            **await _access(user["id"], meta["key"]),
            "tools": _tool_count(meta["key"]),
            "calls": {k: stat[k] for k in ("ok", "failed", "refused", "pending")},
            "last_used_at": stat["last_used_at"],
            "last_artifact": stat["last_artifact"],
        })

    return JSONResponse({
        "providers": providers,
        "runs": list(by_goal.values())[:runs],
        "window": WINDOW,
        "calls_read": len(calls),
        "now": int(time.time()),
    })


@router.get("/activity")
async def activity(request: Request, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    """Every service call this user's goals made, newest first — the audit view.

    Distinct from `GET /api/connections/audit`, which lists uses of a *stored* credential
    and so is silent about calls made on a deployment token. This one reads the tool call
    itself, and is therefore complete for every path a call can take.
    """
    user = require_user(request)
    out = []
    for row in await _recent_calls(user["id"], WINDOW):
        key = provider_of(row["tool_name"])
        if not key:
            continue
        artifact = artifact_of(row["tool_name"], row["result_json"])
        out.append({
            "ts": row["created_at"],
            "provider": key,
            "tool": row["tool_name"],
            "goal_id": row["goal_id"],
            "goal_title": row["goal_title"],
            "outcome": outcome_of(row["status"], row["result_json"]),
            "url": artifact["url"] if artifact else "",
            "label": artifact["label"] if artifact else "",
        })
        if len(out) >= limit:
            break
    return JSONResponse({"uses": out, "window": WINDOW})
