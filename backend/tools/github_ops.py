"""
GitHub read/comment operations for agents.

Complements github_pr.py (which handles PR creation).
These tools let agents read repo contents, post comments, and get issue details.
"""
import base64
import os

from tools.credential_request import WAITING_CREDENTIAL_SENTINEL
from tracing import trace

_TOKEN_MISSING = {
    WAITING_CREDENTIAL_SENTINEL: True,
    "credential": "GITHUB_TOKEN",
    "provider": "github",
    "message": "GitHub personal access token required",
}


def _client():
    from github import Github
    return Github(os.environ.get("GITHUB_TOKEN", ""))


def _require_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN", "") or None


# ── Read file ────────────────────────────────────────────────────────────────────

@trace("github_read_file")
async def github_read_file(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    path = args["path"]
    ref = args.get("ref", "main")
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        # Try the given ref first, fall back to default branch
        try:
            contents = repo.get_contents(path, ref=ref)
        except Exception:
            contents = repo.get_contents(path)
        if isinstance(contents, list):
            return {"ok": False, "error": f"{path} is a directory — use github_list_dir instead"}
        raw = contents.decoded_content
        text = raw.decode("utf-8", errors="replace")
        return {"ok": True, "path": path, "content": text, "size": len(text), "sha": contents.sha}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_READ_FILE_SCHEMA = {
    "description": "Read the content of a file from a GitHub repository.",
    "type": "object",
    "properties": {
        "repo":  {"type": "string", "description": "Repository in 'owner/repo' format"},
        "path":  {"type": "string", "description": "File path within the repo (e.g. 'src/main.py')"},
        "ref":   {"type": "string", "description": "Branch, tag, or commit SHA (default: main)"},
    },
    "required": ["repo", "path"],
}


# ── List directory ───────────────────────────────────────────────────────────────

@trace("github_list_dir")
async def github_list_dir(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    path = args.get("path", "")
    ref = args.get("ref", "main")
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        try:
            contents = repo.get_contents(path, ref=ref)
        except Exception:
            contents = repo.get_contents(path)
        if not isinstance(contents, list):
            return {"ok": False, "error": f"{path} is a file — use github_read_file instead"}
        items = [
            {"name": c.name, "path": c.path, "type": c.type, "size": c.size}
            for c in contents
        ]
        return {"ok": True, "path": path or "/", "items": items}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_LIST_DIR_SCHEMA = {
    "description": "List files and directories in a GitHub repository path.",
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "Repository in 'owner/repo' format"},
        "path": {"type": "string", "description": "Directory path (empty string for root)"},
        "ref":  {"type": "string", "description": "Branch, tag, or commit SHA (default: main)"},
    },
    "required": ["repo"],
}


# ── Get issue ────────────────────────────────────────────────────────────────────

@trace("github_get_issue")
async def github_get_issue(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    issue_number = int(args["issue_number"])
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        comments = []
        for c in issue.get_comments():
            comments.append({"author": c.user.login, "body": c.body, "created_at": str(c.created_at)})
        return {
            "ok": True,
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "state": issue.state,
            "author": issue.user.login,
            "labels": [l.name for l in issue.labels],
            "url": issue.html_url,
            "comments": comments,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_GET_ISSUE_SCHEMA = {
    "description": "Get full details of a GitHub issue including body and comments.",
    "type": "object",
    "properties": {
        "repo":         {"type": "string", "description": "Repository in 'owner/repo' format"},
        "issue_number": {"type": ["integer", "string"], "description": "Issue number"},
    },
    "required": ["repo", "issue_number"],
}


# ── Post comment ─────────────────────────────────────────────────────────────────

@trace("github_post_comment")
async def github_post_comment(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    issue_number = int(args["issue_number"])
    body = args["body"]
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        comment = issue.create_comment(body)
        return {"ok": True, "comment_id": comment.id, "url": comment.html_url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_POST_COMMENT_SCHEMA = {
    "description": "Post a comment on a GitHub issue or pull request.",
    "type": "object",
    "properties": {
        "repo":         {"type": "string", "description": "Repository in 'owner/repo' format"},
        "issue_number": {"type": ["integer", "string"], "description": "Issue or PR number"},
        "body":         {"type": "string", "description": "Comment body (markdown supported)"},
    },
    "required": ["repo", "issue_number", "body"],
}


# ── Search code ──────────────────────────────────────────────────────────────────

@trace("github_search_code")
async def github_search_code(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    query = args["query"]
    try:
        g = _client()
        full_query = f"{query} repo:{repo_name}"
        results = g.search_code(full_query)
        items = []
        for r in results[:10]:
            items.append({"path": r.path, "name": r.name, "url": r.html_url})
        return {"ok": True, "query": query, "total": results.totalCount, "items": items}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_SEARCH_CODE_SCHEMA = {
    "description": "Search for code within a GitHub repository.",
    "type": "object",
    "properties": {
        "repo":  {"type": "string", "description": "Repository in 'owner/repo' format"},
        "query": {"type": "string", "description": "Search query (e.g. 'function calculate_tax')"},
    },
    "required": ["repo", "query"],
}
