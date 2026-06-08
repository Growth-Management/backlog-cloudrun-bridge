import httpx
import pytest

from app.clients.backlog_client import (
    BacklogClient,
    BacklogClientError,
    normalize_issue,
)
from app.core.config import Settings


def make_settings(api_key: str | None = "backlog-key") -> Settings:
    return Settings(
        app_env="local",
        api_auth_token="api-token",
        backlog_base_url="https://ice.backlog.jp",
        backlog_api_key=api_key,
        backlog_project_key="ICESAO_GENTASK",
        backlog_timeout_seconds=10,
    )


def test_client_adds_api_key_without_exposing_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["apiKey"] == "backlog-key"
        return httpx.Response(200, json={"spaceKey": "ice"})

    client = BacklogClient(
        make_settings(),
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://ice.backlog.jp",
        ),
    )

    assert client.get_space() == {"spaceKey": "ice"}


def test_client_raises_when_api_key_is_missing() -> None:
    with pytest.raises(BacklogClientError) as exc_info:
        BacklogClient(make_settings(api_key=None))

    assert exc_info.value.error_code == "backlog_api_key_missing"


def test_client_converts_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errors": [{"message": "not found"}]})

    client = BacklogClient(
        make_settings(),
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://ice.backlog.jp",
        ),
    )

    with pytest.raises(BacklogClientError) as exc_info:
        client.get_issue("ICESAO_GENTASK-1")

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "backlog_http_error"


def test_client_converts_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    client = BacklogClient(
        make_settings(),
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://ice.backlog.jp",
        ),
    )

    with pytest.raises(BacklogClientError) as exc_info:
        client.get_space()

    assert exc_info.value.error_code == "backlog_timeout"


def test_client_converts_invalid_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = BacklogClient(
        make_settings(),
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://ice.backlog.jp",
        ),
    )

    with pytest.raises(BacklogClientError) as exc_info:
        client.get_space()

    assert exc_info.value.error_code == "backlog_invalid_response"


def test_normalize_issue_extracts_stable_fields() -> None:
    normalized = normalize_issue(
        {
            "issueKey": "ICESAO_GENTASK-1",
            "summary": "Example",
            "description": "Body",
            "status": {"id": 1, "name": "Open"},
            "priority": {"id": 3, "name": "Normal"},
            "assignee": {
                "id": 10,
                "name": "篠原邦昭",
                "userId": "sinohara",
                "mailAddress": "sinohara@example.com",
            },
        }
    )

    assert normalized["issue_key"] == "ICESAO_GENTASK-1"
    assert normalized["status"] == {"id": 1, "name": "Open"}
    assert normalized["priority"] == {"id": 3, "name": "Normal"}
    assert normalized["assignee"] == {
        "id": 10,
        "name": "篠原邦昭",
        "user_id": "sinohara",
        "mail_address": "sinohara@example.com",
    }
