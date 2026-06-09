from fastapi.testclient import TestClient

from app.api.routes.issues import get_backlog_client
from app.clients.backlog_client import BacklogClientError
from app.main import app


class FakeBacklogClient:
    def search_issues(self, **kwargs) -> list[dict]:
        assert kwargs == {
            "keyword": "Example",
            "status_ids": [1, 2],
            "assignee_ids": [10],
            "count": 20,
            "offset": 0,
        }
        return [
            {
                "issue_key": "ICESAO_GENTASK-1",
                "summary": "Example",
                "status": {"id": 1, "name": "Open"},
            }
        ]

    def get_issue(self, issue_key: str) -> dict:
        assert issue_key == "ICESAO_GENTASK-1"
        return {
            "issue_key": "ICESAO_GENTASK-1",
            "summary": "Example",
            "description": "Body",
            "status": {"id": 1, "name": "Open"},
            "priority": {"id": 3, "name": "Normal"},
        }

    def get_issue_types(self) -> list[dict]:
        return [{"id": 5, "name": "Task"}]

    def create_issue(self, **kwargs) -> dict:
        assert kwargs == {
            "summary": "Example",
            "description": "Body",
            "issue_type_id": 5,
            "priority_id": 3,
            "assignee_id": 10,
            "start_date": None,
            "due_date": "2026-06-10",
        }
        return {
            "issue_key": "ICESAO_GENTASK-1",
            "summary": "Example",
            "description": "Body",
            "status": {"id": 1, "name": "Open"},
            "priority": {"id": 3, "name": "Normal"},
            "assignee": {"id": 10, "name": "篠原邦昭"},
        }


class FailingBacklogClient:
    def create_issue(self, **kwargs) -> dict:
        raise BacklogClientError(
            "Backlog API returned an error",
            status_code=400,
            error_code="backlog_http_error",
        )


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_create_issue_accepts_valid_request(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/issues",
        headers={"Authorization": "Bearer test-token"},
        json={
            "summary": "Example",
            "description": "Body",
            "issue_type_name": "Task",
            "priority": "normal",
            "assignee_id": 10,
            "due_date": "2026-06-10",
        },
    )

    assert response.status_code == 201
    assert response.json()["issue_key"] == "ICESAO_GENTASK-1"


def test_list_issues_accepts_filters(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.get(
        "/issues?keyword=Example&status_id=1&status_id=2&assignee_id=10",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "issues": [
            {
                "issue_key": "ICESAO_GENTASK-1",
                "summary": "Example",
                "description": None,
                "status": {"id": 1, "name": "Open"},
                "priority": None,
                "assignee": None,
            }
        ],
        "count": 1,
        "offset": 0,
    }


def test_get_issue_returns_detail(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.get(
        "/issues/ICESAO_GENTASK-1",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "issue_key": "ICESAO_GENTASK-1",
        "summary": "Example",
        "description": "Body",
        "status": {"id": 1, "name": "Open"},
        "priority": {"id": 3, "name": "Normal"},
        "assignee": None,
    }


def test_create_issue_requires_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post("/issues", json={"summary": "Example"})

    assert response.status_code == 401


def test_create_issue_rejects_unknown_issue_type(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/issues",
        headers={"Authorization": "Bearer test-token"},
        json={
            "summary": "Example",
            "issue_type_name": "Unknown",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unknown issue_type_name: Unknown"}


def test_create_issue_converts_backlog_error(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FailingBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/issues",
        headers={"Authorization": "Bearer test-token"},
        json={
            "summary": "Example",
            "issue_type_id": 5,
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "message": "Backlog API returned an error",
            "error_code": "backlog_http_error",
            "upstream_status_code": 400,
        }
    }
