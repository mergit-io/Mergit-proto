import asyncio
import logging

from tools.github_client import TOKEN_MISSING, client as _client, github_token, resolve_repo

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


def _find_open_pr(upstream, head_label: str, base_branch: str):
    """The PR this call would have created, if a previous attempt already opened it."""
    from github import GithubException
    try:
        for pr in upstream.get_pulls(state="open", base=base_branch, head=head_label):
            return pr
    except GithubException:
        pass
    return None


def _resolve_base(upstream, requested: str | None) -> str:
    """The real base branch. Models routinely guess 'main' on a 'master' repo.

    Checked with a single branch lookup — the previous membership test walked every
    branch in the repository on every PR.
    """
    from github import GithubException
    if requested:
        try:
            upstream.get_branch(requested)
            return requested
        except GithubException:
            logger.info("base branch %r not found on %s — using default %r",
                        requested, upstream.full_name, upstream.default_branch)
    return upstream.default_branch


async def github_pr(args: dict) -> dict:
    if not github_token():
        return {**TOKEN_MISSING, "message": "GitHub personal access token required to create PRs"}

    from github import GithubException

    repo_name = resolve_repo(args)
    title = args["title"]
    body = args["body"]
    head_branch = args["head_branch"]
    files = args.get("files", []) or []

    # A PR with no file changes is rejected by GitHub as "No commits between <base> and
    # <head>" after the branch has already been created, leaving a stray branch behind.
    # Refusing up front keeps the repo clean and gives the agent a reason it can act on.
    if not files:
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": "files[] is empty — a pull request needs at least one changed file. "
                         "Pass files as [{\"path\": ..., \"content\": ...}]."}

    g = _client()
    try:
        upstream = g.get_repo(repo_name)
    except GithubException as e:
        return {"action": "create_pr", "result": None, "url": None,
                "error": f"cannot access repo {repo_name}: {e}", "ok": False}

    base_branch = _resolve_base(upstream, args.get("base_branch"))
    base_sha = upstream.get_branch(base_branch).commit.sha

    me = g.get_user()
    login = me.login

    # ── Path 1: we have push access → branch + PR directly on the upstream ──
    if getattr(upstream.permissions, "push", False):
        try:
            _commit_files(upstream, files, head_branch, base_sha)
            pr = upstream.create_pull(title=title, body=body, head=head_branch, base=base_branch)
            logger.info("PR created directly on %s: %s", repo_name, pr.html_url)
            return {"action": "create_pr", "result": pr.number, "url": pr.html_url,
                    "mode": "direct", "ok": True}
        except GithubException as e:
            # Re-running a task that already opened its PR must not read as a failure.
            existing = _find_open_pr(upstream, f"{upstream.owner.login}:{head_branch}", base_branch)
            if existing is not None:
                logger.info("PR already open on %s: %s", repo_name, existing.html_url)
                return {"action": "create_pr", "result": existing.number, "url": existing.html_url,
                        "mode": "direct", "existing": True, "ok": True}
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
            await asyncio.sleep(3)
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
        # Branch from the UPSTREAM base commit, not from the fork's own default branch.
        # A fork created weeks ago sits at whatever the upstream looked like then, so
        # branching off it produces a PR whose diff reverts every commit landed since.
        # Forks share an object store with the upstream, so the upstream sha is valid here.
        try:
            _commit_files(fork, files, head_branch, base_sha)
        except GithubException:
            logger.warning("Could not branch %s from upstream sha %s — falling back to the "
                           "fork's own %s (the PR may show unrelated changes)",
                           head_branch, base_sha[:8], fork.default_branch)
            _commit_files(fork, files, head_branch,
                          fork.get_branch(fork.default_branch).commit.sha)

        # Cross-repo PR: head must be "forkowner:branch", opened on the upstream.
        head_label = f"{login}:{head_branch}"
        try:
            pr = upstream.create_pull(title=title, body=body, head=head_label, base=base_branch)
        except GithubException:
            existing = _find_open_pr(upstream, head_label, base_branch)
            if existing is None:
                raise
            logger.info("PR already open via fork %s: %s", fork_full, existing.html_url)
            return {"action": "create_pr", "result": existing.number, "url": existing.html_url,
                    "mode": "fork", "fork": fork_full, "existing": True, "ok": True}
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
                   "The base branch is auto-detected (handles main vs master). Requires at least "
                   "one file in files[]; if the PR already exists it is returned instead of failing.",
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "GitHub repo in 'owner/repo' format (uses GITHUB_DEFAULT_REPO if omitted)"},
        "title": {"type": "string", "description": "PR title"},
        "body": {"type": "string", "description": "PR description/body (markdown)"},
        "head_branch": {"type": "string", "description": "Branch name to create the PR from"},
        "base_branch": {"type": "string", "description": "Target branch (auto-detected from repo default if omitted/wrong)"},
        "files": {
            "type": "array",
            "description": "Files to commit before creating the PR (required, at least one)",
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
    "required": ["title", "body", "head_branch", "files"],
}
