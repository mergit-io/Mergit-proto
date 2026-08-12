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

    # Worker
    max_concurrent_tasks: int = 5
    lease_seconds: int = 300
    poll_interval_seconds: float = 1.0

    # Dev
    debug: bool = False


settings = Settings()


def cors_origin_list() -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
