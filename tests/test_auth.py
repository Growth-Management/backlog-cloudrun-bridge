from fastapi.testclient import TestClient

from app.main import app


def test_auth_check_accepts_valid_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    client = TestClient(app)

    response = client.get(
        "/auth/check",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_check_rejects_missing_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    client = TestClient(app)

    response = client.get("/auth/check")

    assert response.status_code == 401
    assert response.json() == {"detail": "Bearer token is required"}


def test_auth_check_rejects_invalid_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    client = TestClient(app)

    response = client.get(
        "/auth/check",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid bearer token"}


def test_auth_check_fails_when_token_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    client = TestClient(app)

    response = client.get(
        "/auth/check",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": "API authentication token is not configured",
    }
