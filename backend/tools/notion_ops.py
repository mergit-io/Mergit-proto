"""Notion page operations for agents.

Notion is where the *narrative* lives — the incident note, the postmortem, the record a
human reads next week when nobody remembers which PR fixed what. GitHub holds the diff and
Linear holds the status; neither of them holds the explanation.

What is handled here, and why each one is not left to the model:

* **Ids are extracted from URLs.** A human copies `https://www.notion.so/Bugs-24f1a…`.
  The API wants `24f1a…` with dashes. Every id argument goes through `_page_id`, so a
  pasted URL works and a bare id still works.
* **A parent is required, and defaulted.** Notion refuses a workspace-root page from an
  internal integration, so "create a page" with no parent always fails. `NOTION_PARENT_PAGE_ID`
  supplies one, and the error names the setting when it is absent instead of returning
  Notion's `validation_error`.
* **Markdown is converted to blocks.** The API takes a typed block tree, not text. Without
  this an agent's carefully structured note arrives as one 4000-character paragraph, and
  the 2000-character-per-text-node limit silently truncates the rest.
* **Every page comes back with a `url`.** Same contract as the GitHub and Linear tools:
  `agent_runner._claimed_without_artifact` rejects a claim with no address, and that only
  works if a real action produces one.
"""
import logging
import os
import re

import httpx

from config import settings
from tools.placeholders import refuse_if_unfilled as _refuse_if_unfilled
from tools.service_client import audit as _audit
from tools.service_client import credential_check as _credential_check
from tools.service_client import token as _token

logger = logging.getLogger(__name__)

_API = "https://api.notion.com/v1"
_PROVIDER = "notion"
_TIMEOUT = 25

#: Pinned rather than "latest": Notion's API is versioned by date and a newer version has
#: already renamed database parents once. An integration that silently follows the newest
#: version is an integration that breaks on a day nobody deployed anything.
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2026-03-11")

#: 32 hex characters, dashed or not — how every Notion id appears, including inside a URL.
_ID_IN_URL = re.compile(r"([0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)

#: Notion rejects any single rich-text node longer than this.
_TEXT_LIMIT = 2000


def _page_id(value: str) -> str:
    """A bare Notion id from an id, a dashed id, or a page URL. "" if there is none."""
    # The pattern matches a dashed id or a bare one, so a raw id, a dashed id and a page
    # URL (whose slug also contains dashes) all resolve through the same single search.
    m = _ID_IN_URL.search(value or "")
    return m.group(1).replace("-", "") if m else ""


def _rich(text: str) -> list[dict]:
    """One line of text as Notion rich-text nodes, split at the API's length limit."""
    text = text or ""
    if not text:
        return []
    return [{"type": "text", "text": {"content": text[i:i + _TEXT_LIMIT]}}
            for i in range(0, min(len(text), _TEXT_LIMIT * 25), _TEXT_LIMIT)]


def markdown_to_blocks(md: str) -> list[dict]:
    """A pragmatic Markdown → Notion block conversion.

    Deliberately small: headings, bullets, numbered items, fenced code, dividers and
    paragraphs. That is the whole vocabulary of an incident note. Anything richer would be
    a Markdown parser, and a Markdown parser is not what makes this demo work.
    """
    blocks: list[dict] = []
    lines = (md or "").split("\n")
    i = 0
    while i < len(lines) and len(blocks) < 95:  # Notion caps children per request at 100
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            lang = stripped[3:].strip() or "plain text"
            i += 1
            body: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence
            blocks.append({"object": "block", "type": "code", "code": {
                "rich_text": _rich("\n".join(body)),
                "language": lang if lang in _NOTION_LANGUAGES else "plain text"}})
            continue

        if not stripped:
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif stripped.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": _rich(stripped[4:])}})
        elif stripped.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": _rich(stripped[3:])}})
        elif stripped.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": _rich(stripped[2:])}})
        elif stripped.startswith(("- ", "* ")):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": _rich(stripped[2:])}})
        elif re.match(r"^\d+\.\s", stripped):
            blocks.append({"object": "block", "type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": _rich(re.sub(r"^\d+\.\s", "", stripped))}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": _rich(stripped)}})
        i += 1
    return blocks


#: Notion validates `code.language` against a closed list and 400s on anything else.
_NOTION_LANGUAGES = {
    "bash", "c", "c++", "c#", "css", "diff", "docker", "go", "graphql", "html", "java",
    "javascript", "json", "kotlin", "markdown", "plain text", "python", "ruby", "rust",
    "shell", "sql", "swift", "typescript", "yaml",
}


async def _call(args: dict, method: str, path: str, payload: dict | None = None) -> dict:
    """One Notion API call. Returns the body, or `{"ok": False, "error": ...}`."""
    tok = await _token(_PROVIDER, args)
    headers = {
        "Authorization": f"Bearer {tok}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(method, f"{_API}{path}", headers=headers, json=payload)
    except Exception as e:
        return {"ok": False, "error": f"Notion request failed: {e}"}

    try:
        body = resp.json()
    except Exception:
        return {"ok": False, "error": f"Notion returned non-JSON (HTTP {resp.status_code})"}

    if resp.status_code >= 400:
        code = body.get("code", "")
        message = body.get("message", "")[:500]
        # The single most common Notion integration failure, and the one whose own error
        # message does not say what to do about it.
        if code == "object_not_found":
            message += (" — the integration has not been given access to this page. Open "
                        "the page in Notion, ••• menu → Connections → add the Mergit "
                        "integration, then retry.")
        return {"ok": False, "error": f"Notion {code or resp.status_code}: {message}"}
    return {"ok": True, **body}


def _title_of(page: dict) -> str:
    """The title text of a page object, whatever the title property happens to be called."""
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    return ""


# ── Search ───────────────────────────────────────────────────────────────────────

async def notion_search(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    payload: dict = {"page_size": min(int(args.get("limit", 10) or 10), 25)}
    if args.get("query"):
        payload["query"] = args["query"]
    res = await _call(args, "POST", "/search", payload)
    if not res.get("ok"):
        return res
    results = []
    for obj in res.get("results", []):
        results.append({
            "id": obj.get("id", "").replace("-", ""),
            "object": obj.get("object"),
            "title": _title_of(obj),
            "url": obj.get("url", ""),
        })
    await _audit(_PROVIDER, args, "notion_search")
    return {"ok": True, "results": results, "count": len(results)}


NOTION_SEARCH_SCHEMA = {
    "description": (
        "Search the Notion pages and databases the integration can see. Use it to find the "
        "id of a parent page. Results are limited to what has been explicitly shared with "
        "the integration — an empty result usually means nothing was shared, not that "
        "nothing exists."
    ),
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Text to match in page titles"},
        "limit": {"type": "integer", "default": 10},
    },
    "required": [],
}


# ── Create ───────────────────────────────────────────────────────────────────────

async def notion_create_page(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    title = (args.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "title is required"}
    blanks = _refuse_if_unfilled(f"{title}\n{args.get('content') or ''}", "this Notion page")
    if blanks:
        return blanks

    default_raw = (os.environ.get("NOTION_PARENT_PAGE_ID", "")
                   or settings.notion_parent_page_id)
    supplied = (args.get("parent_page_id") or "").strip()

    # A supplied value that contains no page id is not a parent — it is a model repeating
    # something it read. Run dcaac2eb passed the literal string "NOTION_PARENT_PAGE_ID",
    # copied out of this tool's own schema description, and because that string is truthy
    # the configured default never got a chance. Anything unusable falls through to the
    # default rather than failing the call, and only a missing default is an error.
    parent = _page_id(supplied) or _page_id(default_raw)
    if not parent:
        detail = (f" The value passed as parent_page_id ({supplied!r}) contains no Notion "
                  f"page id." if supplied else "")
        return {"ok": False, "error": (
            "no Notion parent page. An internal integration cannot create a workspace-root "
            "page, so one is required: pass parent_page_id as a page id or page URL, or set "
            "NOTION_PARENT_PAGE_ID on the deployment." + detail)}

    payload = {
        "parent": {"type": "page_id", "page_id": parent},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title[:200]}}]}},
        "children": markdown_to_blocks(args.get("content", "")),
    }
    res = await _call(args, "POST", "/pages", payload)
    if not res.get("ok"):
        await _audit(_PROVIDER, args, "notion_create_page", target=parent, outcome="error")
        return res
    page_id = res.get("id", "").replace("-", "")
    await _audit(_PROVIDER, args, "notion_create_page", target=page_id)
    return {"ok": True, "id": page_id, "url": res.get("url", ""), "title": title}


NOTION_CREATE_PAGE_SCHEMA = {
    "description": (
        "Create a Notion page under a parent page and return its URL. Use it to file the "
        "written record of what was done — what broke, why, what changed, and links to the "
        "PR and the ticket. `content` is Markdown: headings, bullets, numbered lists, "
        "fenced code and --- dividers are converted to real Notion blocks."
    ),
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Page title"},
        "content": {"type": "string", "description": "Markdown body. Include real URLs, never placeholders."},
        # Deliberately does not name the environment variable. It used to, and a model
        # passed that name as the value — reading the description as an instruction.
        "parent_page_id": {"type": "string", "description": (
            "Optional. A Notion page id or page URL to create this page under. Omit it "
            "and the workspace's configured parent page is used — that is the normal "
            "case, so only pass this when you have a specific page id in hand.")},
    },
    "required": ["title"],
}


# ── Append ───────────────────────────────────────────────────────────────────────

async def notion_append_blocks(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    page = _page_id(args.get("page_id", ""))
    if not page:
        return {"ok": False, "error": "page_id is required (id or Notion URL)"}
    blanks = _refuse_if_unfilled(args.get("content") or "", "this Notion content")
    if blanks:
        return blanks
    blocks = markdown_to_blocks(args.get("content", ""))
    if not blocks:
        return {"ok": False, "error": "content is empty — nothing to append"}
    res = await _call(args, "PATCH", f"/blocks/{page}/children", {"children": blocks})
    if not res.get("ok"):
        await _audit(_PROVIDER, args, "notion_append_blocks", target=page, outcome="error")
        return res
    await _audit(_PROVIDER, args, "notion_append_blocks", target=page)
    return {"ok": True, "page_id": page, "blocks_added": len(blocks)}


NOTION_APPEND_BLOCKS_SCHEMA = {
    "description": "Append Markdown content to the end of an existing Notion page.",
    "type": "object",
    "properties": {
        "page_id": {"type": "string", "description": "Page id or Notion URL"},
        "content": {"type": "string", "description": "Markdown to append"},
    },
    "required": ["page_id", "content"],
}


# ── Read back ────────────────────────────────────────────────────────────────────

async def notion_get_page(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    page = _page_id(args.get("page_id", ""))
    if not page:
        return {"ok": False, "error": "page_id is required (id or Notion URL)"}

    meta = await _call(args, "GET", f"/pages/{page}")
    if not meta.get("ok"):
        return meta

    text_lines: list[str] = []
    if args.get("include_content", True):
        blocks = await _call(args, "GET", f"/blocks/{page}/children?page_size=100")
        if blocks.get("ok"):
            for b in blocks.get("results", []):
                inner = b.get(b.get("type", ""), {})
                rich = inner.get("rich_text") if isinstance(inner, dict) else None
                if rich:
                    text_lines.append("".join(t.get("plain_text", "") for t in rich))

    await _audit(_PROVIDER, args, "notion_get_page", target=page)
    return {"ok": True, "id": page, "url": meta.get("url", ""),
            "title": _title_of(meta), "content": "\n".join(text_lines)[:8000],
            "archived": meta.get("archived", False)}


NOTION_GET_PAGE_SCHEMA = {
    "description": (
        "Read a Notion page back — title, URL and its text content. Use this to confirm a "
        "page you created really exists and says what you think it says."
    ),
    "type": "object",
    "properties": {
        "page_id": {"type": "string", "description": "Page id or Notion URL"},
        "include_content": {"type": "boolean", "default": True},
    },
    "required": ["page_id"],
}
