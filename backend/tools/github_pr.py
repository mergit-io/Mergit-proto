import os

from config import settings
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL
from tracing import trace


@trace("github_pr")
async def github_pr(args: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
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
    base_branch = args.get("base_branch", "main")
    files = args.get("files", [])

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)

        base_ref = repo.get_branch(base_branch)
        try:
            repo.get_branch(head_branch)
        except GithubException:
            repo.create_git_ref(f"refs/heads/{head_branch}", base_ref.commit.sha)

        for f in files:
            path = f["path"]
            content = f["content"]
            try:
                existing = repo.get_contents(path, ref=head_branch)
                repo.update_file(path, f"Update {path}", content, existing.sha, branch=head_branch)
            except GithubException:
                repo.create_file(path, f"Add {path}", content, branch=head_branch)

        pr = repo.create_pull(title=title, body=body, head=head_branch, base=base_branch)
        return {"action": "create_pr", "result": pr.number, "url": pr.html_url, "ok": True}
    except Exception as e:
        return {"action": "create_pr", "result": None, "url": None, "error": str(e), "ok": False}


SCHEMA = {
    "description": "Create a GitHub pull request, optionally committing files to a new branch first.",
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "GitHub repo in 'owner/repo' format (uses GITHUB_DEFAULT_REPO if omitted)"},
        "title": {"type": "string", "description": "PR title"},
        "body": {"type": "string", "description": "PR description/body (markdown)"},
        "head_branch": {"type": "string", "description": "Branch name to create the PR from"},
        "base_branch": {"type": "string", "default": "main", "description": "Target branch to merge into"},
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
