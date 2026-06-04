import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_env: str
    api_auth_token: str | None


def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        api_auth_token=os.getenv("API_AUTH_TOKEN"),
    )
