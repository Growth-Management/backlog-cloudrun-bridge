#!/usr/bin/env python3
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass

from scripts.google_sheets_auth import build_sheets_service
from scripts.prepare_iwtech_sysop_queue_v2 import SYNC_ISSUE_MAP_HEADERS

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


@dataclass(frozen=True)
class Settings:
    spreadsheet_id: str
    google_auth_mode: str
    google_credentials: str
    google_oauth_client_secret_file: str
    google_oauth_token_file: str
    sync_issue_map_sheet_name: str
    source_project_key: str
    target_project_key: str
    details_limit: int
    fail_on_warnings: bool


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
        sync_issue_map_sheet_name=os.getenv("SYNC_ISSUE_MAP_SHEET_NAME", "sync_issue_map"),
        source_project_key=os.getenv("SOURCE_PROJECT_KEY", "IWTECH_SYSOP"),
        target_project_key=os.getenv("TARGET_PROJECT_KEY", "ICESAO_GENTASK"),
        details_limit=int(os.getenv("CHECK_DETAILS_LIMIT", "20")),
        fail_on_warnings=os.getenv("CHECK_FAIL_ON_WARNINGS", "false").lower() == "true",
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


def read_rows(service, s: Settings) -> list[tuple[int, dict[str, str]]]:
    end_col = col(len(SYNC_ISSUE_MAP_HEADERS))
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.sync_issue_map_sheet_name}!A:{end_col}",
    ).execute()
    values = res.get("values", [])
    rows = []
    for row_no, raw in enumerate(values[1:], start=2):
        padded = raw[:len(SYNC_ISSUE_MAP_HEADERS)] + [""] * (len(SYNC_ISSUE_MAP_HEADERS) - len(raw))
        row = dict(zip(SYNC_ISSUE_MAP_HEADERS, padded))
        if any(str(value).strip() for value in row.values()):
            rows.append((row_no, row))
    return rows


def add_warning(warnings: list[dict[str, str]], row_no: int, code: str, message: str, row: dict[str, str]) -> None:
    warnings.append({
        "row_no": row_no,
        "code": code,
        "message": message,
        "source_issue_key": row.get("source_issue_key", ""),
        "target_issue_key": row.get("target_issue_key", ""),
        "sync_status": row.get("sync_status", ""),
    })


def main() -> None:
    s = settings()
    service = get_service(s)
    rows = read_rows(service, s)

    status_counts = Counter(row.get("sync_status", "") for _, row in rows)
    source_seen: dict[str, list[int]] = defaultdict(list)
    target_seen: dict[str, list[int]] = defaultdict(list)
    warnings = []

    for row_no, row in rows:
        source_issue_key = row.get("source_issue_key", "")
        target_issue_key = row.get("target_issue_key", "")
        if source_issue_key:
            source_seen[source_issue_key].append(row_no)
        if target_issue_key:
            target_seen[target_issue_key].append(row_no)

        if row.get("source_project_key") != s.source_project_key:
            continue
        if row.get("target_project_key") and row.get("target_project_key") != s.target_project_key:
            continue

        sync_status = row.get("sync_status", "")
        if sync_status == "created":
            if not target_issue_key:
                add_warning(warnings, row_no, "CREATED_WITHOUT_TARGET", "created row has no target_issue_key", row)
            if not row.get("last_issue_synced_at", ""):
                add_warning(warnings, row_no, "MISSING_LAST_ISSUE_SYNCED_AT", "created row has no last_issue_synced_at", row)
        elif sync_status in ("create_failed", "create_on_hold"):
            add_warning(warnings, row_no, "CREATE_NOT_COMPLETED", "create reconciliation is not completed", row)
        elif sync_status == "queued_create":
            add_warning(warnings, row_no, "CREATE_STILL_QUEUED", "create queue result has not been reconciled", row)

    for source_issue_key, row_numbers in source_seen.items():
        if len(row_numbers) > 1:
            warnings.append({
                "row_no": ",".join(str(row_no) for row_no in row_numbers),
                "code": "DUPLICATE_SOURCE_ISSUE",
                "message": "source_issue_key appears more than once",
                "source_issue_key": source_issue_key,
                "target_issue_key": "",
                "sync_status": "",
            })

    for target_issue_key, row_numbers in target_seen.items():
        if len(row_numbers) > 1:
            warnings.append({
                "row_no": ",".join(str(row_no) for row_no in row_numbers),
                "code": "DUPLICATE_TARGET_ISSUE",
                "message": "target_issue_key appears more than once",
                "source_issue_key": "",
                "target_issue_key": target_issue_key,
                "sync_status": "",
            })

    output = {
        "status": "warning" if warnings else "ok",
        "total_rows": len(rows),
        "sync_status_counts": dict(status_counts),
        "warning_count": len(warnings),
        "warnings": warnings[:s.details_limit],
    }
    print(json.dumps(output, ensure_ascii=False))
    if warnings and s.fail_on_warnings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
