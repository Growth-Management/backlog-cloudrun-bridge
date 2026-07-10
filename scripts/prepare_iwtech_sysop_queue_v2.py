"""Prepare create_issue rows for syncing IWTECH_SYSOP into write_queue_v2.

This script is intentionally a pre-processor. It reads Backlog issues from a source
project, normalizes them into write_queue_v2 create_issue rows, and records the
source-to-target tracking state in sync_issue_map. The actual Backlog write is
still handled by process_write_queue_v2.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from scripts.google_sheets_auth import build_sheets_service
from scripts.process_write_queue_v2 import HEADERS

SYNC_ISSUE_MAP_HEADERS = [
    "source_project_key",
    "source_issue_key",
    "source_issue_id",
    "source_updated_at",
    "target_project_key",
    "target_issue_key",
    "target_issue_id",
    "target_issue_url",
    "create_queue_id",
    "last_issue_synced_at",
    "last_comment_synced_at",
    "sync_status",
    "last_error",
    "note",
]


@dataclass(frozen=True)
class Settings:
    api_key: str
    spreadsheet_id: str
    client_secret_file: str
    token_file: str
    queue_sheet_name: str
    map_sheet_name: str
    source_project_key: str
    target_project_key: str
    target_project_id: str
    default_issue_type_id: str
    default_priority_id: str
    default_assignee_id: str
    requested_by: str
    max_issues: int
    dry_run: bool


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def get_settings() -> Settings:
    api_key = env("BACKLOG_API_KEY")
    spreadsheet_id = env("GOOGLE_SHEETS_SPREADSHEET_ID")
    client_secret_file = env("GOOGLE_OAUTH_CLIENT_SECRET_FILE")
    token_file = env("GOOGLE_OAUTH_TOKEN_FILE", "token.json")
    target_project_id = env("TARGET_PROJECT_ID")
    default_issue_type_id = env("BACKLOG_DEFAULT_ISSUE_TYPE_ID")
    max_issues_raw = env("SYNC_MAX_ISSUES", "100")

    missing = []
    for name, value in [
        ("BACKLOG_API_KEY", api_key),
        ("GOOGLE_SHEETS_SPREADSHEET_ID", spreadsheet_id),
        ("GOOGLE_OAUTH_CLIENT_SECRET_FILE", client_secret_file),
        ("TARGET_PROJECT_ID", target_project_id),
        ("BACKLOG_DEFAULT_ISSUE_TYPE_ID", default_issue_type_id),
    ]:
        if not value:
            missing.append(name)
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))

    try:
        max_issues = int(max_issues_raw)
    except ValueError as exc:
        raise RuntimeError("SYNC_MAX_ISSUES must be an integer") from exc

    return Settings(
        api_key=api_key,
        spreadsheet_id=spreadsheet_id,
        client_secret_file=client_secret_file,
        token_file=token_file,
        queue_sheet_name=env("WRITE_QUEUE_SHEET_NAME", "write_queue_v2"),
        map_sheet_name=env("SYNC_ISSUE_MAP_SHEET_NAME", "sync_issue_map"),
        source_project_key=env("SOURCE_PROJECT_KEY", "IWTECH_SYSOP"),
        target_project_key=env("TARGET_PROJECT_KEY", ""),
        target_project_id=target_project_id,
        default_issue_type_id=default_issue_type_id,
        default_priority_id=env("BACKLOG_DEFAULT_PRIORITY_ID", "3"),
        default_assignee_id=env("BACKLOG_DEFAULT_ASSIGNEE_ID", ""),
        requested_by=env("SYNC_REQUESTED_BY", "iwtech_sysop_prequeue"),
        max_issues=max_issues,
        dry_run=env("SYNC_DRY_RUN", "false").lower() in ("1", "true", "yes"),
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def backlog_base_url(api_key: str) -> str:
    space = api_key.split(":", 1)[0]
    if not space:
        raise RuntimeError("BACKLOG_API_KEY must be formatted as '<space>:<api-key>'")
    return f"https://{space}.backlog.com/api/v2"


def backlog_api_token(api_key: str) -> str:
    parts = api_key.split(":", 1)
    return parts[1] if len(parts) == 2 else api_key


def rows_to_dicts(values: list[list[str]], headers: list[str]) -> list[dict[str, str]]:
    rows = []
    for row in values[1:]:
        item = {}
        for i, header in enumerate(headers):
            item[header] = row[i] if i < len(row) else ""
        rows.append(item)
    return rows


def ensure_sheet_headers(service: Any, spreadsheet_id: str, sheet_name: str, headers: list[str]) -> None:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!1:1",
    ).execute()
    current = result.get("values", [])
    if current and current[0][: len(headers)] == headers:
        return
    if current and any(current[0]):
        raise RuntimeError(
            f"{sheet_name} has unexpected headers. Expected first columns: {headers}"
        )
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()


def read_sheet(service: Any, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:ZZ",
    ).execute()
    return result.get("values", [])


def append_rows(service: Any, spreadsheet_id: str, sheet_name: str, rows: list[list[str]]) -> None:
    if not rows:
        return
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:ZZ",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def fetch_source_issues(settings: Settings) -> list[dict[str, Any]]:
    explicit_keys = [x.strip() for x in env("SOURCE_ISSUE_KEYS").split(",") if x.strip()]
    base_url = backlog_base_url(settings.api_key)
    token = backlog_api_token(settings.api_key)
    session = requests.Session()
    session.params = {"apiKey": token}

    issues: list[dict[str, Any]] = []
    if explicit_keys:
        for issue_key in explicit_keys[: settings.max_issues]:
            response = session.get(f"{base_url}/issues/{issue_key}", timeout=30)
            response.raise_for_status()
            issues.append(response.json())
        return issues

    offset = 0
    count = min(100, settings.max_issues)
    while len(issues) < settings.max_issues:
        params = {
            "projectId[]": settings.source_project_key,
            "count": min(count, settings.max_issues - len(issues)),
            "offset": offset,
            "sort": "updated",
            "order": "asc",
        }
        response = session.get(f"{base_url}/issues", params=params, timeout=30)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < params["count"]:
            break
        offset += len(batch)
    return issues


def short_text(value: Any, limit: int = 2000) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n... [truncated]"


def make_payload(settings: Settings, issue: dict[str, Any]) -> dict[str, Any]:
    issue_key = str(issue.get("issueKey") or "")
    source_url = f"https://{settings.api_key.split(':', 1)[0]}.backlog.com/view/{issue_key}"
    description = short_text(issue.get("description"), 8000)
    if description:
        description = f"{description}\n\n---\nImported from {source_url}"
    else:
        description = f"Imported from {source_url}"

    payload: dict[str, Any] = {
        "action": "create_issue",
        "project_id": settings.target_project_id,
        "issue_title": str(issue.get("summary") or f"Imported issue {issue_key}"),
        "issue_description": description,
        "issue_type_id": settings.default_issue_type_id,
        "priority_id": settings.default_priority_id,
        "source_project_key": settings.source_project_key,
        "source_issue_key": issue_key,
        "source_issue_id": str(issue.get("id") or ""),
        "source_updated_at": str(issue.get("updated") or ""),
    }
    if settings.default_assignee_id:
        payload["assignee_id"] = settings.default_assignee_id
    return payload


def make_idempotency_key(source_project_key: str, source_issue_key: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"create_issue:{source_project_key}:{source_issue_key}:{digest}"


def make_queue_row(settings: Settings, issue: dict[str, Any], request_id: str) -> tuple[list[str], dict[str, Any], str]:
    payload = make_payload(settings, issue)
    issue_key = str(issue.get("issueKey") or "")
    idempotency_key = make_idempotency_key(settings.source_project_key, issue_key, payload)
    created_at = now_iso()
    row_by_header = {
        "request_id": request_id,
        "requested_at": created_at,
        "requested_by": settings.requested_by,
        "operation_type": "create_issue",
        "target_type": "issue",
        "target_id": issue_key,
        "request_payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "idempotency_key": idempotency_key,
        "status": "queued",
        "locked_by": "",
        "locked_at": "",
        "attempt_count": "0",
        "next_retry_at": "",
        "last_error_code": "",
        "last_error_message": "",
        "result_summary": "",
        "processed_at": "",
        "backlog_request_id": "",
        "source_system": "iwtech_sysop_prequeue",
        "note": "prepared from IWTECH_SYSOP",
    }
    return [row_by_header.get(header, "") for header in HEADERS], payload, idempotency_key


def make_map_row(settings: Settings, issue: dict[str, Any], request_id: str) -> list[str]:
    row_by_header = {
        "source_project_key": settings.source_project_key,
        "source_issue_key": str(issue.get("issueKey") or ""),
        "source_issue_id": str(issue.get("id") or ""),
        "source_updated_at": str(issue.get("updated") or ""),
        "target_project_key": settings.target_project_key,
        "target_issue_key": "",
        "target_issue_id": "",
        "target_issue_url": "",
        "create_queue_id": request_id,
        "last_issue_synced_at": "",
        "last_comment_synced_at": "",
        "sync_status": "queued_create",
        "last_error": "",
        "note": "create_issue queued",
    }
    return [row_by_header.get(header, "") for header in SYNC_ISSUE_MAP_HEADERS]


def main() -> int:
    settings = get_settings()
    service = build_sheets_service(settings.client_secret_file, settings.token_file)
    ensure_sheet_headers(service, settings.spreadsheet_id, settings.queue_sheet_name, HEADERS)
    ensure_sheet_headers(service, settings.spreadsheet_id, settings.map_sheet_name, SYNC_ISSUE_MAP_HEADERS)

    queue_values = read_sheet(service, settings.spreadsheet_id, settings.queue_sheet_name)
    map_values = read_sheet(service, settings.spreadsheet_id, settings.map_sheet_name)
    queue_rows = rows_to_dicts(queue_values, HEADERS) if queue_values else []
    map_rows = rows_to_dicts(map_values, SYNC_ISSUE_MAP_HEADERS) if map_values else []

    existing_source_keys = {
        row.get("source_issue_key", "")
        for row in map_rows
        if row.get("source_project_key") == settings.source_project_key
        and row.get("sync_status") not in ("", "ignored", "reset")
    }
    existing_idempotency = {row.get("idempotency_key", "") for row in queue_rows if row.get("idempotency_key")}

    issues = fetch_source_issues(settings)
    queue_appends: list[list[str]] = []
    map_appends: list[list[str]] = []
    skipped = 0

    for issue in issues:
        issue_key = str(issue.get("issueKey") or "")
        if not issue_key or issue_key in existing_source_keys:
            skipped += 1
            continue
        request_id = str(uuid.uuid4())
        queue_row, _payload, idempotency_key = make_queue_row(settings, issue, request_id)
        if idempotency_key in existing_idempotency:
            skipped += 1
            continue
        queue_appends.append(queue_row)
        map_appends.append(make_map_row(settings, issue, request_id))
        existing_idempotency.add(idempotency_key)
        existing_source_keys.add(issue_key)

    if settings.dry_run:
        print(f"DRY RUN: would append queue_rows={len(queue_appends)} map_rows={len(map_appends)} skipped={skipped}")
        return 0

    append_rows(service, settings.spreadsheet_id, settings.queue_sheet_name, queue_appends)
    append_rows(service, settings.spreadsheet_id, settings.map_sheet_name, map_appends)
    print(f"Appended queue_rows={len(queue_appends)} map_rows={len(map_appends)} skipped={skipped}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
