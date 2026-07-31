#!/usr/bin/env python3
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.google_sheets_auth import build_sheets_service
from scripts.prepare_iwtech_sysop_queue_v2 import SYNC_ISSUE_MAP_HEADERS
from scripts.process_write_queue_v2 import HEADERS

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SOURCE_DRIVEN_OPERATIONS = {"change_status", "change_due_date"}
CREATE_RESULT_PATTERN = re.compile(r"issue created: issueKey=(\S+) id=(\S+)")


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


def col(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def ensure_sync_map_headers(service, s: Settings) -> None:
    end_col = col(len(SYNC_ISSUE_MAP_HEADERS))
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.sync_issue_map_sheet_name}!A1:{end_col}1",
    ).execute()
    current = [str(value).strip() for value in (res.get("values", [[]])[0] if res.get("values") else [])]
    if current == SYNC_ISSUE_MAP_HEADERS:
        return
    if current and current != SYNC_ISSUE_MAP_HEADERS[:len(current)]:
        raise RuntimeError("sync_issue_map headers do not match expected prefix")
    if s.dry_run:
        return
    service.spreadsheets().values().update(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.sync_issue_map_sheet_name}!A1:{end_col}1",
        valueInputOption="RAW",
        body={"values": [SYNC_ISSUE_MAP_HEADERS]},
    ).execute()


def read_rows(service, s: Settings, sheet_name: str, headers: list[str]) -> list[tuple[int, dict[str, str]]]:
    end_col = col(len(headers))
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{sheet_name}!A:{end_col}",
    ).execute()
    values = res.get("values", [])
    rows = []
    for row_no, raw in enumerate(values[1:], start=2):
        padded = raw[:len(headers)] + [""] * (len(headers) - len(raw))
        row = dict(zip(headers, padded))
        if any(str(value).strip() for value in row.values()):
            rows.append((row_no, row))
    return rows


def parse_payload(row: dict[str, str]) -> dict[str, Any]:
    raw = str(row.get("request_payload_json") or "").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def successful_create_results(queue_rows: list[tuple[int, dict[str, str]]]) -> dict[str, dict[str, str]]:
    results: dict[str, dict[str, str]] = {}
    for _, row in queue_rows:
        if row.get("status") != "succeeded" or row.get("operation_type") != "create_issue":
            continue
        queue_id = str(row.get("queue_id") or "").strip()
        if not queue_id:
            continue
        match = CREATE_RESULT_PATTERN.search(str(row.get("result_summary") or ""))
        if not match:
            continue
        target_issue_key, target_issue_id = match.groups()
        payload = parse_payload(row)
        results[queue_id] = {
            "source_issue_key": str(payload.get("source_issue_key") or "").strip(),
            "target_issue_key": target_issue_key,
            "target_issue_id": target_issue_id,
            "processed_at": str(row.get("processed_at") or "").strip(),
        }
    return results


def successful_cursor_sources(queue_rows: list[tuple[int, dict[str, str]]]) -> tuple[dict[str, str], dict[str, str], set[str]]:
    comment_cursors: dict[str, str] = {}
    issue_cursors: dict[str, str] = {}
    issue_cursor_sources_missing_payload: set[str] = set()
    for _, row in queue_rows:
        if row.get("status") != "succeeded":
            continue
        payload = parse_payload(row)
        source_issue_key = str(payload.get("source_issue_key") or "").strip()
        if not source_issue_key:
            continue

        operation = row.get("operation_type", "")
        if operation == "add_comment" and row.get("idempotency_key", "").startswith("sync_comment:"):
            created = str(payload.get("source_comment_created") or "").strip()
            if created and created > comment_cursors.get(source_issue_key, ""):
                comment_cursors[source_issue_key] = created
        elif operation in SOURCE_DRIVEN_OPERATIONS:
            updated = str(payload.get("source_issue_updated_at") or "").strip()
            if updated:
                if updated > issue_cursors.get(source_issue_key, ""):
                    issue_cursors[source_issue_key] = updated
            else:
                issue_cursor_sources_missing_payload.add(source_issue_key)
    return comment_cursors, issue_cursors, issue_cursor_sources_missing_payload


def backlog_get(s: Settings, path: str, params: dict[str, Any] | None = None) -> Any:
    request_params = dict(params or {})
    request_params["apiKey"] = s.backlog_api_key
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.get(path, params=request_params)
        res.raise_for_status()
        return res.json()


def source_issue_updated_at(s: Settings, source_issue_key: str) -> str:
    issue = backlog_get(s, f"/api/v2/issues/{source_issue_key}")
    if not isinstance(issue, dict):
        raise RuntimeError(f"Backlog issue response was not an object: {source_issue_key}")
    return str(issue.get("updated") or "").strip()


def update_sync_map_row(service, s: Settings, row_no: int, row: dict[str, str], updates: dict[str, str]) -> None:
    merged = dict(row)
    merged.update(updates)
    service.spreadsheets().values().update(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.sync_issue_map_sheet_name}!A{row_no}:{col(len(SYNC_ISSUE_MAP_HEADERS))}{row_no}",
        valueInputOption="RAW",
        body={"values": [[merged.get(header, "") for header in SYNC_ISSUE_MAP_HEADERS]]},
    ).execute()


def eligible_map_row(s: Settings, row: dict[str, str]) -> bool:
    if row.get("source_project_key") != s.source_project_key:
        return False
    if row.get("target_project_key") and row.get("target_project_key") != s.target_project_key:
        return False
    if row.get("sync_status") != "created":
        return False
    return bool(row.get("source_issue_key") and row.get("target_issue_key"))


def main() -> None:
    s = settings()
    service = get_service(s)
    ensure_sync_map_headers(service, s)

    queue_rows = read_rows(service, s, s.queue_sheet_name, HEADERS)
    create_results = successful_create_results(queue_rows)
    comment_cursors, issue_cursors, issue_cursor_sources_missing_payload = successful_cursor_sources(queue_rows)

    for source_issue_key in sorted(issue_cursor_sources_missing_payload):
        updated = source_issue_updated_at(s, source_issue_key)
        if updated and updated > issue_cursors.get(source_issue_key, ""):
            issue_cursors[source_issue_key] = updated

    updated = 0
    create_reconciled = 0
    cursor_reconciled = 0
    dry_run_events = []
    now = datetime.now(UTC).isoformat()

    for row_no, row in read_rows(service, s, s.sync_issue_map_sheet_name, SYNC_ISSUE_MAP_HEADERS):
        updates: dict[str, str] = {}
        create_queue_id = str(row.get("create_queue_id") or "").strip()
        create_result = create_results.get(create_queue_id)

        if row.get("sync_status") == "queued_create" and create_result:
            source_issue_key = str(row.get("source_issue_key") or "").strip()
            result_source_issue_key = create_result.get("source_issue_key", "")
            if result_source_issue_key and source_issue_key != result_source_issue_key:
                updates.update({
                    "last_error_code": "CREATE_SOURCE_MISMATCH",
                    "last_error_message": f"queue source {result_source_issue_key} does not match map source {source_issue_key}",
                    "note": "create result reconciliation blocked",
                })
            else:
                target_issue_key = create_result["target_issue_key"]
                processed_at = create_result.get("processed_at") or now
                updates.update({
                    "target_issue_key": target_issue_key,
                    "target_issue_id": create_result["target_issue_id"],
                    "target_issue_url": f"{s.backlog_base_url.rstrip('/')}/view/{target_issue_key}",
                    "last_issue_synced_at": processed_at,
                    "sync_status": "created",
                    "last_error_code": "",
                    "last_error_message": "",
                    "note": "create_issue result reconciled",
                })
                create_reconciled += 1

        effective_row = dict(row)
        effective_row.update(updates)
        if eligible_map_row(s, effective_row):
            source_issue_key = effective_row.get("source_issue_key", "")
            comment_cursor = comment_cursors.get(source_issue_key, "")
            issue_cursor = issue_cursors.get(source_issue_key, "")

            if comment_cursor and comment_cursor > effective_row.get("last_comment_synced_at", ""):
                updates["last_comment_synced_at"] = comment_cursor
            if issue_cursor and issue_cursor > effective_row.get("last_issue_synced_at", ""):
                updates["source_updated_at"] = issue_cursor
                updates["last_issue_synced_at"] = issue_cursor

            if comment_cursor or issue_cursor:
                updates.update({
                    "last_error_code": "",
                    "last_error_message": "",
                    "note": "sync cursors reconciled",
                })
                cursor_reconciled += 1

        if not updates:
            continue

        if s.dry_run:
            dry_run_events.append({"row_no": row_no, "source_issue_key": row.get("source_issue_key", ""), "updates": updates})
        else:
            update_sync_map_row(service, s, row_no, row, updates)
        updated += 1

    print(json.dumps({
        "status": "ok",
        "updated": updated,
        "create_reconciled": create_reconciled,
        "cursor_reconciled": cursor_reconciled,
        "dry_run": s.dry_run,
        "events": dry_run_events,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
