"""GitHub App credentials: app JWTs, installation tokens, and the user-to-server flow.

**Why a GitHub App and not an OAuth App.** The user picks which repositories Mergit may
touch, at install time, and GitHub enforces that list. So the repository allowlist is not
a prompt instruction the model might ignore — it is a property of the credential itself.
An OAuth App token carries the user's full account scope, which for an agent that reads
attacker-authored issue bodies is far too much.

**Three credentials, three lifetimes.**

  * *App JWT* — RS256, signed with the app's private key, `exp` ≤ 10 minutes. Proves "I am
    this app". Cannot touch a repository.
  * *Installation token* — obtained with the JWT, lives 1 hour, and is **scoped per call**
    to specific repositories and permissions. This is what the tools use. Nothing durable
    is stored: for a user whose goals only touch installed repos, Mergit holds an integer.
  * *User token* (`ghu_`, 8h) + refresh (`ghr_`, 6mo) — only for the handful of endpoints
    an installation token cannot call, notably creating a repository on a personal account.

**The cache is not an optimisation.** Every one of the 20 GitHub tools funnels through
here, and an agent loop is 15-40 tool calls per task. Minting per call would add an HTTPS
round trip plus an unseal plus two SQLite reads to each one, and would run into GitHub's
rate limit on the token endpoint itself.
"""
import logging
import time

import httpx
import jwt

from config import github_app_private_key, settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

#: (installation_id, repos, permissions) -> (token, expires_at). Process-local, which is
#: correct here: `final.md` §8.2 fixes this app at exactly one instance, permanently.
_token_cache: dict[tuple, tuple[str, int]] = {}

#: Refresh this long before actual expiry, so a call never starts with a token that dies
#: mid-flight.
_EXPIRY_MARGIN = 300


class GitHubAppNotConfigured(RuntimeError):
    pass


def configured() -> bool:
    return bool(settings.github_app_id and github_app_private_key())


def app_jwt() -> str:
    """A short-lived assertion proving we are the app.

    `iat` is backdated 60 seconds because GitHub rejects a JWT whose `iat` is in the
    future, and a second or two of clock skew between this host and GitHub is normal.
    `exp` is 9 minutes: GitHub's ceiling is 10, and a JWT that expires while in flight
    fails with a 401 that reads like a bad key.
    """
    if not configured():
        raise GitHubAppNotConfigured(
            "GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be set to use GitHub App auth"
        )
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": settings.github_app_id}
    return jwt.encode(payload, github_app_private_key(), algorithm="RS256")


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def installation_token(
    installation_id: int,
    repositories: list[str] | None = None,
    permissions: dict | None = None,
) -> str:
    """Mint (or reuse) an installation token, scoped as tightly as the caller allows.

    `repositories` are bare names, not `owner/repo` — GitHub rejects the qualified form
    here, and the resulting 422 does not explain why.
    """
    cache_key = (
        installation_id,
        tuple(sorted(repositories or [])),
        tuple(sorted((permissions or {}).items())),
    )
    cached = _token_cache.get(cache_key)
    if cached and cached[1] - _EXPIRY_MARGIN > int(time.time()):
        return cached[0]

    body: dict = {}
    if repositories:
        body["repositories"] = repositories
    if permissions:
        body["permissions"] = permissions

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers=_headers(app_jwt()),
            json=body or None,
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"could not mint an installation token for {installation_id}: "
            f"{resp.status_code} {resp.text[:200]}"
        )
    data = resp.json()
    token = data["token"]
    expires = int(time.mktime(time.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ")))
    _token_cache[cache_key] = (token, expires)
    return token


async def exchange_code(code: str, redirect_uri: str) -> dict:
    """Trade an authorization code for a user-to-server token pair."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_app_client_id,
                "client_secret": settings.github_app_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"GitHub rejected the code: {data.get('error_description', data['error'])}")
    return data


async def refresh_user_token(refresh_token: str) -> dict:
    """Redeem a `ghr_` for a new pair. Single use — the old one dies here."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_app_client_id,
                "client_secret": settings.github_app_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"refresh failed: {data.get('error_description', data['error'])}")
    return data


async def user_installations(user_token: str) -> list[dict]:
    """Installations the *user* can actually see, per GitHub, using their own token.

    This is the authorization check for the whole connection flow, and it is not optional.
    GitHub's documentation says so directly: *"Bad actors can hit this URL with a spoofed
    installation_id. Therefore, you should not rely on the validity of the installation_id
    parameter."* Writing the callback's query parameter straight into `user_installations`
    would be an account-takeover primitive — an attacker attaches *your* installation to
    *their* Mergit account and drives your repositories.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{GITHUB_API}/user/installations",
            headers=_headers(user_token),
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"could not list installations: {resp.status_code} {resp.text[:200]}")
    return resp.json().get("installations", [])


async def installation_repositories(token: str) -> list[dict]:
    """The repositories an installation may touch — the allowlist, from the source."""
    repos, page = [], 1
    async with httpx.AsyncClient(timeout=20) as client:
        while page <= 10:  # 1000 repos; past that the allowlist is not the constraint
            resp = await client.get(
                f"{GITHUB_API}/installation/repositories",
                headers=_headers(token),
                params={"per_page": 100, "page": page},
            )
            if resp.status_code >= 400:
                break
            batch = resp.json().get("repositories", [])
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return repos


async def whoami(user_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{GITHUB_API}/user", headers=_headers(user_token))
    resp.raise_for_status()
    return resp.json()


async def add_repo_to_installation(installation_id: int, repo_id: int,
                                   user_token: str) -> bool:
    """Put a newly created repository inside the installation.

    Needed because of an interaction that is invisible until it bites: a repo created with
    the *user* token (the only way to create one on a personal account) is not part of the
    App installation, so it does not appear in `installation_repositories`, so the very
    next `github_pr` against it is refused by our own allowlist. The flagship flow —
    create a repo, push the bot into it — dies exactly there.

    Only meaningful when the installation is `selected`; on an `all` installation the repo
    is already covered and this call is skipped by the caller.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.put(
            f"{GITHUB_API}/user/installations/{installation_id}/repositories/{repo_id}",
            headers=_headers(user_token),
        )
    if resp.status_code in (204, 304):
        return True
    logger.warning("could not add repo %s to installation %s: %s %s",
                   repo_id, installation_id, resp.status_code, resp.text[:200])
    return False


def clear_cache() -> None:
    _token_cache.clear()
