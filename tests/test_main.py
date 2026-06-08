import pytest

from app.main import create_app


def test_create_app_validates_required_settings_in_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("BACKLOG_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        create_app()

    assert str(exc_info.value) == (
        "Missing required settings: API_AUTH_TOKEN, BACKLOG_API_KEY"
    )


def test_create_app_allows_missing_secrets_in_local(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("BACKLOG_API_KEY", raising=False)

    app = create_app()

    assert app.title == "Backlog Cloud Run Bridge"
