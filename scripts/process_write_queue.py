#!/usr/bin/env python3
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.sync_issues_snapshot import (
    BacklogSyncError,
    get_nested,
    require_env,
)


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_BACKLOG_BASE_URL = "https://ice.backlog.jp"
DEFAULT_BACKLOG_PROJECT_KEY = "ICESAO_GENTASK"
DEFAULT_QUEUE_SHEET_NAME = "write_queue"
DEFAULT_MAX_ROWS = 20

WRITE_QUEUE_HEADERS = [
    "request_id",
    "operation",
    "issue_key",
    "summary",
    "description",
    "issue_type_id",
    "priority_id",
    "status_id",
    "assignee_id",
    "start_date",
    "due_date",
    "comment",
    "requested_by",
    "requested_at",
    "approval_status",
    "execution_status",
    "validation_error",
    "applied_at",
    "backlog_response",
    "retry_count",
]

RESULT_COLUMNS = [
    "execution_status",
    "validation_error",
    "applied_at",
    "backlog_response",
    "retry_count",
]


@dataclass(frozen=True)
class WriteQueueSettings:
    backlog_base_url: str
    backlog_api_key: str
    backlog_project_key: str
    spreadsheet_id: str
    queue_sheet_name: str
    google_credentials_file: str
    max_rows: int
    timeout_seconds: float
    dry_run: bool


@dataclass(frozen=True)
class QueueRow:
    sheet_row_number: int
    values: dict[str, str]


@dataclass(frozen=True)
class QueueResult:
    execution_status: str
    validation_error: str
    applied_at: str
    backlog_response: str
    retry_count: int


class QueueValidationError(ValueError):
    pass


def get_settings() -> WriteQueueSettings:
    return WriteQueueSettings(
        backlog_base_url=os.getenv("BACKLOG_BASE_URL", DEFAULT_BACKLOG_BASE_URL),
        backlog_api_key=require_env("BACKLOG_API_KEY"),
        backlog_project_key=os.getenv("BACKLOG_PROJECT_KEY", DEFAULT_BACKLOG_PROJECT_KEY),
        spreadsheet_id=require_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
        queue_sheet_name=os.getenv("WRITE_QUEUE_SHEET_NAME", DEFAULT_QUEUE_SHEET_NAME),
        google_credentials_file=require_env("GOOGLE_APPLICATION_CREDENTIALS"),
        max_rows=int(os.getenv("WRITE_QUEUE_MAX_ROWS", str(DEFAULT_MAX_ROWS))),
        timeout_seconds=float(os.getenv("BACKLOG_TIMEOUT_SECONDS", "20")),
        dry_run=os.getenv("WRITE_QUEUE_DRY_RUN", "false").lower() == "true",
    )


class BacklogWriteClient:
    def __init__(self, settings: WriteQueueSettings) -> None:
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

    def create_issue(self, row: dict[str, str]) -> dict[str, Any]:
        form_data = compact_form(
            {
                "projectId": self.get_project_id(),
                "summary": require_value(row, "summary"),
                "description": row.get("description"),
                "issueTypeId": require_int(row, "issue_type_id"),
                "priorityId": require_int(row, "priority_id"),
                "assigneeId": optional_int(row, "assignee_id"),
                "startDate": row.get("start_date"),
                "dueDate": row.get("due_date"),
            }
        )
        return self._request_dict("POST", "/api/v2/issues", data=form_data)

    def update_issue(self, row: dict[str, str]) -> dict[str, Any]:
        issue_key = require_value(row, "issue_key")
        form_data = compact_form(
            {
                "summary": row.get("summary"),
                "description": row.get("description"),
                "statusId": optional_int(row, "status_id"),
                "priorityId": optional_int(row, "priority_id"),
                "assigneeId": optional_int(row, "assignee_id"),
                "startDate": row.get("start_date"),
                "dueDate": row.get("due_date"),
            }
        )
        if not form_data:
            raise QueueValidationError("update_issue requires at least one update field")
        return self._request_dict("PATCH", f"/api/v2/issues/{issue_key}", data=form_data)

    def add_comment(self, row: dict[str, str]) -> dict[str, Any]:
        issue_key = require_value(row, "issue_key")
        content = require_value(row, "comment")
        return self._request_dict(
            "POST",
            f"/api/v2/issues/{issue_key}/comments",
            data={"content": content},
        )

    def _request_dict(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response_data = self._request(method, path, params=params, data=data)
        if not isinstance(response_data, dict):
            raise BacklogSyncError("Backlog API returned an unexpected object response")
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


class GoogleSheetsWriteQueue:
    def __init__(self, settings: WriteQueueSettings) -> None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            settings.google_credentials_file,
            scopes=[SHEETS_SCOPE],
        )
        self._service = build("sheets", "v4", credentials=credentials)
        self._spreadsheet_id = settings.spreadsheet_id
        self._sheet_name = settings.queue_sheet_name

    def ensure_queue_sheet(self) -> None:
        metadata = self._service.spreadsheets().get(
            spreadsheetId=self._spreadsheet_id,
        ).execute()
        sheets = metadata.get("sheets", [])
        for sheet in sheets:
            properties = sheet.get("properties", {})
            if properties.get("title") == self._sheet_name:
                self._ensure_headers()
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
        self._ensure_headers()

    def get_queue_rows(self) -> list[QueueRow]:
        self.ensure_queue_sheet()
        response = self._service.spreadsheets().values().get(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!A:T",
        ).execute()
        values = response.get("values", [])
        if not values:
            return []
        rows = []
        for index, raw_row in enumerate(values[1:], start=2):
            raw_values = raw_row[: len(WRITE_QUEUE_HEADERS)]
            padded = [
                *raw_values,
                *([""] * (len(WRITE_QUEUE_HEADERS) - len(raw_values))),
            ]
            rows.append(
                QueueRow(
                    sheet_row_number=index,
                    values=dict(zip(WRITE_QUEUE_HEADERS, padded, strict=True)),
                )
            )
        return rows

    def update_result(self, row_number: int, result: QueueResult) -> None:
        values = [
            [
                result.execution_status,
                result.validation_error,
                result.applied_at,
                result.backlog_response,
                result.retry_count,
            ]
        ]
        start_column = column_letter(WRITE_QUEUE_HEADERS.index(RESULT_COLUMNS[0]) + 1)
        end_column = column_letter(WRITE_QUEUE_HEADERS.index(RESULT_COLUMNS[-1]) + 1)
        self._service.spreadsheets().values().update(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!{start_column}{row_number}:{end_column}{row_number}",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

    def _ensure_headers(self) -> None:
        response = self._service.spreadsheets().values().get(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!A1:T1",
        ).execute()
        values = response.get("values", [])
        if values and values[0] == WRITE_QUEUE_HEADERS:
            return
        self._service.spreadsheets().values().update(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!A1",
            valueInputOption="RAW",
            body={"values": [WRITE_QUEUE_HEADERS]},
        ).execute()


def process_queue_rows(
    rows: list[QueueRow],
    backlog_client: BacklogWriteClient,
    max_rows: int,
    dry_run: bool = False,
) -> list[tuple[int, QueueResult]]:
    results = []
    processed = 0
    for queue_row in rows:
        if processed >= max_rows:
            break
        if not should_process(queue_row.values):
            continue
        result = process_queue_row(queue_row.values, backlog_client, dry_run=dry_run)
        results.append((queue_row.sheet_row_number, result))
        processed += 1
    return results


def should_process(row: dict[str, str]) -> bool:
    return (
        row.get("approval_status", "").strip().lower() == "approved"
        and row.get("execution_status", "").strip().lower() == "queued"
    )


def process_queue_row(
    row: dict[str, str],
    backlog_client: BacklogWriteClient,
    dry_run: bool = False,
) -> QueueResult:
    retry_count = parse_int(row.get("retry_count"), default=0)
    try:
        operation = require_value(row, "operation")
        validate_operation(operation)
        validate_row_for_operation(row, operation)
        if dry_run:
            response = {"dry_run": True, "operation": operation}
        elif operation == "create_issue":
            response = backlog_client.create_issue(row)
        elif operation == "update_issue":
            response = backlog_client.update_issue(row)
        else:
            response = backlog_client.add_comment(row)

        return QueueResult(
            execution_status="applied" if not dry_run else "validated",
            validation_error="",
            applied_at=datetime.now(UTC).isoformat() if not dry_run else "",
            backlog_response=summarize_dry_run_response(response)
            if dry_run
            else summarize_backlog_response(response),
            retry_count=retry_count,
        )
    except (BacklogSyncError, QueueValidationError, ValueError) as exc:
        return QueueResult(
            execution_status="failed",
            validation_error=str(exc),
            applied_at="",
            backlog_response="",
            retry_count=retry_count + 1,
        )


def validate_operation(operation: str) -> None:
    allowed = {"create_issue", "update_issue", "add_comment"}
    if operation not in allowed:
        raise QueueValidationError(f"Unsupported operation: {operation}")


def validate_row_for_operation(row: dict[str, str], operation: str) -> None:
    if operation == "create_issue":
        require_value(row, "summary")
        require_int(row, "issue_type_id")
        require_int(row, "priority_id")
        optional_int(row, "assignee_id")
        return

    if operation == "update_issue":
        require_value(row, "issue_key")
        update_fields = compact_form(
            {
                "summary": row.get("summary"),
                "description": row.get("description"),
                "status_id": row.get("status_id"),
                "priority_id": row.get("priority_id"),
                "assignee_id": row.get("assignee_id"),
                "start_date": row.get("start_date"),
                "due_date": row.get("due_date"),
            }
        )
        if not update_fields:
            raise QueueValidationError("update_issue requires at least one update field")
        optional_int(row, "status_id")
        optional_int(row, "priority_id")
        optional_int(row, "assignee_id")
        return

    require_value(row, "issue_key")
    require_value(row, "comment")


def require_value(row: dict[str, str], key: str) -> str:
    value = row.get(key, "").strip()
    if not value:
        raise QueueValidationError(f"{key} is required")
    return value


def require_int(row: dict[str, str], key: str) -> int:
    value = require_value(row, key)
    return parse_positive_int(value, key)


def optional_int(row: dict[str, str], key: str) -> int | None:
    value = row.get(key, "").strip()
    if not value:
        return None
    return parse_positive_int(value, key)


def parse_positive_int(value: str, key: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise QueueValidationError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise QueueValidationError(f"{key} must be greater than 0")
    return parsed


def parse_int(value: str | None, default: int) -> int:
    try:
        return int(value or "")
    except ValueError:
        return default


def compact_form(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if value is not None and value != ""
    }


def summarize_backlog_response(response: dict[str, Any]) -> str:
    summary = {
        "issue_key": response.get("issueKey"),
        "comment_id": response.get("id") if "content" in response else None,
        "summary": response.get("summary"),
        "status": get_nested(response, "status", "name"),
    }
    return json.dumps(compact_form(summary), ensure_ascii=False, separators=(",", ":"))


def summarize_dry_run_response(response: dict[str, Any]) -> str:
    return json.dumps(response, ensure_ascii=False, separators=(",", ":"))


def column_letter(column_number: int) -> str:
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main() -> None:
    settings = get_settings()
    sheet = GoogleSheetsWriteQueue(settings)
    rows = sheet.get_queue_rows()
    backlog_client = BacklogWriteClient(settings)
    results = process_queue_rows(
        rows,
        backlog_client,
        max_rows=settings.max_rows,
        dry_run=settings.dry_run,
    )
    for row_number, result in results:
        sheet.update_result(row_number, result)
    print(
        json.dumps(
            {
                "status": "ok",
                "sheet": settings.queue_sheet_name,
                "processed_count": len(results),
                "dry_run": settings.dry_run,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
