#!/usr/bin/env python3
import json
import os
from collections import Counter
from dataclasses import dataclass

from scripts.google_sheets_auth import build_sheets_service
from scripts.process_write_queue_v2 import HEADERS, col

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
ATTENTION_STATUSES = {"queued", "processing", "failed", "on_hold"}


@dataclass(frozen=True)
class Settings:
    spreadsheet_id: str
    google_auth_mode: str
    google_credentials: str
    google_oauth_client_secret_file: str
    google_oauth_token_file: str
    queue_sheet_name: str
    details_limit: int
    fail_on_attention: bool
    allowed_attention_queue_ids: set[str]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def settings() -> Settings:
    allowed_attention_queue_ids = {
        value.strip()
        for value in os.getenv("CHECK_ALLOWED_ATTENTION_QUEUE_IDS", "").split(",")
        if value.strip()
    }
    return Settings(
        spreadsheet_id=require_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
        google_auth_mode=os.getenv("GOOGLE_AUTH_MODE", "user_oauth"),
        google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        google_oauth_client_secret_file=require_env("GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        google_oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", r"C:\backlog-sync\config\google-oauth-token.json"),
        queue_sheet_name=os.getenv("WRITE_QUEUE_SHEET_NAME", "write_queue_v2"),
        details_limit=int(os.getenv("CHECK_DETAILS_LIMIT", "20")),
        fail_on_attention=os.getenv("CHECK_FAIL_ON_ATTENTION", "false").lower() == "true",
        allowed_attention_queue_ids=allowed_attention_queue_ids,
    )


def get_service(s: Settings):
    return build_sheets_service(
        auth_mode=s.google_auth_mode,
        scopes=[SHEETS_SCOPE],
        service_account_file=s.google_credentials,
        oauth_client_secret_file=s.google_oauth_client_secret_file,
        oauth_token_file=s.google_oauth_token_file,
    )


def read_rows(service, s: Settings) -> list[tuple[int, dict[str, str]]]:
    end_col = col(len(HEADERS))
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.queue_sheet_name}!A:{end_col}",
    ).execute()
    values = res.get("values", [])
    rows = []
    for row_no, raw in enumerate(values[1:], start=2):
        padded = raw[:len(HEADERS)] + [""] * (len(HEADERS) - len(raw))
        row = dict(zip(HEADERS, padded))
        if any(str(value).strip() for value in row.values()):
            rows.append((row_no, row))
    return rows


def main() -> None:
    s = settings()
    service = get_service(s)
    rows = read_rows(service, s)

    status_counts = Counter(row.get("status", "") for _, row in rows)
    operation_counts = Counter(row.get("operation_type", "") for _, row in rows)
    attention = []
    ignored_attention = []
    for row_no, row in rows:
        status = row.get("status", "")
        if status not in ATTENTION_STATUSES:
            continue
        item = {
            "row_no": row_no,
            "queue_id": row.get("queue_id", ""),
            "operation_type": row.get("operation_type", ""),
            "status": status,
            "target_issue_key": row.get("target_issue_key", ""),
            "retry_count": row.get("retry_count", ""),
            "last_error_code": row.get("last_error_code", ""),
            "last_error_message": row.get("last_error_message", ""),
            "result_summary": row.get("result_summary", ""),
        }
        if item["queue_id"] in s.allowed_attention_queue_ids:
            ignored_attention.append(item)
        else:
            attention.append(item)

    output = {
        "status": "attention_required" if attention else "ok",
        "total_rows": len(rows),
        "status_counts": dict(status_counts),
        "operation_counts": dict(operation_counts),
        "attention_count": len(attention),
        "attention_rows": attention[:s.details_limit],
        "ignored_attention_count": len(ignored_attention),
        "ignored_attention_rows": ignored_attention[:s.details_limit],
    }
    print(json.dumps(output, ensure_ascii=False))
    if attention and s.fail_on_attention:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
