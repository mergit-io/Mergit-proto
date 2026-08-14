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
    # OpenRouter resells the same Anthropic models against a single key. It is a
    # separate LiteLLM provider (`openrouter/...`), not an alias for Anthropic — a
    # deployment can hold this key and no ANTHROPIC_API_KEY, which is why availability
    # is resolved per provider prefix rather than per model family.
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

    # OAuth
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    oauth_github_client_id: str = ""
    oauth_github_client_secret: str = ""
    oauth_github_redirect_uri: str = "http://localhost:8000/api/auth/github/callback"
    auth_secret_key: str = "change-me-in-env"

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
