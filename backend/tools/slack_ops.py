"""Slack read/write operations for agents.

Slack is where the work is *reported*, and — more usefully — where it is *asked for*. A
bug is described in a thread long before it is an issue, so an agent that can read the
thread starts from the same information a human would.

Three things here are deliberate and are the difference between this working in a demo
and working at all:

* **Channel names are resolved to ids.** A model writes `#eng-bugs` because that is what
  humans write. Slack's API takes `C0123ABCD`. Refusing the name would be technically
  correct and practically useless, so the name is looked up once and cached per process.
* **Every write returns a permalink.** `chat.postMessage` returns a `ts`, which is not an
  address a human can open, and `agent_runner._claimed_without_artifact` exists precisely
  to reject "I posted it" with nothing to click. `chat.getPermalink` turns the `ts` into
  a URL, so a real post is provably real and a claimed one cannot borrow its shape.
* **`ok: false` from Slack is returned as an error, not swallowed.** Slack answers HTTP
  200 for `channel_not_found`, `not_in_channel` and `missing_scope` alike. Reading only
  the status code is how an agent comes to believe it posted into a channel it was never
  invited to.
"""
import html
import json
import logging

import httpx

from tools.placeholders import refuse_if_unfilled as _refuse_if_unfilled
from tools.service_client import audit as _audit
from tools.service_client import cache_scope as _cache_scope
from tools.service_client import credential_check as _credential_check
from tools.service_client import token as _token

logger = logging.getLogger(__name__)

_API = "https://slack.com/api"
_PROVIDER = "slack"
_TIMEOUT = 20

#: scope → {name → id}, per process. Slack channel ids never change, and
#: `conversations.list` is a paginated call we would otherwise repeat on every message.
#:
#: Keyed by scope, not by name alone: `#eng-bugs` exists in more than one workspace, and a
#: cache that forgot whose workspace it read would answer the second user with the first
#: user's channel id — posting into a channel in somebody else's Slack, from a lookup that
#: never touched the network and so never had a chance to fail.
_CHANNEL_IDS: dict[str, dict[str, str]] = {}


def _channel_cache(scope: str) -> dict[str, str]:
    return _CHANNEL_IDS.setdefault(scope, {})

#: Slack error codes worth translating, because the raw string sends an agent into a
#: retry loop against a wall it cannot climb.
_EXPLAIN = {
    "not_in_channel": ("the bot is not a member of that channel — invite it with "
                       "`/invite @Mergit` in Slack, then retry"),
    "channel_not_found": ("no such channel, or the bot cannot see it. Private channels "
                          "require the bot to be invited before they are visible"),
    "missing_scope": ("the Slack app is missing a scope for this call — reinstall it "
                      "from /app/connections"),
    "invalid_auth": "the Slack token is invalid or was revoked — reconnect Slack",
    "thread_not_found": "no thread at that timestamp in that channel",
}


async def _call(method: str, args: dict, payload: dict, *, http_method: str = "POST") -> dict:
    """One Slack Web API call. Returns Slack's body, or a `{"ok": False, "error"}` dict.

    Slack's own envelope already uses `ok`, which is the same key the tool contract uses,
    so a successful call needs no reshaping and a failed one only needs its `error` code
    made legible.
    """
    tok = await _token(_PROVIDER, args)
    headers = {"Authorization": f"Bearer {tok}"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if http_method == "GET":
                resp = await client.get(f"{_API}/{method}", headers=headers, params=payload)
            else:
                resp = await client.post(f"{_API}/{method}", headers=headers, json=payload)
    except Exception as e:
        return {"ok": False, "error": f"Slack {method} failed: {e}"}

    try:
        body = resp.json()
    except Exception:
        return {"ok": False, "error": f"Slack {method} returned non-JSON (HTTP {resp.status_code})"}

    if not body.get("ok"):
        code = body.get("error", "unknown_error")
        detail = _EXPLAIN.get(code)
        return {"ok": False, "error": f"Slack {method}: {code}" + (f" — {detail}" if detail else "")}
    return body


async def _resolve_channel(args: dict, channel: str) -> tuple[str, str | None]:
    """(channel_id, error). Accepts an id, a `#name`, or a bare name."""
    channel = (channel or "").strip()
    if not channel:
        return "", "channel is required"
    # An id, not a name: Slack ids are uppercase and start with C (public), G (private)
    # or D (DM). A channel literally named "General" would collide, which is why the
    # length check is here — ids are 9-11 chars with no lowercase.
    if channel[0] in "CGD" and channel.isupper() and len(channel) >= 9:
        return channel, None

    name = channel.lstrip("#").lower()
    cache = _channel_cache(await _cache_scope(_PROVIDER, args))
    if name in cache:
        return cache[name], None

    cursor = ""
    for _ in range(10):  # 10 pages × 200 = 2000 channels, then we stop looking
        payload = {"limit": 200, "types": "public_channel,private_channel",
                   "exclude_archived": True}
        if cursor:
            payload["cursor"] = cursor
        body = await _call("conversations.list", args, payload, http_method="GET")
        if not body.get("ok"):
            return "", body.get("error", "could not list channels")
        for ch in body.get("channels", []):
            cache[ch["name"].lower()] = ch["id"]
        if name in cache:
            return cache[name], None
        cursor = (body.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return "", (f"no channel named #{name} is visible to the bot. Invite it with "
                f"`/invite @Mergit` in that channel, or pass the channel id")


async def _permalink(args: dict, channel_id: str, ts: str) -> str:
    """A clickable URL for a message, or "" if neither route yields one.

    Never raises and never fails the write: the message is already posted by the time this
    runs, and losing the link is not a reason to report a real post as a failure.

    There are two routes because the link is not cosmetic. `agent_runner` rejects a
    submission that claims a post with no address, so an empty permalink turns a real,
    successful post into a failed task. `chat.getPermalink` is the accurate one;
    `auth.test` plus the archive-URL format is the fallback for when it is unavailable.
    """
    body = await _call("chat.getPermalink", args,
                       {"channel": channel_id, "message_ts": ts}, http_method="GET")
    if body.get("ok") and body.get("permalink"):
        return body["permalink"]

    who = await _call("auth.test", args, {}, http_method="GET")
    team_url = who.get("url", "") if who.get("ok") else ""
    if not team_url or not ts:
        return ""
    # https://team.slack.com/archives/C0123ABCD/p1694500000123456 — the `p` form is the ts
    # with its decimal point removed, which is how every Slack deep link is built.
    return f"{team_url.rstrip('/')}/archives/{channel_id}/p{ts.replace('.', '')}"


def _trim(messages: list[dict], limit: int) -> list[dict]:
    """Only the fields an agent can act on. A raw Slack message is ~40 keys of blocks,
    edited-history and reaction metadata that cost context and answer nothing.

    Text is HTML-unescaped on the way out. Slack stores `&`, `<` and `>` escaped, so a
    pasted Python session arrives as `&gt;&gt;&gt; largest([-5, -2, -9])` — which is what
    the coder agent would then try to reproduce. The bug report is the input to the fix;
    handing it over mangled is how a correct pipeline produces a wrong patch.
    """
    out = []
    for m in messages[:limit]:
        out.append({
            "ts": m.get("ts"),
            "user": m.get("user") or m.get("bot_id") or "",
            "text": html.unescape(m.get("text") or "")[:4000],
            "thread_ts": m.get("thread_ts"),
            "reply_count": m.get("reply_count", 0),
        })
    return out


# ── List channels ────────────────────────────────────────────────────────────────

async def slack_list_channels(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    body = await _call("conversations.list", args,
                       {"limit": 200, "types": "public_channel,private_channel",
                        "exclude_archived": True}, http_method="GET")
    if not body.get("ok"):
        return body
    channels = [{"id": c["id"], "name": c["name"], "is_member": c.get("is_member", False)}
                for c in body.get("channels", [])]
    cache = _channel_cache(await _cache_scope(_PROVIDER, args))
    for c in channels:
        cache[c["name"].lower()] = c["id"]
    await _audit(_PROVIDER, args, "slack_list_channels")
    return {"ok": True, "channels": channels, "count": len(channels)}


SLACK_LIST_CHANNELS_SCHEMA = {
    "description": "List the Slack channels this workspace bot can see, with their ids.",
    "type": "object",
    "properties": {},
    "required": [],
}


# ── Read a channel ───────────────────────────────────────────────────────────────

async def slack_read_channel(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    channel_id, err = await _resolve_channel(args, args.get("channel", ""))
    if err:
        return {"ok": False, "error": err}
    limit = min(int(args.get("limit", 20) or 20), 100)
    body = await _call("conversations.history", args,
                       {"channel": channel_id, "limit": limit}, http_method="GET")
    if not body.get("ok"):
        return body
    await _audit(_PROVIDER, args, "slack_read_channel", target=channel_id)
    return {"ok": True, "channel": channel_id,
            "messages": _trim(body.get("messages", []), limit)}


SLACK_READ_CHANNEL_SCHEMA = {
    "description": (
        "Read the most recent messages in a Slack channel. Use this to find the report "
        "you have been asked to act on. Each message carries a `ts` — that timestamp is "
        "what slack_read_thread and slack_reply_in_thread need."
    ),
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "Channel name (#eng-bugs) or id (C0123ABCD)"},
        "limit": {"type": "integer", "default": 20, "description": "How many messages (max 100)"},
    },
    "required": ["channel"],
}


# ── Read a thread ────────────────────────────────────────────────────────────────

async def slack_read_thread(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    channel_id, err = await _resolve_channel(args, args.get("channel", ""))
    if err:
        return {"ok": False, "error": err}
    ts = (args.get("thread_ts") or "").strip()
    if not ts:
        return {"ok": False, "error": "thread_ts is required — it is the `ts` of the "
                                      "message that starts the thread"}
    limit = min(int(args.get("limit", 50) or 50), 200)
    body = await _call("conversations.replies", args,
                       {"channel": channel_id, "ts": ts, "limit": limit}, http_method="GET")
    if not body.get("ok"):
        return body
    messages = _trim(body.get("messages", []), limit)
    await _audit(_PROVIDER, args, "slack_read_thread", target=f"{channel_id}/{ts}")
    return {"ok": True, "channel": channel_id, "thread_ts": ts,
            "messages": messages, "count": len(messages)}


SLACK_READ_THREAD_SCHEMA = {
    "description": (
        "Read every message in one Slack thread, oldest first. The first message is the "
        "one that started it — usually the actual report."
    ),
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "Channel name (#eng-bugs) or id"},
        "thread_ts": {"type": "string", "description": "Timestamp of the thread's parent message"},
        "limit": {"type": "integer", "default": 50, "description": "Max messages (max 200)"},
    },
    "required": ["channel", "thread_ts"],
}


# ── Post ─────────────────────────────────────────────────────────────────────────

async def _post(args: dict, *, thread_ts: str = "") -> dict:
    # Everything that can be judged from the arguments alone is judged first: resolving a
    # channel is a paginated API call, and there is no reason to spend it on a message that
    # was never going to be sent.
    text = (args.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "text is required"}
    # A Slack message cannot be un-sent from a channel of humans, so an unresolved
    # `{{t3.output.url}}` is refused before it is posted rather than apologised for after.
    blanks = _refuse_if_unfilled(text, "this Slack message")
    if blanks:
        return blanks

    channel_id, err = await _resolve_channel(args, args.get("channel", ""))
    if err:
        return {"ok": False, "error": err}

    payload = {"channel": channel_id, "text": text[:38000]}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    body = await _call("chat.postMessage", args, payload)
    if not body.get("ok"):
        await _audit(_PROVIDER, args, "slack_post", target=channel_id, outcome="error")
        return body

    ts = body.get("ts", "")
    url = await _permalink(args, channel_id, ts)
    await _audit(_PROVIDER, args, "slack_post", target=channel_id)
    return {"ok": True, "channel": channel_id, "ts": ts,
            "thread_ts": thread_ts or ts, "url": url, "text": text}


async def thread_read_in_goal(goal_id: str | None, channel_id: str) -> str:
    """The thread this goal opened in `channel_id`, or "" if it never read one.

    Reading a thread is an unambiguous statement of intent: the run went and fetched one
    specific conversation, by timestamp, because that is what it was asked to act on.
    Anything it posts to that channel afterwards belongs in that thread unless it says
    otherwise.

    Deliberately keyed on `slack_read_thread` and not on `slack_read_channel`. Plenty of
    goals legitimately read a channel and then post a new top-level message — "summarise
    this file in #eng-bugs" is one — and refusing those would be a false refusal on a
    perfectly ordinary shape.

    Never raises. An unreadable ledger means the guard cannot judge, and a guard that
    cannot judge must not be the reason a message goes unsent.
    """
    if not goal_id:
        return ""
    try:
        import db
        async with db.get_conn() as conn:
            rows = await (
                await conn.execute(
                    """SELECT tc.result_json FROM tool_calls tc
                         JOIN tasks t ON t.id = tc.task_id
                        WHERE t.goal_id = ? AND tc.tool_name = 'slack_read_thread'
                          AND tc.status = 'SUCCESS'
                     ORDER BY tc.created_at DESC""",
                    (goal_id,),
                )
            ).fetchall()
        for row in rows:
            try:
                body = json.loads(row["result_json"] or "{}")
            except (ValueError, TypeError):
                continue
            if isinstance(body, dict) and body.get("channel") == channel_id:
                return str(body.get("thread_ts") or "")
    except Exception as e:
        logger.debug("thread lookup skipped for %s: %s", goal_id, e)
    return ""


async def slack_post_message(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing

    # Run 5a3e9462 was asked to "reply in the same #eng-bugs thread". It read the thread,
    # got `ts: 1789286027.409169` back, and then called this tool without it — posting a
    # new top-level message into the channel while reporting the task complete. The
    # reporter watching the thread saw nothing.
    #
    # Nothing was missing at the point of the call: the timestamp was in hand. So the
    # schema saying "use slack_reply_in_thread instead" was advice, and advice is not a
    # mechanism. This is the mechanism.
    # Order matters and is asserted by test_a_blank_never_reaches_a_slack_channel: a
    # message carrying an unfilled `{{...}}` is refused before anything is looked up,
    # because there is no reason to spend a paginated channel listing on a message that
    # was never going to be sent. The thread guard resolves a channel, so it goes second.
    text = (args.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "text is required"}
    blanks = _refuse_if_unfilled(text, "this Slack message")
    if blanks:
        return blanks

    if not args.get("new_thread"):
        channel_id, err = await _resolve_channel(args, args.get("channel", ""))
        if err:
            return {"ok": False, "error": err}
        thread_ts = await thread_read_in_goal(args.get("_goal_id"), channel_id)
        if thread_ts:
            return {"ok": False, "error":
                    f"this run already read the thread at {thread_ts} in this channel, so a "
                    f"new top-level message would be answering somewhere the reporter is not "
                    f"looking. Reply in it: slack_reply_in_thread with thread_ts=\"{thread_ts}\". "
                    f"If you genuinely mean to start a separate conversation, pass "
                    f"new_thread=true and say why in the text."}

    return await _post(args)


SLACK_POST_MESSAGE_SCHEMA = {
    "description": (
        "Start a NEW top-level message in a Slack channel. Returns the message `ts` and a "
        "permalink. If this run read a thread in that channel, use slack_reply_in_thread "
        "instead — this tool refuses, because a new message answers where the reporter is "
        "not looking."
    ),
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "Channel name (#eng-bugs) or id"},
        "text": {"type": "string", "description": "Message text. Slack mrkdwn: *bold*, `code`, <url|label>"},
        "new_thread": {
            "type": "boolean",
            "description": ("Set true only when a separate conversation is genuinely "
                            "intended, even though this run read a thread in the channel."),
        },
    },
    "required": ["channel", "text"],
}


async def slack_reply_in_thread(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    thread_ts = (args.get("thread_ts") or "").strip()
    if not thread_ts:
        return {"ok": False, "error": "thread_ts is required — reply into the thread you read"}
    return await _post(args, thread_ts=thread_ts)


SLACK_REPLY_IN_THREAD_SCHEMA = {
    "description": (
        "Reply inside an existing Slack thread. This is how a completed task is reported "
        "back to the person who asked: same thread, links included. Returns a permalink."
    ),
    "type": "object",
    "properties": {
        "channel": {"type": "string", "description": "Channel name (#eng-bugs) or id"},
        "thread_ts": {"type": "string", "description": "Timestamp of the thread's parent message"},
        "text": {"type": "string", "description": "Reply text. Include real URLs for anything you claim to have done."},
    },
    "required": ["channel", "thread_ts", "text"],
}
