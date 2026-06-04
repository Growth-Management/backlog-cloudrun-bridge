import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_env: str
    api_auth_token: str | None
    backlog_base_url: str
    backlog_api_key: str | None
    backlog_project_key: str
    backlog_timeout_seconds: float


def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        api_auth_token=os.getenv("API_AUTH_TOKEN"),
        backlog_base_url=os.getenv("BACKLOG_BASE_URL", "https://ice.backlog.jp"),
        backlog_api_key=os.getenv("BACKLOG_API_KEY"),
        backlog_project_key=os.getenv("BACKLOG_PROJECT_KEY", "ICESAO_GENTASK"),
        backlog_timeout_seconds=float(os.getenv("BACKLOG_TIMEOUT_SECONDS", "10")),
    )


def validate_required_settings(settings: Settings) -> None:
    missing = []
    if not settings.api_auth_token:
        missing.append("API_AUTH_TOKEN")
    if not settings.backlog_api_key:
        missing.append("BACKLOG_API_KEY")

    if missing:
        missing_values = ", ".join(missing)
        raise RuntimeError(f"Missing required settings: {missing_values}")
