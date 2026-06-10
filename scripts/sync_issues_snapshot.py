#!/usr/bin/env python3
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_BACKLOG_BASE_URL = "https://ice.backlog.jp"
DEFAULT_BACKLOG_PROJECT_KEY = "ICESAO_GENTASK"
DEFAULT_SHEET_NAME = "issues_snapshot"
DEFAULT_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 10

ISSUES_SNAPSHOT_HEADERS = [
    "issue_key",
    "issue_id",
    "project_key",
    "summary",
    "description",
    "status_id",
    "status_name",
    "priority_id",
    "priority_name",
    "issue_type_id",
    "issue_type_name",
    "assignee_id",
    "assignee_name",
    "start_date",
    "due_date",
    "created",
    "updated",
    "url",
    "last_synced_at",
    "row_hash",
]


@dataclass(frozen=True)
class SyncSettings:
    backlog_base_url: str
    backlog_api_key: str
    backlog_project_key: str
    spreadsheet_id: str
    sheet_name: str
    google_credentials_file: str
    page_size: int
    max_pages: int
    timeout_seconds: float


class SyncConfigurationError(RuntimeError):
    pass


class BacklogSyncError(RuntimeError):
    pass


def get_settings() -> SyncSettings:
    backlog_api_key = require_env("BACKLOG_API_KEY")
    spreadsheet_id = require_env("GOOGLE_SHEETS_SPREADSHEET_ID")
    google_credentials_file = require_env("GOOGLE_APPLICATION_CREDENTIALS")
    return SyncSettings(
        backlog_base_url=os.getenv("BACKLOG_BASE_URL", DEFAULT_BACKLOG_BASE_URL),
        backlog_api_key=backlog_api_key,
        backlog_project_key=os.getenv("BACKLOG_PROJECT_KEY", DEFAULT_BACKLOG_PROJECT_KEY),
        spreadsheet_id=spreadsheet_id,
        sheet_name=os.getenv("ISSUES_SNAPSHOT_SHEET_NAME", DEFAULT_SHEET_NAME),
        google_credentials_file=google_credentials_file,
        page_size=int(os.getenv("ISSUES_SYNC_PAGE_SIZE", str(DEFAULT_PAGE_SIZE))),
        max_pages=int(os.getenv("ISSUES_SYNC_MAX_PAGES", str(DEFAULT_MAX_PAGES))),
        timeout_seconds=float(os.getenv("BACKLOG_TIMEOUT_SECONDS", "20")),
    )


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SyncConfigurationError(f"Missing required environment variable: {name}")
    return value


class BacklogIssuesClient:
    def __init__(self, settings: SyncSettings) -> None:
        self._api_key = settings.backlog_api_key
        self._project_key = settings.backlog_project_key
        self._client = httpx.Client(
            base_url=settings.backlog_base_url.rstrip("/"),
            timeout=settings.timeout_seconds,
        )

    def get_project_id(self) -> int:
        data = self._request_dict("GET", f"/api/v2/projects/{self._project_key}")
        project_id = data.get("id")
        if not isinstance(project_id, int):
            raise BacklogSyncError("Backlog project response does not include an id")
        return project_id

    def fetch_issues(self, page_size: int, max_pages: int) -> list[dict[str, Any]]:
        project_id = self.get_project_id()
        issues: list[dict[str, Any]] = []
        for page in range(max_pages):
            offset = page * page_size
            page_issues = self._request_list(
                "GET",
                "/api/v2/issues",
                params={
                    "projectId[]": [project_id],
                    "count": page_size,
                    "offset": offset,
                    "sort": "updated",
                    "order": "desc",
                },
            )
            issues.extend(issue for issue in page_issues if isinstance(issue, dict))
            if len(page_issues) < page_size:
                break
        return issues

    def _request_dict(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = self._request(method, path, params=params)
        if not isinstance(data, dict):
            raise BacklogSyncError("Backlog API returned an unexpected object response")
        return data

    def _request_list(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        data = self._request(method, path, params=params)
        if not isinstance(data, list):
            raise BacklogSyncError("Backlog API returned an unexpected list response")
        return data

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        request_params = dict(params or {})
        request_params["apiKey"] = self._api_key
        try:
            response = self._client.request(method, path, params=request_params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BacklogSyncError(
                f"Backlog API returned {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise BacklogSyncError("Backlog API request failed") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BacklogSyncError("Backlog API returned invalid JSON") from exc


class GoogleSheetsIssuesSnapshot:
    def __init__(self, settings: SyncSettings) -> None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            settings.google_credentials_file,
            scopes=[SHEETS_SCOPE],
        )
        self._service = build("sheets", "v4", credentials=credentials)
        self._spreadsheet_id = settings.spreadsheet_id
        self._sheet_name = settings.sheet_name

    def replace_snapshot(self, rows: list[list[Any]]) -> None:
        self._ensure_sheet_exists()
        body = {"values": [ISSUES_SNAPSHOT_HEADERS, *rows]}
        self._service.spreadsheets().values().clear(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!A:Z",
            body={},
        ).execute()
        self._service.spreadsheets().values().update(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!A1",
            valueInputOption="RAW",
            body=body,
        ).execute()

    def _ensure_sheet_exists(self) -> None:
        metadata = self._service.spreadsheets().get(
            spreadsheetId=self._spreadsheet_id,
        ).execute()
        sheets = metadata.get("sheets", [])
        for sheet in sheets:
            properties = sheet.get("properties", {})
            if properties.get("title") == self._sheet_name:
                return

        self._service.spreadsheets().batchUpdate(
            spreadsheetId=self._spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": self._sheet_name,
                            }
                        }
                    }
                ]
            },
        ).execute()


def build_issue_rows(
    issues: list[dict[str, Any]],
    project_key: str,
    backlog_base_url: str,
    synced_at: str,
) -> list[list[Any]]:
    return [
        issue_to_row(issue, project_key, backlog_base_url, synced_at)
        for issue in issues
    ]


def issue_to_row(
    issue: dict[str, Any],
    project_key: str,
    backlog_base_url: str,
    synced_at: str,
) -> list[Any]:
    issue_key = issue.get("issueKey") or ""
    normalized = {
        "issue_key": issue_key,
        "issue_id": issue.get("id") or "",
        "project_key": project_key,
        "summary": issue.get("summary") or "",
        "description": issue.get("description") or "",
        "status_id": get_nested(issue, "status", "id"),
        "status_name": get_nested(issue, "status", "name"),
        "priority_id": get_nested(issue, "priority", "id"),
        "priority_name": get_nested(issue, "priority", "name"),
        "issue_type_id": get_nested(issue, "issueType", "id"),
        "issue_type_name": get_nested(issue, "issueType", "name"),
        "assignee_id": get_nested(issue, "assignee", "id"),
        "assignee_name": get_nested(issue, "assignee", "name"),
        "start_date": issue.get("startDate") or "",
        "due_date": issue.get("dueDate") or "",
        "created": issue.get("created") or "",
        "updated": issue.get("updated") or "",
        "url": build_issue_url(backlog_base_url, issue_key),
        "last_synced_at": synced_at,
    }
    normalized["row_hash"] = build_row_hash(normalized)
    return [normalized[header] for header in ISSUES_SNAPSHOT_HEADERS]


def get_nested(data: dict[str, Any], object_key: str, value_key: str) -> Any:
    value = data.get(object_key)
    if not isinstance(value, dict):
        return ""
    return value.get(value_key) or ""


def build_issue_url(backlog_base_url: str, issue_key: str) -> str:
    if not issue_key:
        return ""
    return f"{backlog_base_url.rstrip('/')}/view/{issue_key}"


def build_row_hash(row: dict[str, Any]) -> str:
    hash_source = {
        key: value
        for key, value in row.items()
        if key not in {"last_synced_at", "row_hash"}
    }
    payload = json.dumps(hash_source, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    settings = get_settings()
    synced_at = datetime.now(UTC).isoformat()
    backlog_client = BacklogIssuesClient(settings)
    issues = backlog_client.fetch_issues(
        page_size=settings.page_size,
        max_pages=settings.max_pages,
    )
    rows = build_issue_rows(
        issues,
        project_key=settings.backlog_project_key,
        backlog_base_url=settings.backlog_base_url,
        synced_at=synced_at,
    )
    sheet = GoogleSheetsIssuesSnapshot(settings)
    sheet.replace_snapshot(rows)
    print(
        json.dumps(
            {
                "status": "ok",
                "sheet": settings.sheet_name,
                "synced_count": len(rows),
                "synced_at": synced_at,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
