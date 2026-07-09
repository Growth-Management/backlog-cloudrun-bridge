#!/usr/bin/env python3
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.google_sheets_auth import build_sheets_service


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_BACKLOG_BASE_URL = "https://ice.backlog.jp"
DEFAULT_BACKLOG_PROJECT_KEY = "ICESAO_GENTASK"
DEFAULT_QUEUE_SHEET_NAME = "write_queue_v2"
DEFAULT_MAX_ROWS = 20
DEFAULT_GOOGLE_AUTH_MODE = "user_oauth"
DEFAULT_GOOGLE_OAUTH_TOKEN_FILE = "google-oauth-token.json"

WRITE_QUEUE_V2_HEADERS = [
    "queue_id",
    "requested_at",
    "requested_by",
    "request_source",
    "project_key",
    "operation_type",
    "target_issue_key",
    "issue_title",
    "issue_description",
    "comment_body",
    "new_status_name",
    "new_priority_name",
    "assignee_name",
    "due_date",
    "category_names",
    "custom_fields_json",
    "request_payload_json",
    "idempotency_key",
    "status",
    "retry_count",
    "last_error_code",
    "last_error_message",
    "result_summary",
    "processed_at",
    "processed_by_worker",
    "raw_request_text",
    "note",
]

RESULT_COLUMNS = [
    "status",
    "retry_count",
    "last_error_code",
    "last_error_message",
    "result_summary",
    "processed_at",
    "processed_by_worker",
]


@dataclass(frozen=True)
class Settings:
    backlog_base_url: str
    backlog_api_key: str
    backlog_project_key: str
    spreadsheet_id: str
    queue_sheet_name: str
    google_auth_mode: str
    google_oauth_client_secret_file: str
    google_oauth_token_file: str
    max_rows: int
    timeout_seconds: float
    dry_run: bool
    worker_name: str
    default_issue_type_id: str
    default_priority_id: str
    default_assignee_id: str


@dataclass(frozen=True)
class QueueRow:
    sheet_row_number: int
    values: dict[str, str]


@dataclass(frozen=True)
class QueueResult:
    status: str
    retry_count: int
    last_error_code: str
    last_error_message: str
    result_summary: str
    processed_at: str
    processed_by_worker: str


class SyncConfigurationError(RuntimeError):
    pass


class BacklogSyncError(RuntimeError):
    pass


class QueueValidationError(ValueError):
    pass


class UnsupportedOperationError(QueueValidationError):
    pass


class GoogleSheetsWriteQueueV2:
    def __init__(self, settings: Settings) -> None:
        self._service = build_sheets_service(
            auth_mode=settings.google_auth_mode,
            scopes=[SHEETS_SCOPE],
            service_account_file="",
            oauth_client_secret_file=settings.google_oauth_client_secret_file,
            oauth_token_file=settings.google_oauth_token_file,
        )
        self._spreadsheet_id = settings.spreadsheet_id
        self._sheet_name = settings.queue_sheet_name

    def get_queue_rows(self) -> list[QueueRow]:
        response = self._service.spreadsheets().values().get(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!A:AA",
        ).execute()
        values = response.get("values", [])
        if not values:
            return []

        rows: list[QueueRow] = []
        for index, raw_row in enumerate(values[1:], start=2):
            raw_values = raw_row[: len(WRITE_QUEUE_V2_HEADERS)]
            padded = [
                *raw_values,
                *([""] * (len(WRITE_QUEUE_V2_HEADERS) - len(raw_values))),
            ]
            rows.append(
                QueueRow(
                    sheet_row_number=index,
                    values=dict(zip(WRITE_QUEUE_V2_HEADERS, padded, strict=True)),
                )
            )
        return rows

    def update_result(self, row_number: int, result: QueueResult) -> None:
        values = [[
            result.status,
            str(result.retry_count),
            result.last_error_code,
            result.last_error_message,
            result.result_summary,
            result.processed_at,
            result.processed_by_worker,
        ]]
        start_column = column_letter(WRITE_QUEUE_V2_HEADERS.index(RESULT_COLUMNS[0]) + 1)
        end_column = column_letter(WRITE_QUEUE_V2_HEADERS.index(RESULT_COLUMNS[-1]) + 1)
        self._service.spreadsheets().values().update(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!{start_column}{row_number}:{end_column}{row_number}",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

    def mark_processing(self, row_number: int) -> None:
        status_column = column_letter(WRITE_QUEUE_V2_HEADERS.index("status") + 1)
        self._service.spreadsheets().values().update(
            spreadsheetId=self._spreadsheet_id,
            range=f"{self._sheet_name}!{status_column}{row_number}",
            valueInputOption="RAW",
            body={"values": [["processing"]]},
        ).execute()


class BacklogWriteClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.backlog_api_key
        self._project_key = settings.backlog_project_key
        self._client = httpx.Client(
            base_url=settings.backlog_base_url.rstrip("/"),
            timeout=settings.timeout_seconds,
        )

    def add_comment(self, issue_key: str, comment_body: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/v2/issues/{issue_key}/comments",
            data={"content": comment_body},
        )
        if not isinstance(response, dict):
            raise BacklogSyncError("Backlog API returned an unexpected object response")
        return response

    def create_issue(
        self,
        project_id: str,
        summary: str,
        issue_type_id: str,
        priority_id: str,
        description: str = "",
        assignee_id: str = "",
        due_date: str = "",
    ) -> dict[str, Any]:
        data = {
            "projectId": project_id,
            "summary": summary,
            "issueTypeId": issue_type_id,
            "priorityId": priority_id,
        }
        if description:
            data["description"] = description
        if assignee_id:
            data["assigneeId"] = assignee_id
        if due_date:
            data["dueDate"] = due_date

        response = self._request("POST", "/api/v2/issues", data=data)
        if not isinstance(response, dict):
            raise BacklogSyncError("Backlog API returned an unexpected object response")
        return response

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
            response = self._client.request(method, path, params=request_params, data=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BacklogSyncError(f"Backlog API returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise BacklogSyncError("Backlog API request failed") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BacklogSyncError("Backlog API returned invalid JSON") from exc


def get_settings() -> Settings:
    google_auth_mode = os.getenv("GOOGLE_AUTH_MODE", DEFAULT_GOOGLE_AUTH_MODE)
    if google_auth_mode != "user_oauth":
        raise SyncConfigurationError("process_write_queue_v2.py expects GOOGLE_AUTH_MODE=user_oauth")

    return Settings(
        backlog_base_url=os.getenv("BACKLOG_BASE_URL", DEFAULT_BACKLOG_BASE_URL),
        backlog_api_key=require_env("BACKLOG_API_KEY"),
        backlog_project_key=os.getenv("BACKLOG_PROJECT_KEY", DEFAULT_BACKLOG_PROJECT_KEY),
        spreadsheet_id=require_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
        queue_sheet_name=os.getenv("WRITE_QUEUE_SHEET_NAME", DEFAULT_QUEUE_SHEET_NAME),
        google_auth_mode=google_auth_mode,
        google_oauth_client_secret_file=require_env("GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        google_oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", DEFAULT_GOOGLE_OAUTH_TOKEN_FILE),
        max_rows=int(os.getenv("WRITE_QUEUE_MAX_ROWS", str(DEFAULT_MAX_ROWS))),
        timeout_seconds=float(os.getenv("BACKLOG_TIMEOUT_SECONDS", "20")),
        dry_run=os.getenv("WRITE_QUEUE_DRY_RUN", "false").lower() == "true",
        worker_name=os.getenv("WORKER_NAME", "backlog-sync-worker-v2"),
        default_issue_type_id=os.getenv("BACKLOG_DEFAULT_ISSUE_TYPE_ID", ""),
        default_priority_id=os.getenv("BACKLOG_DEFAULT_PRIORITY_ID", ""),
        default_assignee_id=os.getenv("BACKLOG_DEFAULT_ASSIGNEE_ID", ""),
    )


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SyncConfigurationError(f"Missing required environment variable: {name}")
    return value


def should_process(row: dict[str, str]) -> bool:
    return row.get("status", "").strip().lower() == "queued"


def parse_add_comment_payload(row: dict[str, str]) -> tuple[str, str]:
    operation_type = require_value(row, "operation_type")
    if operation_type != "add_comment":
        raise UnsupportedOperationError(f"Unsupported operation_type: {operation_type}")

    raw_payload = require_value(row, "request_payload_json")
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise QueueValidationError(f"request_payload_json is invalid: {exc}") from exc

    target_issue_key = payload.get("target_issue_key") or row.get("target_issue_key", "")
    comment_body = payload.get("comment_body") or row.get("comment_body", "")

    if not target_issue_key:
        raise QueueValidationError("target_issue_key is required")
    if not comment_body:
        raise QueueValidationError("comment_body is required")

    return target_issue_key, comment_body


def parse_create_issue_payload(row: dict[str, str], settings: Settings) -> dict[str, str]:
    operation_type = require_value(row, "operation_type")
    if operation_type != "create_issue":
        raise UnsupportedOperationError(f"Unsupported operation_type: {operation_type}")

    raw_payload = require_value(row, "request_payload_json")
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise QueueValidationError(f"request_payload_json is invalid: {exc}") from exc

    summary = payload.get("issue_title") or payload.get("summary") or row.get("issue_title", "")
    description = payload.get("issue_description") or payload.get("description") or row.get("issue_description", "")
    project_id = str(payload.get("project_id") or payload.get("projectId") or "")
    issue_type_id = str(
        payload.get("issue_type_id")
        or payload.get("issueTypeId")
        or settings.default_issue_type_id
    )
    priority_id = str(
        payload.get("priority_id")
        or payload.get("priorityId")
        or settings.default_priority_id
    )
    assignee_id = str(
        payload.get("assignee_id")
        or payload.get("assigneeId")
        or settings.default_assignee_id
    )
    due_date = payload.get("due_date") or payload.get("dueDate") or row.get("due_date", "")

    if not summary:
        raise QueueValidationError("issue_title is required")
    if not project_id:
        raise QueueValidationError("project_id is required in request_payload_json")
    if not issue_type_id:
        raise QueueValidationError("issue_type_id is required in request_payload_json or BACKLOG_DEFAULT_ISSUE_TYPE_ID")
    if not priority_id:
        raise QueueValidationError("priority_id is required in request_payload_json or BACKLOG_DEFAULT_PRIORITY_ID")

    return {
        "project_id": project_id,
        "summary": summary,
        "description": description,
        "issue_type_id": issue_type_id,
        "priority_id": priority_id,
        "assignee_id": assignee_id,
        "due_date": due_date,
    }


def process_queue_row(row: dict[str, str], backlog_client: BacklogWriteClient, settings: Settings) -> QueueResult:
    retry_count = parse_int(row.get("retry_count"), default=0)
    try:
        operation_type = require_value(row, "operation_type")
        if settings.dry_run:
            if operation_type == "add_comment":
                parse_add_comment_payload(row)
            elif operation_type == "create_issue":
                parse_create_issue_payload(row, settings)
            else:
                raise UnsupportedOperationError(f"Unsupported operation_type: {operation_type}")

            response = {"dry_run": True, "operation_type": operation_type}
            summary = summarize_response(response, operation_type)
            return QueueResult(
                status="validated",
                retry_count=retry_count,
                last_error_code="",
                last_error_message="",
                result_summary=summary,
                processed_at="",
                processed_by_worker=settings.worker_name,
            )

        if operation_type == "add_comment":
            issue_key, comment_body = parse_add_comment_payload(row)
            response = backlog_client.add_comment(issue_key, comment_body)
        elif operation_type == "create_issue":
            payload = parse_create_issue_payload(row, settings)
            response = backlog_client.create_issue(
                project_id=payload["project_id"],
                summary=payload["summary"],
                issue_type_id=payload["issue_type_id"],
                priority_id=payload["priority_id"],
                description=payload["description"],
                assignee_id=payload["assignee_id"],
                due_date=payload["due_date"],
            )
        else:
            raise UnsupportedOperationError(f"Unsupported operation_type: {operation_type}")

        return QueueResult(
            status="succeeded",
            retry_count=retry_count,
            last_error_code="",
            last_error_message="",
            result_summary=summarize_response(response, operation_type),
            processed_at=datetime.now(UTC).isoformat(),
            processed_by_worker=settings.worker_name,
        )
    except UnsupportedOperationError as exc:
        return QueueResult(
            status="on_hold",
            retry_count=retry_count,
            last_error_code="UNSUPPORTED_OPERATION",
            last_error_message=str(exc),
            result_summary="",
            processed_at="",
            processed_by_worker=settings.worker_name,
        )
    except QueueValidationError as exc:
        return QueueResult(
            status="failed",
            retry_count=retry_count + 1,
            last_error_code="VALIDATION_ERROR",
            last_error_message=str(exc),
            result_summary="",
            processed_at="",
            processed_by_worker=settings.worker_name,
        )
    except BacklogSyncError as exc:
        return QueueResult(
            status="failed",
            retry_count=retry_count + 1,
            last_error_code="BACKLOG_API_ERROR",
            last_error_message=str(exc),
            result_summary="",
            processed_at="",
            processed_by_worker=settings.worker_name,
        )


def process_queue_rows(rows: list[QueueRow], sheets: GoogleSheetsWriteQueueV2, backlog_client: BacklogWriteClient, settings: Settings) -> list[tuple[int, QueueResult]]:
    results = []
    processed = 0
    for queue_row in rows:
        if processed >= settings.max_rows:
            break
        if not should_process(queue_row.values):
            continue

        sheets.mark_processing(queue_row.sheet_row_number)
        result = process_queue_row(queue_row.values, backlog_client, settings)
        results.append((queue_row.sheet_row_number, result))
        processed += 1
    return results


def require_value(row: dict[str, str], key: str) -> str:
    value = row.get(key, "").strip()
    if not value:
        raise QueueValidationError(f"{key} is required")
    return value


def parse_int(value: str | None, default: int = 0) -> int:
    if value is None or str(value).strip() == "":
        return default
    return int(str(value).strip())


def summarize_response(response: dict[str, Any], operation_type: str) -> str:
    if response.get("dry_run"):
        return f"dry_run: {operation_type} validated"
    if operation_type == "create_issue":
        issue_key = response.get("issueKey", "")
        issue_id = response.get("id", "")
        return f"issue created: issueKey={issue_key} id={issue_id}"
    return f"comment added: id={response.get('id', '')}"


def column_letter(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main() -> None:
    settings = get_settings()
    sheets = GoogleSheetsWriteQueueV2(settings)
    backlog_client = BacklogWriteClient(settings)

    rows = sheets.get_queue_rows()
    results = process_queue_rows(rows, sheets, backlog_client, settings)
    for row_number, result in results:
        sheets.update_result(row_number, result)


if __name__ == "__main__":
    main()
