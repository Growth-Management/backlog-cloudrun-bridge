from typing import Any

import httpx

from app.core.config import Settings


class BacklogClientError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str = "backlog_client_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class BacklogClient:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
    ) -> None:
        if not settings.backlog_api_key:
            raise BacklogClientError(
                "Backlog API key is not configured",
                error_code="backlog_api_key_missing",
            )

        self._api_key = settings.backlog_api_key
        self._project_key = settings.backlog_project_key
        self._client = client or httpx.Client(
            base_url=settings.backlog_base_url.rstrip("/"),
            timeout=settings.backlog_timeout_seconds,
        )

    def get_space(self) -> dict[str, Any]:
        return self._request_dict("GET", "/api/v2/space")

    def get_project(self, project_key: str | None = None) -> dict[str, Any]:
        key = project_key or self._project_key
        return self._request_dict("GET", f"/api/v2/projects/{key}")

    def get_issue_types(self, project_key: str | None = None) -> list[dict[str, Any]]:
        key = project_key or self._project_key
        data = self._request("GET", f"/api/v2/projects/{key}/issueTypes")
        if not isinstance(data, list):
            raise BacklogClientError(
                "Backlog API returned an unexpected issue type response",
                error_code="backlog_invalid_response",
            )
        return data

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        issue = self._request_dict("GET", f"/api/v2/issues/{issue_key}")
        return normalize_issue(issue)

    def search_issues(
        self,
        keyword: str | None = None,
        status_ids: list[int] | None = None,
        assignee_ids: list[int] | None = None,
        count: int = 20,
        offset: int = 0,
        project_key: str | None = None,
    ) -> list[dict[str, Any]]:
        project = self.get_project(project_key)
        project_id = project.get("id")
        if not isinstance(project_id, int):
            raise BacklogClientError(
                "Backlog project response does not include a project id",
                error_code="backlog_invalid_response",
            )

        params: dict[str, Any] = {
            "projectId[]": [project_id],
            "count": count,
            "offset": offset,
        }
        if keyword:
            params["keyword"] = keyword
        if status_ids:
            params["statusId[]"] = status_ids
        if assignee_ids:
            params["assigneeId[]"] = assignee_ids

        issues = self._request("GET", "/api/v2/issues", params=params)
        if not isinstance(issues, list):
            raise BacklogClientError(
                "Backlog API returned an unexpected issue list response",
                error_code="backlog_invalid_response",
            )
        return [normalize_issue(issue) for issue in issues if isinstance(issue, dict)]

    def create_issue(
        self,
        summary: str,
        issue_type_id: int,
        priority_id: int,
        description: str | None = None,
        assignee_id: int | None = None,
        start_date: str | None = None,
        due_date: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        project = self.get_project(project_key)
        project_id = project.get("id")
        if not isinstance(project_id, int):
            raise BacklogClientError(
                "Backlog project response does not include a project id",
                error_code="backlog_invalid_response",
            )

        form_data: dict[str, Any] = {
            "projectId": project_id,
            "summary": summary,
            "issueTypeId": issue_type_id,
            "priorityId": priority_id,
        }
        if description is not None:
            form_data["description"] = description
        if assignee_id is not None:
            form_data["assigneeId"] = assignee_id
        if start_date is not None:
            form_data["startDate"] = start_date
        if due_date is not None:
            form_data["dueDate"] = due_date

        issue = self._request_dict("POST", "/api/v2/issues", data=form_data)
        return normalize_issue(issue)

    def _request_dict(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response_data = self._request(method, path, params=params, data=data)
        if not isinstance(response_data, dict):
            raise BacklogClientError(
                "Backlog API returned an unexpected response",
                error_code="backlog_invalid_response",
            )
        return response_data

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        request_params = dict(params or {})
        request_params["apiKey"] = self._api_key

        try:
            response = self._client.request(
                method,
                path,
                params=request_params,
                data=data,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise BacklogClientError(
                "Backlog API request timed out",
                error_code="backlog_timeout",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise BacklogClientError(
                "Backlog API returned an error",
                status_code=exc.response.status_code,
                error_code="backlog_http_error",
            ) from exc
        except httpx.HTTPError as exc:
            raise BacklogClientError(
                "Backlog API request failed",
                error_code="backlog_request_error",
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise BacklogClientError(
                "Backlog API returned an invalid JSON response",
                error_code="backlog_invalid_response",
            ) from exc

        return data


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_key": issue.get("issueKey"),
        "summary": issue.get("summary"),
        "description": issue.get("description"),
        "status": _normalize_named_value(issue.get("status")),
        "priority": _normalize_named_value(issue.get("priority")),
        "assignee": _normalize_user(issue.get("assignee")),
    }


def _normalize_named_value(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "id": value.get("id"),
        "name": value.get("name"),
    }


def _normalize_user(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "id": value.get("id"),
        "name": value.get("name"),
        "user_id": value.get("userId"),
        "mail_address": value.get("mailAddress"),
    }
