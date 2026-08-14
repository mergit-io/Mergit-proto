"""One place that answers "what is our GitHub token, and is it usable".

Before this module the answer depended on which file you asked. `github_pr` read
`os.environ` *or* `settings.github_token`; every tool in `github_ops` read only
`os.environ`. Since `Settings` loads `backend/.env` through pydantic-settings —
which populates the settings object and never touches `os.environ` — a token
configured the documented way made `github_pr` work while the other nine tools
reported a missing credential and parked their task in WAITING_CREDENTIAL.
Hosts that inject real environment variables (Render) hid the split entirely.
"""
import os
from typing import Any

from config import settings
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL

TOKEN_MISSING: dict[str, Any] = {
    WAITING_CREDENTIAL_SENTINEL: True,
    "credential": "GITHUB_TOKEN",
    "provider": "github",
    "message": "GitHub personal access token required",
}


def github_token() -> str:
    """The active token, checked in both places it can legitimately live.

    `os.environ` wins so that a key saved at runtime through `PUT /api/config/keys`
    takes effect without a restart.
    """
    return os.environ.get("GITHUB_TOKEN", "") or settings.github_token or ""


def client():
    from github import Github

    return Github(github_token())


def resolve_repo(args: dict) -> str:
    """Repo from the tool args, falling back to the configured default."""
    return (
        args.get("repo")
        or os.environ.get("GITHUB_DEFAULT_REPO", "")
        or settings.github_default_repo
    )
