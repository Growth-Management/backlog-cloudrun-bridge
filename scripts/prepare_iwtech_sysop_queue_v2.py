#!/usr/bin/env python3
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.google_sheets_auth import build_sheets_service
from scripts.process_write_queue_v2 import HEADERS

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

SYNC_ISSUE_MAP_HEADERS = [
    "source_project_key", "source_issue_key", "source_issue_id", "source_issue_url",
    "target_project_key", "target_issue_key", "target_issue_id", "target_issue_url",
    "source_updated_at", "last_issue_synced_at", "sync_status", "create_queue_id",
    "last_error_code", "last_error_message", "note",
]


@dataclass(frozen=True)
class Settings:
    backlog_base_url: str
    backlog_api_key: str
    spreadsheet_id: str
    google_auth_mode: str
    google_credentials: str
    google_oauth_client_secret_file: str
    google_oauth_token_file: str
    queue_sheet_name: str
    sync_issue_map_sheet_name: str
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


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def settings() -> Settings:
    return Settings(
        backlog_base_url=os.getenv("BACKLOG_BASE_URL", "https://ice.backlog.jp"),
        backlog_api_key=require_env("BACKLOG_API_KEY"),
        spreadsheet_id=require_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
        google_auth_mode=os.getenv("GOOGLE_AUTH_MODE", "user_oauth"),
        google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        google_oauth_client_secret_file=require_env("GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        google_oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", r"C:\backlog-sync\config\google-oauth-token.json"),
        queue_sheet_name=os.getenv("WRITE_QUEUE_SHEET_NAME", "write_queue_v2"),
        sync_issue_map_sheet_name=os.getenv("SYNC_ISSUE_MAP_SHEET_NAME", "sync_issue_map"),
        source_project_key=os.getenv("SOURCE_PROJECT_KEY", "IWTECH_SYSOP"),
        target_project_key=os.getenv("TARGET_PROJECT_KEY", "ICESAO_GENTASK"),
        target_project_id=require_env("TARGET_PROJECT_ID"),
        default_issue_type_id=require_env("BACKLOG_DEFAULT_ISSUE_TYPE_ID"),
        default_priority_id=os.getenv("BACKLOG_DEFAULT_PRIORITY_ID", "3"),
        default_assignee_id=os.getenv("BACKLOG_DEFAULT_ASSIGNEE_ID", ""),
        requested_by=os.getenv("SYNC_REQUESTED_BY", "iwtech-sysop-sync"),
        max_issues=int(os.getenv("SYNC_MAX_ISSUES", "20")),
        dry_run=os.getenv("SYNC_DRY_RUN", "false").lower() == "true",
        timeout_seconds=float(os.getenv("BACKLOG_TIMEOUT_SECONDS", "20")),
    )


def get_service(s: Settings):
    return build_sheets_service(
        auth_mode=s.google_auth_mode,
        scopes=[SHEETS_SCOPE],
        service_account_file=s.google_credentials,
        oauth_client_secret_file=s.google_oauth_client_secret_file,
        oauth_token_file=s.google_oauth_token_file,
    )


def read_table(service, s: Settings, sheet_name: str, headers: list[str]) -> list[dict[str, str]]:
    end_col = col(len(headers))
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{sheet_name}!A:{end_col}",
    ).execute()
    values = res.get("values", [])
    if not values:
        return []
    sheet_headers = [str(value).strip() for value in values[0][:len(headers)]]
    rows = []
    for raw in values[1:]:
        padded = raw[:len(sheet_headers)] + [""] * (len(sheet_headers) - len(raw))
        row = dict(zip(sheet_headers, padded))
        if any(str(value).strip() for value in row.values()):
            rows.append(row)
    return rows


def append_row(service, s: Settings, sheet_name: str, values: list[str]) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=s.spreadsheet_id,
        range=f"{sheet_name}!A:A",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()


def backlog_get(s: Settings, path: str, params: dict[str, Any] | None = None) -> Any:
    request_params = dict(params or {})
    request_params["apiKey"] = s.backlog_api_key
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.get(path, params=request_params)
        res.raise_for_status()
        return res.json()


def source_issues(s: Settings) -> list[dict[str, Any]]:
    issue_keys = [key.strip() for key in os.getenv("SOURCE_ISSUE_KEYS", "").split(",") if key.strip()]
    if issue_keys:
        return [backlog_get(s, f"/api/v2/issues/{issue_key}") for issue_key in issue_keys]

    project = backlog_get(s, f"/api/v2/projects/{s.source_project_key}")
    project_id = project.get("id")
    if not project_id:
        raise RuntimeError(f"source project id not found: {s.source_project_key}")
    issues = backlog_get(
        s,
        "/api/v2/issues",
        params={"projectId[]": [project_id], "sort": "updated", "order": "desc", "count": s.max_issues},
    )
    if not isinstance(issues, list):
        raise RuntimeError("Backlog issues response was not a list")
    return [issue for issue in issues if isinstance(issue, dict)]


def build_rows(s: Settings, issue: dict[str, Any], sequence: int) -> tuple[list[str], list[str]]:
    now = datetime.now(UTC).isoformat()
    source_issue_key = str(issue.get("issueKey") or "")
    queue_id = build_queue_id(sequence)
    title = f"[{source_issue_key}] {issue.get('summary') or ''}".strip()
    source_url = issue_url(s.backlog_base_url, source_issue_key)
    description = "\n".join([
        f"Source Backlog issue: {source_url}",
        f"Source project: {s.source_project_key}",
        f"Source issue key: {source_issue_key}",
        f"Source status: {nested_name(issue, 'status')}",
        f"Source priority: {nested_name(issue, 'priority')}",
        f"Source assignee: {nested_name(issue, 'assignee')}",
        f"Source created user: {nested_name(issue, 'createdUser')}",
        f"Source updated at: {issue.get('updated') or ''}",
        "",
        "---- Source description ----",
        str(issue.get("description") or ""),
    ])
    payload = {
        "action": "create_issue",
        "source_project_key": s.source_project_key,
        "source_issue_key": source_issue_key,
        "source_issue_id": issue.get("id"),
        "source_issue_url": source_url,
        "project_key": s.target_project_key,
        "project_id": s.target_project_id,
        "issue_title": title,
        "issue_description": description,
        "issue_type_id": s.default_issue_type_id,
        "priority_id": s.default_priority_id,
        "assignee_id": s.default_assignee_id,
        "due_date": issue.get("dueDate") or "",
    }
    queue = {
        "queue_id": queue_id,
        "requested_at": now,
        "requested_by": s.requested_by,
        "request_source": "IWTECH_SYSOP sync",
        "project_key": s.target_project_key,
        "operation_type": "create_issue",
        "target_issue_key": "",
        "issue_title": title,
        "issue_description": description,
        "comment_body": "",
        "new_status_name": "",
        "new_priority_name": nested_name(issue, "priority"),
        "assignee_name": "",
        "due_date": issue.get("dueDate") or "",
        "category_names": "",
        "custom_fields_json": json.dumps({"source_project_key": s.source_project_key, "source_issue_key": source_issue_key}, ensure_ascii=False, separators=(",", ":")),
        "request_payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "idempotency_key": f"sync_issue:create:{source_issue_key}",
        "status": "queued",
        "retry_count": "0",
        "last_error_code": "",
        "last_error_message": "",
        "result_summary": "",
        "processed_at": "",
        "processed_by_worker": "",
        "raw_request_text": f"sync source issue {source_issue_key} to {s.target_project_key}",
        "note": "created by IWTECH_SYSOP pre-queue job",
    }
    mapping = {
        "source_project_key": s.source_project_key,
        "source_issue_key": source_issue_key,
        "source_issue_id": str(issue.get("id") or ""),
        "source_issue_url": source_url,
        "target_project_key": s.target_project_key,
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
    return [queue.get(header, "") for header in HEADERS], [mapping.get(header, "") for header in SYNC_ISSUE_MAP_HEADERS]


def nested_name(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return ""


def issue_url(base_url: str, issue_key: str) -> str:
    if not issue_key:
        return ""
    return f"{base_url.rstrip('/')}/view/{issue_key}"


def build_queue_id(sequence: int) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = hashlib.sha1(f"{timestamp}:{sequence}".encode("utf-8")).hexdigest()[:6]
    return f"WQV2-IWTECH-{timestamp}-{sequence:03d}-{suffix}"


def col(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main() -> None:
    s = settings()
    service = get_service(s)
    existing_map = read_table(service, s, s.sync_issue_map_sheet_name, SYNC_ISSUE_MAP_HEADERS)
    existing_queue = read_table(service, s, s.queue_sheet_name, HEADERS)
    mapped_keys = {row.get("source_issue_key", "") for row in existing_map if row.get("source_issue_key", "")}
    idempotency_keys = {row.get("idempotency_key", "") for row in existing_queue if row.get("idempotency_key", "") and row.get("status", "") != "cancelled"}

    appended = 0
    for issue in source_issues(s):
        source_issue_key = str(issue.get("issueKey") or "")
        if not source_issue_key:
            continue
        if source_issue_key in mapped_keys:
            continue
        if f"sync_issue:create:{source_issue_key}" in idempotency_keys:
            continue
        queue_row, map_row = build_rows(s, issue, appended + 1)
        if s.dry_run:
            print(json.dumps({"queue_row": queue_row, "sync_issue_map_row": map_row}, ensure_ascii=False))
        else:
            append_row(service, s, s.queue_sheet_name, queue_row)
            append_row(service, s, s.sync_issue_map_sheet_name, map_row)
        appended += 1

    print(json.dumps({"status": "ok", "prepared_create_issue_rows": appended, "dry_run": s.dry_run}, ensure_ascii=False))


if __name__ == "__main__":
    main()
