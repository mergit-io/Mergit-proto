import logging
import os
import time

from config import settings
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL
from tracing import trace

logger = logging.getLogger(__name__)


def _commit_files(repo, files, head_branch, base_sha):
    """Ensure head_branch exists (from base_sha) and commit files onto it."""
    from github import GithubException
    try:
        repo.get_branch(head_branch)
    except GithubException:
        repo.create_git_ref(f"refs/heads/{head_branch}", base_sha)
    for f in files:
        path, content = f["path"], f["content"]
        try:
            existing = repo.get_contents(path, ref=head_branch)
            repo.update_file(path, f"Fix {path}", content, existing.sha, branch=head_branch)
        except GithubException:
            repo.create_file(path, f"Add {path}", content, branch=head_branch)


@trace("github_pr")
async def github_pr(args: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "") or settings.github_token
    if not token:
        return {
            WAITING_CREDENTIAL_SENTINEL: True,
            "credential": "GITHUB_TOKEN",
            "provider": "github",
            "message": "GitHub personal access token required to create PRs",
        }

    from github import Github, GithubException

    repo_name = args.get("repo") or os.environ.get("GITHUB_DEFAULT_REPO", "") or settings.github_default_repo
    title = args["title"]
    body = args["body"]
    head_branch = args["head_branch"]
    files = args.get("files", [])

    g = Github(token)
    try:
        upstream = g.get_repo(repo_name)
    except GithubException as e:
        return {"action": "create_pr", "result": None, "url": None,
                "error": f"cannot access repo {repo_name}: {e}", "ok": False}

    # Auto-detect the real base branch — the model often guesses "main" when it's "master".
    base_branch = args.get("base_branch")
    if not base_branch or base_branch not in (b.name for b in upstream.get_branches()):
        base_branch = upstream.default_branch
    base_sha = upstream.get_branch(base_branch).commit.sha

    me = g.get_user()
    login = me.login

    # ── Path 1: we have push access → branch + PR directly on the upstream ──
    if upstream.permissions.push:
        try:
            _commit_files(upstream, files, head_branch, base_sha)
            pr = upstream.create_pull(title=title, body=body, head=head_branch, base=base_branch)
            logger.info("PR created directly on %s: %s", repo_name, pr.html_url)
            return {"action": "create_pr", "result": pr.number, "url": pr.html_url,
                    "mode": "direct", "ok": True}
        except GithubException as e:
            logger.warning("Direct PR on %s failed (%s) — falling back to fork", repo_name, e)

    # ── Path 2: no push access (or direct failed) → autonomous fork-and-PR ──
    fork_full = f"{login}/{upstream.name}"
    try:
        fork = g.get_repo(fork_full)
    except GithubException:
        logger.info("Forking %s → %s", repo_name, fork_full)
        me.create_fork(upstream)
        fork = None
        for _ in range(20):  # forks are async — poll until ready
            time.sleep(3)
            try:
                fork = g.get_repo(fork_full)
                fork.get_branch(fork.default_branch)
                break
            except GithubException:
                fork = None
        if fork is None:
            return {"action": "create_pr", "result": None, "url": None,
                    "error": f"fork {fork_full} did not become ready in time", "ok": False}

    try:
        fork_base_sha = fork.get_branch(fork.default_branch).commit.sha
        _commit_files(fork, files, head_branch, fork_base_sha)
        # Cross-repo PR: head must be "forkowner:branch", opened on the upstream.
        pr = upstream.create_pull(
            title=title, body=body, head=f"{login}:{head_branch}", base=base_branch
        )
        logger.info("PR created via fork %s → %s: %s", fork_full, repo_name, pr.html_url)
        return {"action": "create_pr", "result": pr.number, "url": pr.html_url,
                "mode": "fork", "fork": fork_full, "ok": True}
    except GithubException as e:
        return {"action": "create_pr", "result": None, "url": None,
                "error": f"fork PR failed: {e}", "ok": False}


SCHEMA = {
    "description": "Create a GitHub pull request. Commits files to a new branch, then opens a PR. "
                   "If the token lacks push access to the target repo, it AUTONOMOUSLY forks the "
                   "repo, pushes the branch to the fork, and opens a cross-repo PR upstream. "
                   "The base branch is auto-detected (handles main vs master).",
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "GitHub repo in 'owner/repo' format (uses GITHUB_DEFAULT_REPO if omitted)"},
        "title": {"type": "string", "description": "PR title"},
        "body": {"type": "string", "description": "PR description/body (markdown)"},
        "head_branch": {"type": "string", "description": "Branch name to create the PR from"},
        "base_branch": {"type": "string", "description": "Target branch (auto-detected from repo default if omitted/wrong)"},
        "files": {
            "type": "array",
            "description": "Files to commit before creating the PR",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "required": ["title", "body", "head_branch"],
}
