#!/usr/bin/env python3
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from scripts.google_sheets_auth import build_sheets_service
from scripts.process_write_queue_v2 import HEADERS
from scripts.prepare_iwtech_sysop_queue_v2 import SYNC_ISSUE_MAP_HEADERS

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
RESULT_COLUMNS = [
    "target_issue_key", "target_issue_id", "target_issue_url", "last_issue_synced_at",
    "sync_status", "last_error_code", "last_error_message", "note",
]


@dataclass(frozen=True)
class Settings:
    spreadsheet_id: str
    google_auth_mode: str
    google_credentials: str
    google_oauth_client_secret_file: str
    google_oauth_token_file: str
    backlog_base_url: str
    queue_sheet_name: str
    sync_issue_map_sheet_name: str
    dry_run: bool


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def settings() -> Settings:
    return Settings(
        spreadsheet_id=require_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
        google_auth_mode=os.getenv("GOOGLE_AUTH_MODE", "user_oauth"),
        google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        google_oauth_client_secret_file=require_env("GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        google_oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", r"C:\backlog-sync\config\google-oauth-token.json"),
        backlog_base_url=os.getenv("BACKLOG_BASE_URL", "https://ice.backlog.jp"),
        queue_sheet_name=os.getenv("WRITE_QUEUE_SHEET_NAME", "write_queue_v2"),
        sync_issue_map_sheet_name=os.getenv("SYNC_ISSUE_MAP_SHEET_NAME", "sync_issue_map"),
        dry_run=os.getenv("SYNC_DRY_RUN", "false").lower() == "true",
    )


def get_service(s: Settings):
    return build_sheets_service(
        auth_mode=s.google_auth_mode,
        scopes=[SHEETS_SCOPE],
        service_account_file=s.google_credentials,
        oauth_client_secret_file=s.google_oauth_client_secret_file,
        oauth_token_file=s.google_oauth_token_file,
    )


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


def update_sync_map_result(service, s: Settings, row_no: int, values: list[str]) -> None:
    start = col(SYNC_ISSUE_MAP_HEADERS.index(RESULT_COLUMNS[0]) + 1)
    end = col(SYNC_ISSUE_MAP_HEADERS.index(RESULT_COLUMNS[-1]) + 1)
    service.spreadsheets().values().update(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.sync_issue_map_sheet_name}!{start}{row_no}:{end}{row_no}",
        valueInputOption="RAW",
        body={"values": [values]},
    ).execute()


def parse_created_issue(summary: str) -> tuple[str, str]:
    issue_match = re.search(r"issueKey=([A-Z0-9_]+-\d+)", summary or "")
    id_match = re.search(r"\bid=([0-9]+)", summary or "")
    return (issue_match.group(1) if issue_match else "", id_match.group(1) if id_match else "")


def issue_url(base_url: str, issue_key: str) -> str:
    if not issue_key:
        return ""
    return f"{base_url.rstrip('/')}/view/{issue_key}"


def col(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main() -> None:
    s = settings()
    service = get_service(s)
    queue_by_id = {
        row.get("queue_id", ""): row
        for _, row in read_rows(service, s, s.queue_sheet_name, HEADERS)
        if row.get("queue_id", "")
    }

    updated = 0
    dry_run_events = []
    now = datetime.now(UTC).isoformat()
    for row_no, row in read_rows(service, s, s.sync_issue_map_sheet_name, SYNC_ISSUE_MAP_HEADERS):
        if row.get("sync_status", "") not in ("queued_create", "create_failed", "create_on_hold"):
            continue
        queue_id = row.get("create_queue_id", "")
        queue_row = queue_by_id.get(queue_id)
        if not queue_row:
            continue

        queue_status = queue_row.get("status", "")
        values = None
        if queue_status == "succeeded":
            issue_key, issue_id = parse_created_issue(queue_row.get("result_summary", ""))
            if not issue_key:
                values = ["", "", "", "", "on_hold", "TARGET_ISSUE_KEY_NOT_FOUND", "Could not parse created issue key from result_summary", "check write_queue_v2 result_summary"]
            else:
                values = [issue_key, issue_id, issue_url(s.backlog_base_url, issue_key), now, "created", "", "", "create_issue result reconciled"]
        elif queue_status == "failed":
            values = ["", "", "", now, "create_failed", queue_row.get("last_error_code", ""), queue_row.get("last_error_message", ""), "create_issue queue failed"]
        elif queue_status == "on_hold":
            values = ["", "", "", now, "create_on_hold", queue_row.get("last_error_code", ""), queue_row.get("last_error_message", ""), "create_issue queue is on_hold"]

        if values is None:
            continue
        if s.dry_run:
            dry_run_events.append({"row_no": row_no, "create_queue_id": queue_id, "values": values})
        else:
            update_sync_map_result(service, s, row_no, values)
        updated += 1

    print(json.dumps({"status": "ok", "updated": updated, "dry_run": s.dry_run, "events": dry_run_events}, ensure_ascii=False))


if __name__ == "__main__":
    main()
