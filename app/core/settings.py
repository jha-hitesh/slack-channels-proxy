from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    docs_username: str = "admin"
    docs_password: str = "admin"

    slack_base_url: str = "https://slack.com/api"
    slack_signing_secret: str = ""
    slack_signature_tolerance_seconds: int = 300
    database_url: str = "sqlite:///./data/slack_proxy.db"
    sync_lock_stale_after_minutes: int = 10


settings = Settings()
