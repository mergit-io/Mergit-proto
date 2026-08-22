"""
GitHub read/comment operations for agents.

Complements github_pr.py (which handles PR creation).
These tools let agents read repo contents, post comments, and get issue details.
"""
import logging
import re

from tools.github_client import TOKEN_MISSING as _TOKEN_MISSING
from tools.github_client import audit as _audit
from tools.github_client import client as _client
from tools.github_client import credential_check as _credential_check
from tools.github_client import github_token

logger = logging.getLogger(__name__)


def _require_token() -> str | None:
    """The shared deployment token, if there is one.

    Retained for the single-tenant fallback and for callers that only need to know whether
    *any* GitHub credential exists. It is no longer the authorisation check: that is
    `_credential_check(args)`, which resolves the goal's owner and can park the task with
    a per-user resume key rather than a global one.
    """
    return github_token() or None


#: A value that was never filled in. `{{t3.output.pr_number}}` is an interpolation
#: template that outlived its task; `#<pr_number>` is the model writing its own blank.
#:
#: The angle-bracket form requires snake_case with an underscore, which is what a blank
#: looks like and what ordinary comment text does not: `Vec<String>` and `<div>` have no
#: underscore, and <https://example.com> is not an identifier. `<number>` slips through as
#: the price of that — a wrong refusal costs a real comment.
#:
#: Matching is case-insensitive. It was lowercase-only, and on 2026-08-22 an integrator
#: posted `Fixed in PR #<PR_NUMBER>` on issue #25 of the sandbox repo: the same blank this
#: guard exists to stop, written in the casing it did not cover. A placeholder is a
#: placeholder whichever way the model shifts it.
_PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}|<[a-z][a-z0-9]*_[a-z0-9_]*>", re.I)


def _unfilled_placeholders(body: str) -> list[str]:
    return _PLACEHOLDER.findall(body or "")


# ── Read file ────────────────────────────────────────────────────────────────────

async def github_read_file(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    path = args["path"]
    ref = args.get("ref")
    try:
        g = await _client(args)
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

async def github_list_dir(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    path = args.get("path", "")
    ref = args.get("ref")
    try:
        g = await _client(args)
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

async def github_get_issue(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    issue_number = int(args["issue_number"])
    try:
        g = await _client(args)
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

async def github_post_comment(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    issue_number = int(args["issue_number"])
    body = args["body"]
    # A comment is published the moment it is posted, usually on someone else's
    # repository. An integrator that has not created the pull request yet writes the blank
    # it was given and posts it, so the thread gets "see PR #<pr_number>" followed by a
    # correction — twice the noise, and the first one cannot be unsent.
    unfilled = _unfilled_placeholders(body)
    if unfilled:
        logger.warning("Refusing comment on %s#%s — unfilled placeholders: %s",
                       repo_name, issue_number, unfilled)
        return {"ok": False, "error": (
            f"the comment still contains {', '.join(unfilled)}, which is a placeholder "
            "rather than a value. Get the real value first — if you are referring to a "
            "pull request you have not created yet, create it and use the number it "
            "returns — then post the comment once, filled in.")}
    try:
        g = await _client(args)
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

async def github_search_code(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    query = args["query"]
    try:
        g = await _client(args)
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

async def github_create_repo(args: dict) -> dict:
    """Create a NEW GitHub repo under the authenticated account and commit files into it.
    Used when a goal asks to build something and ship it as its own repository."""
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    name = args["name"].strip().replace(" ", "-")
    description = args.get("description", "")
    private = args.get("private", True)
    files = args.get("files", [])
    if not files:
        return {"ok": False, "error": "files[] is required — a repo with no code is not a deliverable"}
    try:
        from github import GithubException
        g = await _client(args)
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

async def github_list_workflows(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    try:
        g = await _client(args)
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

async def github_get_branch_protection(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    branch = args.get("branch")
    try:
        g = await _client(args)
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

async def github_set_branch_protection(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    branch = args.get("branch")
    rules = args.get("rules", {})
    try:
        from github import GithubException
        g = await _client(args)
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


# ── Create issue ─────────────────────────────────────────────────────────────────

async def github_create_issue(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    title = args["title"]
    body = args.get("body", "")
    labels = args.get("labels", []) or []
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        issue = repo.create_issue(title=title, body=body, labels=labels)
        return {"ok": True, "number": issue.number, "url": issue.html_url,
                "title": issue.title, "state": issue.state}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_CREATE_ISSUE_SCHEMA = {
    "description": "Open a new issue on a GitHub repository.",
    "type": "object",
    "properties": {
        "repo":   {"type": "string", "description": "Repository in 'owner/repo' format"},
        "title":  {"type": "string", "description": "Issue title"},
        "body":   {"type": "string", "description": "Issue body (markdown supported)"},
        "labels": {"type": "array", "items": {"type": "string"},
                   "description": "Labels to apply (must already exist on the repo)"},
    },
    "required": ["repo", "title"],
}


# ── Close issue ──────────────────────────────────────────────────────────────────

async def github_close_issue(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    issue_number = int(args["issue_number"])
    comment = args.get("comment")
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        if comment:
            issue.create_comment(comment)
        # state_reason distinguishes "fixed" from "won't do" in the GitHub UI.
        issue.edit(state="closed", state_reason=args.get("state_reason", "completed"))
        return {"ok": True, "number": issue_number, "state": "closed", "url": issue.html_url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_CLOSE_ISSUE_SCHEMA = {
    "description": "Close a GitHub issue, optionally leaving a closing comment first.",
    "type": "object",
    "properties": {
        "repo":         {"type": "string", "description": "Repository in 'owner/repo' format"},
        "issue_number": {"type": ["integer", "string"], "description": "Issue number"},
        "comment":      {"type": "string", "description": "Comment to post before closing"},
        "state_reason": {"type": "string", "enum": ["completed", "not_planned"],
                         "description": "Why it is being closed (default: completed)"},
    },
    "required": ["repo", "issue_number"],
}


# ── Add labels ───────────────────────────────────────────────────────────────────

async def github_add_labels(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    issue_number = int(args["issue_number"])
    labels = args["labels"]
    if isinstance(labels, str):
        labels = [labels]
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        # A label that does not exist yet is created rather than failing the whole call.
        existing = {l.name for l in repo.get_labels()}
        for name in labels:
            if name not in existing:
                try:
                    repo.create_label(name=name, color="ededed")
                except Exception:
                    pass
        issue.add_to_labels(*labels)
        return {"ok": True, "number": issue_number,
                "labels": [l.name for l in issue.get_labels()]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_ADD_LABELS_SCHEMA = {
    "description": "Add labels to a GitHub issue or pull request. Labels that do not "
                   "exist on the repo yet are created automatically.",
    "type": "object",
    "properties": {
        "repo":         {"type": "string", "description": "Repository in 'owner/repo' format"},
        "issue_number": {"type": ["integer", "string"], "description": "Issue or PR number"},
        "labels":       {"type": "array", "items": {"type": "string"},
                         "description": "Label names to add"},
    },
    "required": ["repo", "issue_number", "labels"],
}


# ── Pull request: read ───────────────────────────────────────────────────────────

def _review_summary(pr) -> dict:
    """Latest review verdict per reviewer — GitHub keeps every review, only the last counts."""
    latest: dict[str, str] = {}
    try:
        for r in pr.get_reviews():
            if r.state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
                latest[r.user.login] = r.state
    except Exception:
        return {"approved_by": [], "changes_requested_by": [], "readable": False}
    return {
        "approved_by": [u for u, s in latest.items() if s == "APPROVED"],
        "changes_requested_by": [u for u, s in latest.items() if s == "CHANGES_REQUESTED"],
        "readable": True,
    }


def _check_summary(repo, pr) -> dict:
    """Check-run conclusions on the PR head, so a refusal can name the failing job."""
    try:
        runs = repo.get_commit(pr.head.sha).get_check_runs()
        items = [{"name": c.name, "status": c.status, "conclusion": c.conclusion} for c in runs]
    except Exception:
        return {"total": 0, "failing": [], "pending": [], "readable": False}
    failing = [c["name"] for c in items
               if c["conclusion"] in ("failure", "timed_out", "cancelled", "action_required")]
    pending = [c["name"] for c in items if c["status"] != "completed"]
    return {"total": len(items), "failing": failing, "pending": pending,
            "runs": items, "readable": True}


def _pr_payload(repo, pr, with_checks: bool = True) -> dict:
    payload = {
        "number": pr.number,
        "title": pr.title,
        "body": pr.body or "",
        "state": pr.state,
        "draft": pr.draft,
        "merged": pr.merged,
        "mergeable": pr.mergeable,
        "mergeable_state": pr.mergeable_state,
        "author": pr.user.login if pr.user else None,
        "head": pr.head.ref,
        "base": pr.base.ref,
        "head_sha": pr.head.sha,
        "commits": pr.commits,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "changed_files": pr.changed_files,
        "labels": [l.name for l in pr.labels],
        "url": pr.html_url,
    }
    if with_checks:
        payload["reviews"] = _review_summary(pr)
        payload["checks"] = _check_summary(repo, pr)
    return payload


async def github_get_pr(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    pr_number = int(args["pr_number"])
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        return {"ok": True, **_pr_payload(repo, pr)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_GET_PR_SCHEMA = {
    "description": "Get full state of a pull request: title, body, branches, review verdicts, "
                   "CI check results, mergeability and merge-blocking reasons.",
    "type": "object",
    "properties": {
        "repo":      {"type": "string", "description": "Repository in 'owner/repo' format"},
        "pr_number": {"type": ["integer", "string"], "description": "Pull request number"},
    },
    "required": ["repo", "pr_number"],
}


async def github_list_prs(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    state = args.get("state", "open")
    limit = int(args.get("limit", 20))
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        prs = repo.get_pulls(state=state, sort="updated", direction="desc")
        items = []
        for pr in prs[:limit]:
            items.append({
                "number": pr.number, "title": pr.title, "state": pr.state,
                "draft": pr.draft, "author": pr.user.login if pr.user else None,
                "head": pr.head.ref, "base": pr.base.ref, "url": pr.html_url,
            })
        return {"ok": True, "repo": repo_name, "state": state, "count": len(items), "items": items}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_LIST_PRS_SCHEMA = {
    "description": "List pull requests on a repository, most recently updated first.",
    "type": "object",
    "properties": {
        "repo":  {"type": "string", "description": "Repository in 'owner/repo' format"},
        "state": {"type": "string", "enum": ["open", "closed", "all"],
                  "description": "Which PRs to list (default: open)"},
        "limit": {"type": ["integer", "string"], "description": "Max results (default 20)"},
    },
    "required": ["repo"],
}


# ── Pull request: the actual diff ────────────────────────────────────────────────

_MAX_PATCH_CHARS = 12000   # a whole diff has to survive the model's context window
_MAX_FILES = 60


async def github_get_pr_files(args: dict) -> dict:
    """The changed files and their unified diffs.

    Without this a 'review this PR' goal has no way to see the code it is reviewing,
    so the review is written from the PR title alone.
    """
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    pr_number = int(args["pr_number"])
    include_patch = args.get("include_patch", True)
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        files, budget, truncated_files = [], _MAX_PATCH_CHARS, []
        all_files = list(pr.get_files())
        for f in all_files[:_MAX_FILES]:
            entry = {
                "path": f.filename, "status": f.status,
                "additions": f.additions, "deletions": f.deletions, "changes": f.changes,
            }
            if f.previous_filename:
                entry["previous_path"] = f.previous_filename
            if include_patch:
                patch = f.patch or ""          # empty for binary files
                if len(patch) > budget:
                    # Charge the budget for the content kept, never for the marker, and never
                    # let it go negative: `patch[:-19]` slices from the END of the string, so
                    # one negative budget hands the NEXT file back all but intact and the cap
                    # stops holding from the first truncation onwards.
                    patch = patch[:budget] + "\n… [diff truncated]"
                    truncated_files.append(f.filename)
                    budget = 0
                else:
                    budget -= len(patch)
                entry["patch"] = patch
            files.append(entry)
        return {
            "ok": True, "repo": repo_name, "pr_number": pr_number,
            "base": pr.base.ref, "head": pr.head.ref,
            "total_changed_files": len(all_files),
            "returned_files": len(files),
            "files_omitted": max(0, len(all_files) - len(files)),
            "patches_truncated": truncated_files,
            "files": files,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_GET_PR_FILES_SCHEMA = {
    "description": "Get the changed files and unified diffs of a pull request. Use this "
                   "BEFORE reviewing a PR — it is the only way to see the actual code change.",
    "type": "object",
    "properties": {
        "repo":          {"type": "string", "description": "Repository in 'owner/repo' format"},
        "pr_number":     {"type": ["integer", "string"], "description": "Pull request number"},
        "include_patch": {"type": "boolean", "description": "Include unified diffs (default true)"},
    },
    "required": ["repo", "pr_number"],
}


# ── Pull request: review, reviewers, edit ────────────────────────────────────────

async def github_review_pr(args: dict) -> dict:
    """Submit a formal review (APPROVE / REQUEST_CHANGES / COMMENT), not a plain comment."""
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    pr_number = int(args["pr_number"])
    body = args["body"]
    event = (args.get("event") or "COMMENT").upper()
    if event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
        return {"ok": False, "error": f"event must be APPROVE, REQUEST_CHANGES or COMMENT, got {event!r}"}
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        try:
            review = pr.create_review(body=body, event=event)
            downgraded = False
        except Exception as e:
            # GitHub forbids approving or requesting changes on your own PR. Falling back
            # to a plain COMMENT review keeps the feedback, and says that it happened.
            if event == "COMMENT" or "own pull request" not in str(e).lower():
                raise
            review = pr.create_review(body=body, event="COMMENT")
            downgraded = True
        return {"ok": True, "review_id": review.id, "state": review.state,
                "requested_event": event, "event_downgraded": downgraded,
                "reason": "cannot review your own pull request" if downgraded else None,
                "url": pr.html_url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_REVIEW_PR_SCHEMA = {
    "description": "Submit a formal pull request review. Read the diff with github_get_pr_files "
                   "first — never review a PR you have not read. APPROVE and REQUEST_CHANGES are "
                   "rejected by GitHub on your own PR and fall back to a COMMENT review.",
    "type": "object",
    "properties": {
        "repo":      {"type": "string", "description": "Repository in 'owner/repo' format"},
        "pr_number": {"type": ["integer", "string"], "description": "Pull request number"},
        "body":      {"type": "string", "description": "Review text (markdown)"},
        "event":     {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                      "description": "Review verdict (default COMMENT)"},
    },
    "required": ["repo", "pr_number", "body"],
}


async def github_request_review(args: dict) -> dict:
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    pr_number = int(args["pr_number"])
    reviewers = args.get("reviewers", []) or []
    team_reviewers = args.get("team_reviewers", []) or []
    if isinstance(reviewers, str):
        reviewers = [reviewers]
    if not reviewers and not team_reviewers:
        return {"ok": False, "error": "reviewers or team_reviewers is required"}
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        kwargs = {}
        if reviewers:
            kwargs["reviewers"] = reviewers
        if team_reviewers:
            kwargs["team_reviewers"] = team_reviewers
        pr.create_review_request(**kwargs)
        return {"ok": True, "pr_number": pr_number,
                "requested": reviewers + team_reviewers, "url": pr.html_url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_REQUEST_REVIEW_SCHEMA = {
    "description": "Request review on a pull request from users or teams. GitHub rejects "
                   "requesting a review from the PR author.",
    "type": "object",
    "properties": {
        "repo":           {"type": "string", "description": "Repository in 'owner/repo' format"},
        "pr_number":      {"type": ["integer", "string"], "description": "Pull request number"},
        "reviewers":      {"type": "array", "items": {"type": "string"},
                           "description": "GitHub usernames"},
        "team_reviewers": {"type": "array", "items": {"type": "string"},
                           "description": "Org team slugs"},
    },
    "required": ["repo", "pr_number"],
}


async def github_update_pr(args: dict) -> dict:
    """Edit an open PR: title, body, base branch, draft/ready, or close it."""
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    repo_name = args["repo"]
    pr_number = int(args["pr_number"])
    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        edits = {}
        for key in ("title", "body", "state"):
            if args.get(key) is not None:
                edits[key] = args[key]
        if args.get("base_branch"):
            edits["base"] = args["base_branch"]
        if edits:
            pr.edit(**edits)
        if args.get("ready_for_review") is True and pr.draft:
            pr.mark_ready_for_review()
        pr = repo.get_pull(pr_number)
        return {"ok": True, "number": pr.number, "title": pr.title, "state": pr.state,
                "draft": pr.draft, "base": pr.base.ref, "url": pr.html_url,
                "updated": sorted(edits.keys())}
    except Exception as e:
        return {"ok": False, "error": str(e)}


GITHUB_UPDATE_PR_SCHEMA = {
    "description": "Update an existing pull request — title, body, base branch, close it, "
                   "or mark a draft ready for review.",
    "type": "object",
    "properties": {
        "repo":             {"type": "string", "description": "Repository in 'owner/repo' format"},
        "pr_number":        {"type": ["integer", "string"], "description": "Pull request number"},
        "title":            {"type": "string", "description": "New title"},
        "body":             {"type": "string", "description": "New body (markdown)"},
        "base_branch":      {"type": "string", "description": "Retarget the PR at this base branch"},
        "state":            {"type": "string", "enum": ["open", "closed"],
                             "description": "Reopen or close the PR"},
        "ready_for_review": {"type": "boolean", "description": "Flip a draft PR to ready"},
    },
    "required": ["repo", "pr_number"],
}


# ── Pull request: merge ──────────────────────────────────────────────────────────

# Merging is the one GitHub action an agent cannot walk back, so it is gated rather
# than attempted. GitHub folds conflicts, required reviews and required checks into
# a single `mergeable_state`; only these two values mean "nothing objects".
#   clean     — mergeable, checks green, no blocking review
#   has_hooks — same, on an installation with pre-receive hooks
_MERGE_ALLOWED_STATES = {"clean", "has_hooks"}

_MERGE_REFUSAL_REASON = {
    "dirty":    "the branch has merge conflicts with the base",
    "blocked":  "a required status check or a required review is not satisfied",
    "unstable": "at least one CI check is failing or still running",
    "behind":   "the branch is behind the base and the repo requires branches to be up to date",
    "draft":    "the pull request is still a draft",
    "unknown":  "GitHub had not finished computing mergeability",
}


async def github_merge_pr(args: dict) -> dict:
    """Merge a pull request, but only when nothing objects to it.

    Refusing returns ok=False with the specific blocker rather than forcing the merge,
    so the agent reports an accurate outcome instead of claiming a merge that GitHub
    would have rejected — or worse, landing a red branch.
    """
    _missing = await _credential_check(args)
    if _missing:
        return _missing
    import asyncio

    repo_name = args["repo"]
    pr_number = int(args["pr_number"])
    merge_method = (args.get("merge_method") or "squash").lower()
    if merge_method not in ("squash", "merge", "rebase"):
        return {"ok": False, "error": f"merge_method must be squash, merge or rebase, got {merge_method!r}"}

    try:
        g = await _client(args)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        if pr.merged:
            # Idempotent: a retried task must not read as a failure.
            return {"ok": True, "merged": True, "already_merged": True,
                    "pr_number": pr_number, "sha": pr.merge_commit_sha, "url": pr.html_url}
        if pr.state != "open":
            return {"ok": False, "merged": False, "refused": True, "pr_number": pr_number,
                    "reason": f"the pull request is {pr.state}, not open", "url": pr.html_url}

        # mergeable/mergeable_state are computed in the background; a PR read moments
        # after creation reports "unknown" until GitHub catches up.
        for _ in range(6):
            if pr.mergeable_state and pr.mergeable_state != "unknown":
                break
            await asyncio.sleep(2)
            pr = repo.get_pull(pr_number)

        state = pr.mergeable_state
        reviews = _review_summary(pr)
        checks = _check_summary(repo, pr)

        def refuse(reason: str) -> dict:
            return {"ok": False, "merged": False, "refused": True, "pr_number": pr_number,
                    "reason": reason, "mergeable_state": state, "mergeable": pr.mergeable,
                    "reviews": reviews, "checks": checks, "url": pr.html_url}

        if pr.draft:
            return refuse(_MERGE_REFUSAL_REASON["draft"])
        if pr.mergeable is False:
            return refuse(_MERGE_REFUSAL_REASON["dirty"])
        if reviews["changes_requested_by"]:
            return refuse("changes were requested by "
                          + ", ".join(reviews["changes_requested_by"]))
        if state not in _MERGE_ALLOWED_STATES:
            detail = _MERGE_REFUSAL_REASON.get(state, f"GitHub reports mergeable_state={state!r}")
            if checks["failing"]:
                detail += f" (failing: {', '.join(checks['failing'])})"
            elif checks["pending"]:
                detail += f" (pending: {', '.join(checks['pending'])})"
            return refuse(detail)

        kwargs = {"merge_method": merge_method}
        if args.get("commit_title"):
            kwargs["commit_title"] = args["commit_title"]
        if args.get("commit_message"):
            kwargs["commit_message"] = args["commit_message"]
        result = pr.merge(**kwargs)
        if not result.merged:
            return refuse(f"GitHub declined the merge: {result.message}")

        merged = {"ok": True, "merged": True, "already_merged": False, "pr_number": pr_number,
                  "sha": result.sha, "merge_method": merge_method,
                  "message": result.message, "url": pr.html_url}

        # Everything past this point is cleanup. The merge has already happened and cannot be
        # undone, so nothing here may turn the result into ok=False — the caller would report
        # a merge that did land as one that did not. `pr.head.repo` is None when the head
        # branch lived in a fork that has since been deleted.
        if args.get("delete_branch"):
            try:
                head_repo = getattr(pr.head, "repo", None)
                if head_repo is not None and head_repo.full_name == repo.full_name:
                    repo.get_git_ref(f"heads/{pr.head.ref}").delete()
                    merged["branch_deleted"] = pr.head.ref
                else:
                    merged["branch_deleted"] = None
                    merged["branch_delete_skipped"] = "head branch is not in this repository"
            except Exception as e:
                merged["branch_deleted"] = None
                merged["branch_delete_error"] = str(e)

        return merged
    except Exception as e:
        return {"ok": False, "merged": False, "error": str(e)}


GITHUB_MERGE_PR_SCHEMA = {
    "description": "Merge a pull request. Refuses — and reports the specific blocker — when "
                   "the PR has conflicts, a failing or pending CI check, an unsatisfied "
                   "required review, requested changes, or is still a draft. Already-merged "
                   "PRs return success. Default method is squash.",
    "type": "object",
    "properties": {
        "repo":           {"type": "string", "description": "Repository in 'owner/repo' format"},
        "pr_number":      {"type": ["integer", "string"], "description": "Pull request number"},
        "merge_method":   {"type": "string", "enum": ["squash", "merge", "rebase"],
                           "description": "How to merge (default squash)"},
        "commit_title":   {"type": "string", "description": "Override the merge commit title"},
        "commit_message": {"type": "string", "description": "Override the merge commit body"},
        "delete_branch":  {"type": "boolean",
                           "description": "Delete the head branch after merging (same-repo branches only)"},
    },
    "required": ["repo", "pr_number"],
}
