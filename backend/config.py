from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    groq_api_key: str = ""

    # Tools
    tavily_api_key: str = ""
    slack_webhook_url: str = ""
    github_token: str = ""
    github_default_repo: str = ""

    # Tracing
    omium_api_key: str = ""
    omium_project: str = "omnibox"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "./omnibox.db"
    workspace_dir: str = "./workspace"

    # Worker
    max_concurrent_tasks: int = 5
    lease_seconds: int = 120
    poll_interval_seconds: float = 1.0


settings = Settings()
