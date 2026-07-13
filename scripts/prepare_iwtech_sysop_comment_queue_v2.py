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
    requested_by: str
    max_issues: int
    max_comments_per_issue: int
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
        requested_by=os.getenv("SYNC_REQUESTED_BY", "iwtech-sysop-sync"),
        max_issues=int(os.getenv("SYNC_MAX_ISSUES", "20")),
        max_comments_per_issue=int(os.getenv("SYNC_MAX_COMMENTS_PER_ISSUE", "100")),
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


def source_comments(s: Settings, source_issue_key: str) -> list[dict[str, Any]]:
    comments = backlog_get(
        s,
        f"/api/v2/issues/{source_issue_key}/comments",
        params={"order": "asc", "count": s.max_comments_per_issue},
    )
    if not isinstance(comments, list):
        raise RuntimeError(f"Backlog comments response was not a list: {source_issue_key}")
    return [comment for comment in comments if isinstance(comment, dict)]


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


def build_comment_body(s: Settings, map_row: dict[str, str], comment: dict[str, Any]) -> str:
    source_issue_key = map_row.get("source_issue_key", "")
    source_issue_url = map_row.get("source_issue_url") or issue_url(s.backlog_base_url, source_issue_key)
    created_user = comment.get("createdUser") if isinstance(comment.get("createdUser"), dict) else {}
    author = str(created_user.get("name") or created_user.get("userId") or "")
    content = str(comment.get("content") or "").strip()
    return "\n".join([
        "[IWTECH_SYSOP comment sync]",
        f"Source issue: {source_issue_key}",
        f"Source URL: {source_issue_url}",
        f"Source comment ID: {comment.get('id') or ''}",
        f"Source comment author: {author}",
        f"Source comment created at: {comment.get('created') or ''}",
        "",
        "---- Source comment ----",
        content,
    ])


def build_queue_row(s: Settings, map_row: dict[str, str], comment: dict[str, Any], sequence: int) -> list[str]:
    now = datetime.now(UTC).isoformat()
    source_issue_key = map_row.get("source_issue_key", "")
    target_issue_key = map_row.get("target_issue_key", "")
    comment_id = str(comment.get("id") or "")
    queue_id = build_queue_id(sequence)
    comment_body = build_comment_body(s, map_row, comment)
    payload = {
        "action": "add_comment",
        "target_issue_key": target_issue_key,
        "comment_body": comment_body,
        "source_project_key": s.source_project_key,
        "source_issue_key": source_issue_key,
        "source_comment_id": comment_id,
        "source_comment_created": comment.get("created") or "",
    }
    row = {
        "queue_id": queue_id,
        "requested_at": now,
        "requested_by": s.requested_by,
        "request_source": "IWTECH_SYSOP comment sync",
        "project_key": s.target_project_key,
        "operation_type": "add_comment",
        "target_issue_key": target_issue_key,
        "issue_title": "",
        "issue_description": "",
        "comment_body": comment_body,
        "new_status_name": "",
        "new_priority_name": "",
        "assignee_name": "",
        "due_date": "",
        "category_names": "",
        "custom_fields_json": json.dumps({"source_project_key": s.source_project_key, "source_issue_key": source_issue_key, "source_comment_id": comment_id}, ensure_ascii=False, separators=(",", ":")),
        "request_payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "idempotency_key": f"sync_comment:{source_issue_key}:{comment_id}",
        "status": "queued",
        "retry_count": "0",
        "last_error_code": "",
        "last_error_message": "",
        "result_summary": "",
        "processed_at": "",
        "processed_by_worker": "",
        "raw_request_text": f"sync source comment {source_issue_key}#{comment_id} to {target_issue_key}",
        "note": "created by IWTECH_SYSOP comment pre-queue job",
    }
    return [row.get(header, "") for header in HEADERS]


def build_queue_id(sequence: int) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = hashlib.sha1(f"comment:{timestamp}:{sequence}".encode("utf-8")).hexdigest()[:6]
    return f"WQV2-IWTECH-COMMENT-{timestamp}-{sequence:03d}-{suffix}"


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
    map_rows = read_table(service, s, s.sync_issue_map_sheet_name, SYNC_ISSUE_MAP_HEADERS)
    queue_rows = read_table(service, s, s.queue_sheet_name, HEADERS)
    idempotency_keys = {
        row.get("idempotency_key", "")
        for row in queue_rows
        if row.get("idempotency_key", "") and row.get("status", "") != "cancelled"
    }

    appended = 0
    skipped = 0
    scanned_comments = 0
    queue_appends: list[list[str]] = []
    for map_row in eligible_map_rows(s, map_rows):
        for comment in source_comments(s, map_row["source_issue_key"]):
            comment_id = str(comment.get("id") or "")
            content = str(comment.get("content") or "").strip()
            if not comment_id or not content:
                skipped += 1
                continue
            idempotency_key = f"sync_comment:{map_row['source_issue_key']}:{comment_id}"
            scanned_comments += 1
            if idempotency_key in idempotency_keys:
                skipped += 1
                continue
            queue_row = build_queue_row(s, map_row, comment, appended + 1)
            if s.dry_run:
                print(json.dumps({"queue_row": queue_row}, ensure_ascii=False))
            else:
                queue_appends.append(queue_row)
            idempotency_keys.add(idempotency_key)
            appended += 1

    if not s.dry_run:
        append_rows(service, s, s.queue_sheet_name, queue_appends)

    print(json.dumps({
        "status": "ok",
        "prepared_add_comment_rows": appended,
        "scanned_comments": scanned_comments,
        "skipped": skipped,
        "dry_run": s.dry_run,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
