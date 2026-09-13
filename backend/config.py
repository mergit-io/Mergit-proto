from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""   # GEMINI_API_KEY — used by LiteLLM for gemini/ models
    google_api_key: str = ""   # GOOGLE_API_KEY — accepted alias, bridged at startup
    mistral_api_key: str = ""

    # Tools
    tavily_api_key: str = ""
    slack_webhook_url: str = ""
    github_token: str = ""
    github_default_repo: str = ""

    # Tracing
    omium_api_key: str = ""
    omium_project: str = "omnibox"
    omium_skip_workflow_register: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "./omnibox.db"
    workspace_dir: str = "./workspace"
    frontend_url: str = "http://localhost:3000"

    # OAuth
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    oauth_github_client_id: str = ""
    oauth_github_client_secret: str = ""
    oauth_github_redirect_uri: str = "http://localhost:8000/api/auth/github/callback"
    auth_secret_key: str = "change-me-in-env"

    # Worker
    max_concurrent_tasks: int = 5
    lease_seconds: int = 300
    poll_interval_seconds: float = 1.0

    # Dev
    debug: bool = False


settings = Settings()
