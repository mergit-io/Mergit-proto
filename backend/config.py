import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


_runtime_config_dir = os.environ.get("RUNTIME_CONFIG_DIR")
if _runtime_config_dir:
    load_dotenv(Path(_runtime_config_dir) / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    # One key, many providers — the fallback of last resort when a first-party
    # quota is gone. See _FALLBACKS in llm.py.
    openrouter_api_key: str = ""

    # Tools
    tavily_api_key: str = ""
    github_token: str = ""
    github_default_repo: str = ""
    mergit_repo: str = "mergit-io/Mergit-proto"  # repo where self-heal issues/PRs are filed


    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "./mergit.db"
    workspace_dir: str = "./workspace"
    runtime_config_dir: str = "."
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"
    cookie_secure: bool = False

    # Shared-secret gate for public deployments. Empty = wide open, which is right on a
    # laptop and wrong anywhere reachable: the API is unauthenticated, so a public URL
    # hands out the provider keys and `code_exec` to anyone who finds it. See access_gate.py.
    access_password: str = ""

    # Demo seeding — mint a canned goal + 3 proofs on boot when the ledger is empty.
    # For hosts with no persistent disk, where every restart otherwise wipes the DB and
    # a visitor lands on an empty dashboard.
    seed_demo: bool = False

    # ── Identity ────────────────────────────────────────────────────────────────
    # Google is the identity anchor and nothing else. `openid email profile` are
    # non-sensitive scopes: no Google verification, no CASA, no cost, ever. Anything
    # beyond identity (Gmail, Drive, Calendar) is a separate *connection*, requested at
    # the point of use — never bolted onto login.
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_google_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    #: Signs the short-lived OAuth transaction cookie and the connection `state` HMAC.
    #: Boot refuses the default value once auth is enabled — see `require_auth_secret()`.
    auth_secret_key: str = "change-me-in-env"
    #: Comma-separated. Recomputed from the ID token on EVERY login, so revoking admin is
    #: a config change rather than a DB edit. Never "first user wins": on a public URL the
    #: first user is a stranger.
    admin_emails: str = ""
    #: Session lifetime. Sessions are opaque ids backed by a row, so this is a ceiling,
    #: not a promise — `POST /api/auth/logout` revokes server-side and takes effect at once.
    session_ttl_seconds: int = 60 * 60 * 24 * 14

    # ── Delegated authority ─────────────────────────────────────────────────────
    # A GitHub App, not an OAuth App: permissions are per-repository and chosen by the
    # user at install time, so the repo allowlist is enforced by GitHub rather than by
    # our prompt. The private key signs a ≤10-minute RS256 JWT which is exchanged for a
    # 1-hour installation token, scoped per call.
    github_app_id: str = ""
    github_app_client_id: str = ""
    github_app_client_secret: str = ""
    #: PEM. Newlines may be written as literal "\n" so it survives a one-line env var.
    github_app_private_key: str = ""
    github_app_slug: str = "mergit"
    github_webhook_secret: str = ""

    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""

    #: Wraps the per-row data keys that encrypt stored OAuth tokens. Read once at startup
    #: and popped from os.environ before the worker starts, because `PUT /api/config/keys`
    #: writes into os.environ and `code_exec` inherits it.
    mergit_kek_current: str = ""
    #: Retired KEKs, "id:base64key" comma-separated, kept only so old rows still decrypt.
    mergit_kek_previous: str = ""

    #: Self-heal files issues on Mergit's OWN repo, as Mergit — deliberately outside the
    #: per-user broker. Falls back to `github_token` so existing deployments keep working.
    mergit_self_heal_token: str = ""

    # ── Demo posture ────────────────────────────────────────────────────────────
    # `code_exec` runs model-authored Python. Until it runs out of process (Phase 6) a
    # public deployment sets this, which unregisters the tool outright — closing the
    # remote-code-execution hole while leaving the showcase fully interactive. A password
    # gate would close it too, and would also kill the demo.
    demo_safe_mode: bool = False

    # Chain — see docs/superpowers/specs/2026-08-12-onchain-proof-layer.md
    # "local" runs a real EVM in-process: no RPC, no key, no tokens. "monad-testnet" needs
    # chain_rpc_url + a funded chain_private_key. Switching targets requires no code change.
    chain_enabled: bool = True
    chain_target: str = "local"
    chain_rpc_url: str = ""
    chain_private_key: str = ""
    chain_submit_interval_seconds: float = 2.0

    # API limits. Both endpoints below are unauthenticated, so these bound abuse rather
    # than real use: the orchestrator is expected to cope with long problem statements
    # (it truncates to 3000 chars for planning), and no UI asks for more than a page.
    max_goal_chars: int = 20_000
    max_page_size: int = 200

    # Worker
    max_concurrent_tasks: int = 5
    lease_seconds: int = 300
    poll_interval_seconds: float = 1.0

    # Dev
    debug: bool = False


settings = Settings()


def cors_origin_list() -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


def admin_email_set() -> set[str]:
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


def auth_enabled() -> bool:
    """Auth is on exactly when Google is configured. There is no separate switch.

    A boolean flag would be a way to accidentally ship an open deployment; tying it to the
    credentials means the only way to have login is to have configured login.
    """
    return bool(settings.oauth_google_client_id and settings.oauth_google_client_secret)


def require_auth_secret() -> None:
    """Refuse to boot with a guessable session secret once auth is enabled.

    `auth_secret_key` defaulted to "change-me-in-env" for as long as the signing code was
    dead. The moment it signs anything real, a deployment that missed the variable has
    forgeable OAuth state, so this is a hard failure and not a warning.
    """
    if not auth_enabled():
        return
    secret = settings.auth_secret_key
    if secret == "change-me-in-env" or len(secret) < 32:
        raise RuntimeError(
            "AUTH_SECRET_KEY must be set to at least 32 random characters when Google "
            "sign-in is configured (it is currently the default or too short). "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
        )


def github_app_private_key() -> str:
    """The PEM, with literal \\n sequences restored to real newlines.

    Render and most dashboards store env vars as a single line, so a pasted PEM arrives
    with its newlines escaped. Cryptography rejects that with an error that does not
    mention newlines, which is a bad afternoon.
    """
    return settings.github_app_private_key.replace("\\n", "\n").strip()
