#!/usr/bin/env python3
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.google_sheets_auth import build_sheets_service
from scripts.process_write_queue_v2 import WRITE_QUEUE_V2_HEADERS


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_BACKLOG_BASE_URL = "https://ice.backlog.jp"
DEFAULT_SPREADSHEET_ID_ENV = "GOOGLE_SHEETS_SPREADSHEET_ID"
DEFAULT_GOOGLE_AUTH_MODE = "user_oauth"
DEFAULT_GOOGLE_OAUTH_TOKEN_FILE = "google-oauth-token.json"
DEFAULT_QUEUE_SHEET_NAME = "write_queue_v2"
DEFAULT_SYNC_CONFIG_SHEET_NAME = "sync_config"
DEFAULT_SYNC_ISSUE_MAP_SHEET_NAME = "sync_issue_map"
DEFAULT_SOURCE_PROJECT_KEY = "IWTECH_SYSOP"
DEFAULT_TARGET_PROJECT_KEY = "ICESAO_GENTASK"
SYNC_ISSUE_MAP_HEADERS = [
    "source_project_key",
    "source_issue_key",
    "source_issue_id",
    "source_issue_url",
    "target_project_key",
    "target_issue_key",
    "target_issue_id",
    "target_issue_url",
    "source_updated_at",
    "last_issue_synced_at",
    "sync_status",
    "create_queue_id",
    "last_error_code",
    "last_error_message",
    "note",
]


@dataclass(frozen=True)
class Settings:
    backlog_base_url: str
    backlog_api_key: str
    spreadsheet_id: str
    queue_sheet_name: str
    sync_config_sheet_name: str
    sync_issue_map_sheet_name: str
    google_auth_mode: str
    google_oauth_client_secret_file: str
    google_oauth_token_file: str
    source_project_key: str
    target_project_key: str
    target_project_id: str
    default_issue_type_id: str
    default_priority_id: str
    default_assignee_id: str
    requested_by: str
    max_issues: int
    dry_run: bool
    timeout_seconds: float


class SyncPreparationError(RuntimeError):
    pass


class GoogleSheetsTableClient:
    def __init__(self, settings: Settings) -> None:
        self._service = build_sheets_service(
            auth_mode=settings.google_auth_mode,
            scopes=[SHEETS_SCOPE],
            service_account_file="",
            oauth_client_secret_file=settings.google_oauth_client_secret_file,
            oauth_token_file=settings.google_oauth_token_file,
        )
        self._spreadsheet_id = settings.spreadsheet_id

    def get_rows(self, sheet_name: str, end_column: str) -> list[dict[str, str]]:
        response = self._service.spreadsheets().values().get(
            spreadsheetId=self._spreadsheet_id,
            range=f"{sheet_name}!A:{end_column}",
        ).execute()
        values = response.get("values", [])
        if not values:
            return []

        headers = [str(header).strip() for header in values[0]]
        rows = []
        for raw_row in values[1:]:
            padded = [*raw_row, *([""] * (len(headers) - len(raw_row)))]
            row = dict(zip(headers, [str(value) for value in padded[: len(headers)]], strict=False))
            if any(value.strip() for value in row.values()):
                rows.append(row)
        return rows

    def append_row(self, sheet_name: str, values: list[str]) -> None:
        self._service.spreadsheets().values().append(
            spreadsheetId=self._spreadsheet_id,
            range=f"{sheet_name}!A:A",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [values]},
        ).execute()


class BacklogReadClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.backlog_api_key
        self._client = httpx.Client(
            base_url=settings.backlog_base_url.rstrip("/"),
            timeout=settings.timeout_seconds,
        )

    def get_project(self, project_key: str) -> dict[str, Any]:
        response = self._request("GET", f"/api/v2/projects/{project_key}")
        if not isinstance(response, dict):
            raise SyncPreparationError("Backlog project response was not an object")
        return response

    def list_recent_issues(self, project_id: str, count: int) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            "/api/v2/issues",
            params={
                "projectId[]": [project_id],
                "sort": "updated",
                "order": "desc",
                "count": str(count),
            },
        )
        if not isinstance(response, list):
            raise SyncPreparationError("Backlog issues response was not a list")
        return response

    def get_issue(self, issue_key: str) -> dict[str, Any]:
        response = self._request("GET", f"/api/v2/issues/{issue_key}")
        if not isinstance(response, dict):
            raise SyncPreparationError("Backlog issue response was not an object")
        return response

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        request_params = dict(params or {})
        request_params["apiKey"] = self._api_key
        try:
            response = self._client.request(method, path, params=request_params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SyncPreparationError(f"Backlog API returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SyncPreparationError("Backlog API request failed") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise SyncPreparationError("Backlog API returned invalid JSON") from exc


def get_settings() -> Settings:
    google_auth_mode = os.getenv("GOOGLE_AUTH_MODE", DEFAULT_GOOGLE_AUTH_MODE)
    if google_auth_mode != "user_oauth":
        raise SyncPreparationError("prepare_iwtech_sysop_queue_v2.py expects GOOGLE_AUTH_MODE=user_oauth")

    return Settings(
        backlog_base_url=os.getenv("BACKLOG_BASE_URL", DEFAULT_BACKLOG_BASE_URL),
        backlog_api_key=require_env("BACKLOG_API_KEY"),
        spreadsheet_id=require_env(DEFAULT_SPREADSHEET_ID_ENV),
        queue_sheet_name=os.getenv("WRITE_QUEUE_SHEET_NAME", DEFAULT_QUEUE_SHEET_NAME),
        sync_config_sheet_name=os.getenv("SYNC_CONFIG_SHEET_NAME", DEFAULT_SYNC_CONFIG_SHEET_NAME),
        sync_issue_map_sheet_name=os.getenv("SYNC_ISSUE_MAP_SHEET_NAME", DEFAULT_SYNC_ISSUE_MAP_SHEET_NAME),
        google_auth_mode=google_auth_mode,
        google_oauth_client_secret_file=require_env("GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        google_oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", DEFAULT_GOOGLE_OAUTH_TOKEN_FILE),
        source_project_key=os.getenv("SOURCE_PROJECT_KEY", DEFAULT_SOURCE_PROJECT_KEY),
        target_project_key=os.getenv("TARGET_PROJECT_KEY", DEFAULT_TARGET_PROJECT_KEY),
        target_project_id=os.getenv("TARGET_PROJECT_ID", ""),
        default_issue_type_id=os.getenv("BACKLOG_DEFAULT_ISSUE_TYPE_ID", ""),
        default_priority_id=os.getenv("BACKLOG_DEFAULT_PRIORITY_ID", ""),
        default_assignee_id=os.getenv("BACKLOG_DEFAULT_ASSIGNEE_ID", ""),
        requested_by=os.getenv("SYNC_REQUESTED_BY", "iwtech-sysop-sync"),
        max_issues=int(os.getenv("SYNC_MAX_ISSUES", "20")),
        dry_run=os.getenv("SYNC_DRY_RUN", "false").lower() == "true",
        timeout_seconds=float(os.getenv("BACKLOG_TIMEOUT_SECONDS", "20")),
    )


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SyncPreparationError(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    settings = apply_sync_config(get_settings())
    validate_settings(settings)

    sheets = GoogleSheetsTableClient(settings)
    backlog = BacklogReadClient(settings)

    source_project = backlog.get_project(settings.source_project_key)
    source_project_id = str(source_project.get("id") or "")
    if not source_project_id:
        raise SyncPreparationError(f"Could not resolve source project id: {settings.source_project_key}")

    existing_source_keys = get_existing_source_issue_keys(sheets, settings)
    existing_idempotency_keys = get_existing_idempotency_keys(sheets, settings)

    issues = get_source_issues(backlog, settings, source_project_id)
    appended = 0
    for issue in issues:
        source_issue_key = str(issue.get("issueKey") or "")
        if not source_issue_key:
            continue
        if source_issue_key in existing_source_keys:
            continue

        idempotency_key = f"sync_issue:create:{source_issue_key}"
        if idempotency_key in existing_idempotency_keys:
            continue

        queue_id = build_queue_id(appended + 1)
        queue_row = build_create_issue_queue_row(settings, issue, queue_id, idempotency_key)
        map_row = build_sync_issue_map_row(settings, issue, queue_id)
        if settings.dry_run:
            print(json.dumps({"queue_row": queue_row, "sync_issue_map_row": map_row}, ensure_ascii=False))
        else:
            sheets.append_row(settings.queue_sheet_name, queue_row)
            sheets.append_row(settings.sync_issue_map_sheet_name, map_row)
        appended += 1

    print(f"prepared create_issue rows: {appended}")


def apply_sync_config(settings: Settings) -> Settings:
    return settings


def validate_settings(settings: Settings) -> None:
    missing = []
    if not settings.target_project_id:
        missing.append("TARGET_PROJECT_ID")
    if not settings.default_issue_type_id:
        missing.append("BACKLOG_DEFAULT_ISSUE_TYPE_ID")
    if not settings.default_priority_id:
        missing.append("BACKLOG_DEFAULT_PRIORITY_ID")
    if missing:
        raise SyncPreparationError(f"Missing required create_issue settings: {', '.join(missing)}")


def get_existing_source_issue_keys(sheets: GoogleSheetsTableClient, settings: Settings) -> set[str]:
    rows = sheets.get_rows(settings.sync_issue_map_sheet_name, "O")
    return {
        row.get("source_issue_key", "").strip()
        for row in rows
        if row.get("source_project_key", "").strip() == settings.source_project_key
        and row.get("target_project_key", "").strip() == settings.target_project_key
        and row.get("source_issue_key", "").strip()
    }


def get_existing_idempotency_keys(sheets: GoogleSheetsTableClient, settings: Settings) -> set[str]:
    rows = sheets.get_rows(settings.queue_sheet_name, "AA")
    return {
        row.get("idempotency_key", "").strip()
        for row in rows
        if row.get("idempotency_key", "").strip()
        and row.get("status", "").strip().lower() not in {"cancelled"}
    }


def get_source_issues(
    backlog: BacklogReadClient,
    settings: Settings,
    source_project_id: str,
) -> list[dict[str, Any]]:
    explicit_issue_keys = [
        issue_key.strip()
        for issue_key in os.getenv("SOURCE_ISSUE_KEYS", "").split(",")
        if issue_key.strip()
    ]
    if explicit_issue_keys:
        return [backlog.get_issue(issue_key) for issue_key in explicit_issue_keys]
    return backlog.list_recent_issues(source_project_id, settings.max_issues)


def build_create_issue_queue_row(
    settings: Settings,
    issue: dict[str, Any],
    queue_id: str,
    idempotency_key: str,
) -> list[str]:
    now = datetime.now(UTC).isoformat()
    source_issue_key = str(issue.get("issueKey") or "")
    title = f"[{source_issue_key}] {issue.get('summary') or ''}".strip()
    description = build_synced_issue_description(settings, issue)
    priority_name = get_nested_name(issue, "priority")
    payload = {
        "action": "create_issue",
        "source_project_key": settings.source_project_key,
        "source_issue_key": source_issue_key,
        "source_issue_id": issue.get("id"),
        "source_issue_url": build_issue_url(settings.backlog_base_url, source_issue_key),
        "project_key": settings.target_project_key,
        "project_id": settings.target_project_id,
        "issue_title": title,
        "issue_description": description,
        "issue_type_id": settings.default_issue_type_id,
        "priority_id": settings.default_priority_id,
        "assignee_id": settings.default_assignee_id,
    }
    row = {
        "queue_id": queue_id,
        "requested_at": now,
        "requested_by": settings.requested_by,
        "request_source": "IWTECH_SYSOP sync",
        "project_key": settings.target_project_key,
        "operation_type": "create_issue",
        "target_issue_key": "",
        "issue_title": title,
        "issue_description": description,
        "comment_body": "",
        "new_status_name": "",
        "new_priority_name": priority_name,
        "assignee_name": "",
        "due_date": str(issue.get("dueDate") or ""),
        "category_names": "",
        "custom_fields_json": json.dumps(
            {
                "source_project_key": settings.source_project_key,
                "source_issue_key": source_issue_key,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "request_payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "idempotency_key": idempotency_key,
        "status": "queued",
        "retry_count": "0",
        "last_error_code": "",
        "last_error_message": "",
        "result_summary": "",
        "processed_at": "",
        "processed_by_worker": "",
        "raw_request_text": f"sync source issue {source_issue_key} to {settings.target_project_key}",
        "note": "created by IWTECH_SYSOP pre-queue job",
    }
    return [row.get(header, "") for header in WRITE_QUEUE_V2_HEADERS]


def build_sync_issue_map_row(settings: Settings, issue: dict[str, Any], queue_id: str) -> list[str]:
    source_issue_key = str(issue.get("issueKey") or "")
    row = {
        "source_project_key": settings.source_project_key,
        "source_issue_key": source_issue_key,
        "source_issue_id": str(issue.get("id") or ""),
        "source_issue_url": build_issue_url(settings.backlog_base_url, source_issue_key),
        "target_project_key": settings.target_project_key,
        "target_issue_key": "",
        "target_issue_id": "",
        "target_issue_url": "",
        "source_updated_at": str(issue.get("updated") or ""),
        "last_issue_synced_at": "",
        "sync_status": "queued_create",
        "create_queue_id": queue_id,
        "last_error_code": "",
        "last_error_message": "",
        "note": "waiting for create_issue result reconciliation",
    }
    return [row.get(header, "") for header in SYNC_ISSUE_MAP_HEADERS]


def build_synced_issue_description(settings: Settings, issue: dict[str, Any]) -> str:
    source_issue_key = str(issue.get("issueKey") or "")
    lines = [
        f"Source Backlog issue: {build_issue_url(settings.backlog_base_url, source_issue_key)}",
        f"Source project: {settings.source_project_key}",
        f"Source issue key: {source_issue_key}",
        f"Source status: {get_nested_name(issue, 'status')}",
        f"Source priority: {get_nested_name(issue, 'priority')}",
        f"Source assignee: {get_nested_name(issue, 'assignee')}",
        f"Source created user: {get_nested_name(issue, 'createdUser')}",
        f"Source updated at: {issue.get('updated') or ''}",
        "",
        "---- Source description ----",
        str(issue.get("description") or ""),
    ]
    return "\n".join(lines)


def get_nested_name(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return ""


def build_issue_url(base_url: str, issue_key: str) -> str:
    if not issue_key:
        return ""
    return f"{base_url.rstrip('/').replace('/api/v2', '')}/view/{issue_key}"


def build_queue_id(sequence: int) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = hashlib.sha1(f"{timestamp}:{sequence}".encode("utf-8")).hexdigest()[:6]
    return f"WQV2-IWTECH-{timestamp}-{sequence:03d}-{suffix}"


if __name__ == "__main__":
    main()
