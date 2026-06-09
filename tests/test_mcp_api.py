import json

from fastapi.testclient import TestClient

from app.api.routes.mcp import get_backlog_client
from app.clients.backlog_client import BacklogClientError
from app.main import app


class FakeBacklogClient:
    def search_issues(self, **kwargs) -> list[dict]:
        assert kwargs == {
            "keyword": "Example",
            "status_ids": [1],
            "assignee_ids": [10],
            "count": 10,
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


class FailingBacklogClient:
    def get_issue(self, issue_key: str) -> dict:
        raise BacklogClientError(
            "Backlog API returned an error",
            status_code=404,
            error_code="backlog_http_error",
        )


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_mcp_initialize_returns_server_capabilities(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0.1.0"},
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["protocolVersion"] == "2025-06-18"
    assert body["result"]["capabilities"] == {"tools": {"listChanged": False}}


def test_mcp_initialized_notification_returns_accepted(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
    )

    assert response.status_code == 202


def test_mcp_tools_list_returns_read_only_tools(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={
            "jsonrpc": "2.0",
            "id": "tools",
            "method": "tools/list",
        },
    )

    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "backlog_search_issues",
        "backlog_get_issue",
    ]
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)


def test_mcp_search_issues_tool_calls_service(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "backlog_search_issues",
                "arguments": {
                    "keyword": "Example",
                    "status_ids": [1],
                    "assignee_ids": [10],
                    "count": 10,
                },
            },
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    content = json.loads(result["content"][0]["text"])
    assert content == {
        "issues": [
            {
                "issue_key": "ICESAO_GENTASK-1",
                "summary": "Example",
                "status": {"id": 1, "name": "Open"},
            }
        ],
        "count": 1,
        "offset": 0,
    }


def test_mcp_get_issue_tool_calls_service(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "backlog_get_issue",
                "arguments": {"issue_key": "ICESAO_GENTASK-1"},
            },
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    content = json.loads(result["content"][0]["text"])
    assert content["issue_key"] == "ICESAO_GENTASK-1"
    assert content["description"] == "Body"


def test_mcp_tool_call_returns_tool_error_for_backlog_error(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FailingBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "backlog_get_issue",
                "arguments": {"issue_key": "ICESAO_GENTASK-404"},
            },
        },
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    content = json.loads(result["content"][0]["text"])
    assert content == {
        "message": "Backlog API returned an error",
        "error_code": "backlog_http_error",
        "upstream_status_code": 404,
    }


def test_mcp_requires_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    app.dependency_overrides[get_backlog_client] = lambda: FakeBacklogClient()
    client = TestClient(app)

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        },
    )

    assert response.status_code == 401
