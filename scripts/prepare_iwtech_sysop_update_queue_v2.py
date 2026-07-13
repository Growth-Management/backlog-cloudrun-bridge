#!/usr/bin/env python3
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.google_sheets_auth import build_sheets_service
from scripts.prepare_iwtech_sysop_queue_v2 import SYNC_ISSUE_MAP_HEADERS
from scripts.process_write_queue_v2 import HEADERS

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


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
    fixed_assignee_name: str
    sync_due_date: bool
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
        fixed_assignee_name=os.getenv("SYNC_FIXED_ASSIGNEE_NAME", "").strip(),
        sync_due_date=os.getenv("SYNC_DUE_DATE", "true").lower() in ("1", "true", "yes"),
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


def append_rows(service, s: Settings, sheet_name: str, rows: list[list[str]]) -> None:
    if not rows:
        return
    service.spreadsheets().values().append(
        spreadsheetId=s.spreadsheet_id,
        range=f"{sheet_name}!A:A",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def backlog_get(s: Settings, path: str, params: dict[str, Any] | None = None) -> Any:
    request_params = dict(params or {})
    request_params["apiKey"] = s.backlog_api_key
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.get(path, params=request_params)
        res.raise_for_status()
        return res.json()


def source_issue(s: Settings, source_issue_key: str) -> dict[str, Any]:
    issue = backlog_get(s, f"/api/v2/issues/{source_issue_key}")
    if not isinstance(issue, dict):
        raise RuntimeError(f"Backlog issue response was not an object: {source_issue_key}")
    return issue


def eligible_map_rows(s: Settings, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    explicit_keys = {key.strip() for key in os.getenv("SOURCE_ISSUE_KEYS", "").split(",") if key.strip()}
    selected = []
    for row in rows:
        if row.get("source_project_key") != s.source_project_key:
            continue
        if row.get("target_project_key") and row.get("target_project_key") != s.target_project_key:
            continue
        if row.get("sync_status") != "created":
            continue
        if not row.get("source_issue_key") or not row.get("target_issue_key"):
            continue
        if explicit_keys and row.get("source_issue_key") not in explicit_keys:
            continue
        selected.append(row)
        if len(selected) >= s.max_issues:
            break
    return selected


def normalize_due_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10]


def build_assignee_row(s: Settings, map_row: dict[str, str], sequence: int) -> list[str]:
    now = datetime.now(UTC).isoformat()
    source_issue_key = map_row["source_issue_key"]
    target_issue_key = map_row["target_issue_key"]
    queue_id = build_queue_id("ASSIGNEE", sequence)
    payload = {
        "action": "change_assignee",
        "target_issue_key": target_issue_key,
        "assignee_name": s.fixed_assignee_name,
        "source_project_key": s.source_project_key,
        "source_issue_key": source_issue_key,
    }
    row = {
        "queue_id": queue_id,
        "requested_at": now,
        "requested_by": s.requested_by,
        "request_source": "IWTECH_SYSOP update sync",
        "project_key": s.target_project_key,
        "operation_type": "change_assignee",
        "target_issue_key": target_issue_key,
        "assignee_name": s.fixed_assignee_name,
        "request_payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "idempotency_key": f"sync_assignee:{source_issue_key}:{target_issue_key}:{s.fixed_assignee_name}",
        "status": "queued",
        "retry_count": "0",
        "raw_request_text": f"sync fixed assignee {s.fixed_assignee_name} to {target_issue_key}",
        "note": "created by IWTECH_SYSOP update pre-queue job",
    }
    return [row.get(header, "") for header in HEADERS]


def build_due_date_row(s: Settings, map_row: dict[str, str], issue: dict[str, Any], sequence: int) -> list[str] | None:
    due_date = normalize_due_date(issue.get("dueDate"))
    if not due_date:
        return None
    now = datetime.now(UTC).isoformat()
    source_issue_key = map_row["source_issue_key"]
    target_issue_key = map_row["target_issue_key"]
    queue_id = build_queue_id("DUEDATE", sequence)
    payload = {
        "action": "change_due_date",
        "target_issue_key": target_issue_key,
        "due_date": due_date,
        "source_project_key": s.source_project_key,
        "source_issue_key": source_issue_key,
    }
    row = {
        "queue_id": queue_id,
        "requested_at": now,
        "requested_by": s.requested_by,
        "request_source": "IWTECH_SYSOP update sync",
        "project_key": s.target_project_key,
        "operation_type": "change_due_date",
        "target_issue_key": target_issue_key,
        "due_date": due_date,
        "request_payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "idempotency_key": f"sync_due_date:{source_issue_key}:{target_issue_key}:{due_date}",
        "status": "queued",
        "retry_count": "0",
        "raw_request_text": f"sync due date {due_date} to {target_issue_key}",
        "note": "created by IWTECH_SYSOP update pre-queue job",
    }
    return [row.get(header, "") for header in HEADERS]


def build_queue_id(kind: str, sequence: int) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = hashlib.sha1(f"{kind}:{timestamp}:{sequence}".encode("utf-8")).hexdigest()[:6]
    return f"WQV2-IWTECH-{kind}-{timestamp}-{sequence:03d}-{suffix}"


def col(index: int) -> str:
    result = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def main() -> None:
    s = settings()
    service = get_service(s)
    map_rows = read_table(service, s, s.sync_issue_map_sheet_name, SYNC_ISSUE_MAP_HEADERS)
    queue_rows = read_table(service, s, s.queue_sheet_name, HEADERS)
    idempotency_keys = {
        row.get("idempotency_key", "")
        for row in queue_rows
        if row.get("idempotency_key", "") and row.get("status", "") != "cancelled"
    }

    queue_appends: list[list[str]] = []
    assignee_rows = 0
    due_date_rows = 0
    skipped = 0
    sequence = 0

    for map_row in eligible_map_rows(s, map_rows):
        source_issue_key = map_row["source_issue_key"]
        target_issue_key = map_row["target_issue_key"]

        if s.fixed_assignee_name:
            idempotency_key = f"sync_assignee:{source_issue_key}:{target_issue_key}:{s.fixed_assignee_name}"
            if idempotency_key in idempotency_keys:
                skipped += 1
            else:
                sequence += 1
                row = build_assignee_row(s, map_row, sequence)
                if s.dry_run:
                    print(json.dumps({"queue_row": row}, ensure_ascii=False))
                else:
                    queue_appends.append(row)
                idempotency_keys.add(idempotency_key)
                assignee_rows += 1

        if s.sync_due_date:
            issue = source_issue(s, source_issue_key)
            due_date = normalize_due_date(issue.get("dueDate"))
            idempotency_key = f"sync_due_date:{source_issue_key}:{target_issue_key}:{due_date}"
            if not due_date:
                skipped += 1
            elif idempotency_key in idempotency_keys:
                skipped += 1
            else:
                sequence += 1
                row = build_due_date_row(s, map_row, issue, sequence)
                if row is None:
                    skipped += 1
                    continue
                if s.dry_run:
                    print(json.dumps({"queue_row": row}, ensure_ascii=False))
                else:
                    queue_appends.append(row)
                idempotency_keys.add(idempotency_key)
                due_date_rows += 1

    if not s.dry_run:
        append_rows(service, s, s.queue_sheet_name, queue_appends)

    print(json.dumps({
        "status": "ok",
        "prepared_assignee_rows": assignee_rows,
        "prepared_due_date_rows": due_date_rows,
        "skipped": skipped,
        "dry_run": s.dry_run,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
