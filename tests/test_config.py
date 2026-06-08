import pytest

from app.core.config import get_settings, validate_required_settings


def test_get_settings_uses_backlog_defaults(monkeypatch) -> None:
    monkeypatch.delenv("BACKLOG_BASE_URL", raising=False)
    monkeypatch.delenv("BACKLOG_PROJECT_KEY", raising=False)
    monkeypatch.delenv("BACKLOG_TIMEOUT_SECONDS", raising=False)

    settings = get_settings()

    assert settings.backlog_base_url == "https://ice.backlog.jp"
    assert settings.backlog_project_key == "ICESAO_GENTASK"
    assert settings.backlog_timeout_seconds == 10


def test_validate_required_settings_reports_missing_secrets(monkeypatch) -> None:
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("BACKLOG_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        validate_required_settings(get_settings())

    assert str(exc_info.value) == (
        "Missing required settings: API_AUTH_TOKEN, BACKLOG_API_KEY"
    )


def test_validate_required_settings_accepts_required_secrets(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("BACKLOG_API_KEY", "backlog-key")

    validate_required_settings(get_settings())
