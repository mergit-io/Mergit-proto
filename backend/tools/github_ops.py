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
    ref = args.get("ref")
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        # Use specified ref, or repo default branch, falling back to no ref
        effective_ref = ref or repo.default_branch
        try:
            contents = repo.get_contents(path, ref=effective_ref)
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
    ref = args.get("ref")
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        effective_ref = ref or repo.default_branch
        try:
            contents = repo.get_contents(path, ref=effective_ref)
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


# ── Create a brand-new repo and push files ──────────────────────────────────────

@trace("github_create_repo")
async def github_create_repo(args: dict) -> dict:
    """Create a NEW GitHub repo under the authenticated account and commit files into it.
    Used when a goal asks to build something and ship it as its own repository."""
    if not _require_token():
        return _TOKEN_MISSING
    name = args["name"].strip().replace(" ", "-")
    description = args.get("description", "")
    private = args.get("private", True)
    files = args.get("files", [])
    if not files:
        return {"ok": False, "error": "files[] is required — a repo with no code is not a deliverable"}
    try:
        from github import GithubException
        g = _client()
        user = g.get_user()
        try:
            repo = user.create_repo(name=name, description=description,
                                    private=private, auto_init=True)
        except GithubException as e:
            # Name taken — reuse the existing repo if we own it, else suffix it
            try:
                repo = g.get_repo(f"{user.login}/{name}")
            except GithubException:
                import time
                name = f"{name}-{int(time.time())}"
                repo = user.create_repo(name=name, description=description,
                                        private=private, auto_init=True)
        committed = []
        for f in files:
            path, content = f["path"], f["content"]
            try:
                existing = repo.get_contents(path)
                repo.update_file(path, f"Add {path}", content, existing.sha)
            except GithubException:
                repo.create_file(path, f"Add {path}", content)
            committed.append(path)
        return {
            "ok": True,
            "repo": repo.full_name,
            "url": repo.html_url,
            "default_branch": repo.default_branch,
            "files_committed": committed,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_CREATE_REPO_SCHEMA = {
    "description": "Create a NEW GitHub repository under the authenticated account and commit "
                   "files into it. Use this to ship a freshly-built app/project as its own repo. "
                   "Pass files[] with path+content for every file the project needs.",
    "type": "object",
    "properties": {
        "name":        {"type": "string", "description": "Repo name (kebab-case)"},
        "description": {"type": "string", "description": "Short repo description"},
        "private":     {"type": "boolean", "description": "Private repo (default true)"},
        "files": {
            "type": "array",
            "description": "Every file to commit (README, source, tests, etc.)",
            "items": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "required": ["name", "files"],
}


# ── List GitHub Actions workflows ────────────────────────────────────────────────

@trace("github_list_workflows")
async def github_list_workflows(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        # Workflows are YAML files in .github/workflows/
        try:
            contents = repo.get_contents(".github/workflows")
        except Exception:
            return {"ok": True, "repo": repo_name, "workflows": [], "note": "No .github/workflows directory found"}
        if not isinstance(contents, list):
            contents = [contents]
        workflows = []
        for f in contents:
            if f.name.endswith((".yml", ".yaml")):
                raw = f.decoded_content.decode("utf-8", errors="replace")
                workflows.append({"name": f.name, "path": f.path, "content": raw, "sha": f.sha})
        return {"ok": True, "repo": repo_name, "workflows": workflows}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_LIST_WORKFLOWS_SCHEMA = {
    "description": "List all GitHub Actions workflow YAML files in a repository.",
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "Repository in 'owner/repo' format"},
    },
    "required": ["repo"],
}


# ── Get branch protection rules ──────────────────────────────────────────────────

@trace("github_get_branch_protection")
async def github_get_branch_protection(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    branch = args.get("branch")
    try:
        g = _client()
        repo = g.get_repo(repo_name)
        target = branch or repo.default_branch
        b = repo.get_branch(target)
        if not b.protected:
            return {"ok": True, "repo": repo_name, "branch": target, "protected": False, "rules": {}}
        prot = b.get_protection()
        rules = {
            "required_status_checks": None,
            "enforce_admins": prot.enforce_admins,
            "required_pull_request_reviews": None,
            "restrictions": None,
        }
        if prot.required_status_checks:
            rules["required_status_checks"] = {
                "strict": prot.required_status_checks.strict,
                "contexts": list(prot.required_status_checks.contexts),
            }
        if prot.required_pull_request_reviews:
            rev = prot.required_pull_request_reviews
            rules["required_pull_request_reviews"] = {
                "dismiss_stale_reviews": rev.dismiss_stale_reviews,
                "require_code_owner_reviews": rev.require_code_owner_reviews,
                "required_approving_review_count": rev.required_approving_review_count,
            }
        return {"ok": True, "repo": repo_name, "branch": target, "protected": True, "rules": rules}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_GET_BRANCH_PROTECTION_SCHEMA = {
    "description": "Get branch protection rules for a GitHub repository branch.",
    "type": "object",
    "properties": {
        "repo":   {"type": "string", "description": "Repository in 'owner/repo' format"},
        "branch": {"type": "string", "description": "Branch name (default: repo default branch)"},
    },
    "required": ["repo"],
}


# ── Set branch protection rules ──────────────────────────────────────────────────

@trace("github_set_branch_protection")
async def github_set_branch_protection(args: dict) -> dict:
    if not _require_token():
        return _TOKEN_MISSING
    repo_name = args["repo"]
    branch = args.get("branch")
    rules = args.get("rules", {})
    try:
        from github import GithubException
        g = _client()
        repo = g.get_repo(repo_name)
        target = branch or repo.default_branch
        b = repo.get_branch(target)

        # Build kwargs for edit_protection
        kwargs: dict = {}
        if "required_status_checks" in rules:
            rsc = rules["required_status_checks"]
            if rsc is None:
                kwargs["strict"] = False
                kwargs["contexts"] = []
            else:
                kwargs["strict"] = rsc.get("strict", False)
                kwargs["contexts"] = rsc.get("contexts", [])
        if "enforce_admins" in rules:
            kwargs["enforce_admins"] = rules["enforce_admins"]
        if "required_pull_request_reviews" in rules:
            rev = rules["required_pull_request_reviews"]
            if rev:
                kwargs["dismiss_stale_reviews"] = rev.get("dismiss_stale_reviews", False)
                kwargs["require_code_owner_reviews"] = rev.get("require_code_owner_reviews", False)
                kwargs["required_approving_review_count"] = rev.get("required_approving_review_count", 1)
        if "restrictions" in rules:
            kwargs["user_push_restrictions"] = []
            kwargs["team_push_restrictions"] = []

        b.edit_protection(**kwargs)
        return {"ok": True, "repo": repo_name, "branch": target, "applied_rules": rules}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_SET_BRANCH_PROTECTION_SCHEMA = {
    "description": "Set or update branch protection rules for a GitHub repository branch.",
    "type": "object",
    "properties": {
        "repo":   {"type": "string", "description": "Repository in 'owner/repo' format"},
        "branch": {"type": "string", "description": "Branch name (default: repo default branch)"},
        "rules": {
            "type": "object",
            "description": "Protection rules to apply",
            "properties": {
                "required_status_checks": {
                    "type": ["object", "null"],
                    "properties": {
                        "strict": {"type": "boolean"},
                        "contexts": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "enforce_admins": {"type": "boolean"},
                "required_pull_request_reviews": {
                    "type": ["object", "null"],
                    "properties": {
                        "dismiss_stale_reviews": {"type": "boolean"},
                        "require_code_owner_reviews": {"type": "boolean"},
                        "required_approving_review_count": {"type": "integer"},
                    },
                },
            },
        },
    },
    "required": ["repo", "rules"],
}
