#!/usr/bin/env python3
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from scripts.google_sheets_auth import build_sheets_service

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
HEADERS = [
    "queue_id", "requested_at", "requested_by", "request_source", "project_key",
    "operation_type", "target_issue_key", "issue_title", "issue_description",
    "comment_body", "new_status_name", "new_priority_name", "assignee_name",
    "due_date", "category_names", "custom_fields_json", "request_payload_json",
    "idempotency_key", "status", "retry_count", "last_error_code",
    "last_error_message", "result_summary", "processed_at",
    "processed_by_worker", "raw_request_text", "note",
]
RESULT_COLUMNS = [
    "status", "retry_count", "last_error_code", "last_error_message",
    "result_summary", "processed_at", "processed_by_worker",
]

@dataclass(frozen=True)
class Settings:
    backlog_base_url: str
    backlog_api_key: str
    spreadsheet_id: str
    queue_sheet_name: str
    google_auth_mode: str
    google_credentials: str
    google_oauth_client_secret_file: str
    google_oauth_token_file: str
    max_rows: int
    dry_run: bool
    worker_name: str
    timeout_seconds: float
    status_mapping_sheet_name: str
    priority_mapping_sheet_name: str
    assignee_mapping_sheet_name: str
    default_project_id: str
    default_issue_type_id: str
    default_priority_id: str
    default_assignee_id: str

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
        queue_sheet_name=os.getenv("WRITE_QUEUE_SHEET_NAME", "write_queue_v2"),
        google_auth_mode=os.getenv("GOOGLE_AUTH_MODE", "user_oauth"),
        google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        google_oauth_client_secret_file=require_env("GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        google_oauth_token_file=os.getenv("GOOGLE_OAUTH_TOKEN_FILE", r"C:\backlog-sync\config\google-oauth-token.json"),
        max_rows=int(os.getenv("WRITE_QUEUE_MAX_ROWS", "20")),
        dry_run=os.getenv("WRITE_QUEUE_DRY_RUN", "false").lower() == "true",
        worker_name=os.getenv("WORKER_NAME", "backlog-sync-worker-v2"),
        timeout_seconds=float(os.getenv("BACKLOG_TIMEOUT_SECONDS", "20")),
        status_mapping_sheet_name=os.getenv("STATUS_MAPPING_SHEET_NAME", "status_mapping"),
        priority_mapping_sheet_name=os.getenv("PRIORITY_MAPPING_SHEET_NAME", "priority_mapping"),
        assignee_mapping_sheet_name=os.getenv("ASSIGNEE_MAPPING_SHEET_NAME", "assignee_mapping"),
        default_project_id=os.getenv("TARGET_PROJECT_ID", ""),
        default_issue_type_id=os.getenv("BACKLOG_DEFAULT_ISSUE_TYPE_ID", ""),
        default_priority_id=os.getenv("BACKLOG_DEFAULT_PRIORITY_ID", ""),
        default_assignee_id=os.getenv("BACKLOG_DEFAULT_ASSIGNEE_ID", ""),
    )

def col(index: int) -> str:
    s = ""
    while index > 0:
        index, r = divmod(index - 1, 26)
        s = chr(65 + r) + s
    return s

def get_service(s: Settings):
    return build_sheets_service(
        auth_mode=s.google_auth_mode,
        scopes=[SHEETS_SCOPE],
        service_account_file=s.google_credentials,
        oauth_client_secret_file=s.google_oauth_client_secret_file,
        oauth_token_file=s.google_oauth_token_file,
    )

def read_rows(service, s: Settings) -> list[tuple[int, dict[str, str]]]:
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.queue_sheet_name}!A:AA",
    ).execute()
    values = res.get("values", [])
    rows = []
    for row_no, raw in enumerate(values[1:], start=2):
        padded = raw[:len(HEADERS)] + [""] * (len(HEADERS) - len(raw))
        rows.append((row_no, dict(zip(HEADERS, padded))))
    return rows


def read_status_mapping(service, s: Settings) -> dict[tuple[str, str], str]:
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.status_mapping_sheet_name}!A:H",
    ).execute()

    values = res.get("values", [])
    if not values:
        return {}

    headers = values[0]
    mapping: dict[tuple[str, str], str] = {}

    for raw in values[1:]:
        padded = raw + [""] * (len(headers) - len(raw))
        row = dict(zip(headers, padded))
        if str(row.get("is_active", "")).upper() not in ("TRUE", "1", "YES"):
            continue

        project_key = str(row.get("project_key", "")).strip()
        status_name = str(row.get("status_name", "")).strip()
        status_id = str(row.get("status_id", "")).strip()

        if project_key and status_name and status_id:
            mapping[(project_key, status_name)] = status_id

    return mapping

def read_active_mapping(
    service,
    s: Settings,
    sheet_name: str,
    expected_headers: list[str],
    name_column: str,
    id_column: str,
) -> dict[tuple[str, str], str]:
    res = service.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id,
        range=f"{sheet_name}!A:{col(len(expected_headers))}",
    ).execute()

    values = res.get("values", [])
    if not values:
        return {}

    headers = [str(value).strip() for value in values[0][:len(expected_headers)]]
    if headers != expected_headers:
        raise RuntimeError(f"{sheet_name} headers do not match expected mapping schema")

    mapping: dict[tuple[str, str], str] = {}
    for row_no, raw in enumerate(values[1:], start=2):
        padded = raw[:len(expected_headers)] + [""] * (len(expected_headers) - len(raw))
        row = dict(zip(expected_headers, padded))

        if not any(str(value).strip() for value in row.values()):
            continue
        if str(row.get("is_active", "")).strip().upper() not in ("TRUE", "1", "YES"):
            continue

        project_key = str(row.get("project_key", "")).strip()
        display_name = str(row.get(name_column, "")).strip()
        mapped_id = str(row.get(id_column, "")).strip()

        if not project_key or not display_name or not mapped_id:
            raise RuntimeError(f"{sheet_name} row {row_no} has active mapping without required values")

        key = (project_key, display_name)
        if key in mapping:
            raise RuntimeError(f"{sheet_name} has duplicate active mapping for {project_key}/{display_name}")

        mapping[key] = mapped_id

    return mapping


def read_priority_mapping(service, s: Settings) -> dict[tuple[str, str], str]:
    return read_active_mapping(
        service=service,
        s=s,
        sheet_name=s.priority_mapping_sheet_name,
        expected_headers=[
            "project_key", "priority_name", "priority_id", "is_active",
            "note", "last_checked_at", "source", "sort_order",
        ],
        name_column="priority_name",
        id_column="priority_id",
    )


def read_assignee_mapping(service, s: Settings) -> dict[tuple[str, str], str]:
    return read_active_mapping(
        service=service,
        s=s,
        sheet_name=s.assignee_mapping_sheet_name,
        expected_headers=[
            "project_key", "assignee_name", "assignee_id", "backlog_user_id",
            "is_active", "note", "last_checked_at", "source",
        ],
        name_column="assignee_name",
        id_column="assignee_id",
    )

def update_cells(service, s: Settings, row_no: int, values: list[str]) -> None:
    start = col(HEADERS.index(RESULT_COLUMNS[0]) + 1)
    end = col(HEADERS.index(RESULT_COLUMNS[-1]) + 1)
    service.spreadsheets().values().update(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.queue_sheet_name}!{start}{row_no}:{end}{row_no}",
        valueInputOption="RAW",
        body={"values": [values]},
    ).execute()

def mark_processing(service, s: Settings, row_no: int) -> None:
    status_col = col(HEADERS.index("status") + 1)
    service.spreadsheets().values().update(
        spreadsheetId=s.spreadsheet_id,
        range=f"{s.queue_sheet_name}!{status_col}{row_no}",
        valueInputOption="RAW",
        body={"values": [["processing"]]},
    ).execute()

def parse_payload(row: dict[str, str]) -> dict[str, str]:
    operation_type = row.get("operation_type", "").strip()
    if operation_type not in ("add_comment", "change_status", "change_priority", "change_assignee", "change_due_date", "create_issue"):
        raise ValueError(f"Unsupported operation_type: {operation_type}")

    raw_payload = row.get("request_payload_json", "").strip()
    if not raw_payload:
        raise ValueError("request_payload_json is required")

    payload = json.loads(raw_payload)
    action = payload.get("action") or operation_type
    if action != operation_type:
        raise ValueError(f"payload action does not match operation_type: {action} != {operation_type}")

    if operation_type == "create_issue":
        issue_title = payload.get("issue_title") or payload.get("summary") or row.get("issue_title", "")
        issue_description = payload.get("issue_description") or payload.get("description") or row.get("issue_description", "")
        project_id = str(payload.get("project_id") or payload.get("projectId") or "").strip()
        issue_type_id = str(payload.get("issue_type_id") or payload.get("issueTypeId") or "").strip()
        priority_id = str(payload.get("priority_id") or payload.get("priorityId") or "").strip()
        assignee_id = str(payload.get("assignee_id") or payload.get("assigneeId") or "").strip()
        due_date = normalize_due_date(payload.get("due_date") or payload.get("dueDate") or row.get("due_date", ""))

        if not issue_title:
            raise ValueError("issue_title is required")

        return {
            "action": "create_issue",
            "project_id": project_id,
            "issue_title": issue_title,
            "issue_description": issue_description,
            "issue_type_id": issue_type_id,
            "priority_id": priority_id,
            "assignee_id": assignee_id,
            "due_date": due_date,
        }

    issue_key = payload.get("target_issue_key") or row.get("target_issue_key", "")
    if not issue_key:
        raise ValueError("target_issue_key is required")

    if operation_type == "add_comment":
        comment = payload.get("comment_body") or row.get("comment_body", "")
        if not comment:
            raise ValueError("comment_body is required")
        return {"action": "add_comment", "target_issue_key": issue_key, "comment_body": comment}

    if operation_type == "change_status":
        new_status_name = payload.get("new_status_name") or row.get("new_status_name", "")
        if not new_status_name:
            raise ValueError("new_status_name is required")
        return {"action": "change_status", "target_issue_key": issue_key, "new_status_name": new_status_name}

    if operation_type == "change_priority":
        new_priority_name = payload.get("new_priority_name") or row.get("new_priority_name", "")
        if not new_priority_name:
            raise ValueError("new_priority_name is required")
        return {"action": "change_priority", "target_issue_key": issue_key, "new_priority_name": new_priority_name}

    if operation_type == "change_assignee":
        assignee_name = payload.get("assignee_name") or row.get("assignee_name", "")
        if not assignee_name:
            raise ValueError("assignee_name is required")
        return {"action": "change_assignee", "target_issue_key": issue_key, "assignee_name": assignee_name}

    if operation_type == "change_due_date":
        due_date = normalize_due_date(payload.get("due_date") or payload.get("dueDate") or row.get("due_date", ""))
        if not due_date:
            raise ValueError("due_date is required")
        return {"action": "change_due_date", "target_issue_key": issue_key, "due_date": due_date}

    raise ValueError(f"Unsupported operation_type: {operation_type}")


def normalize_due_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10]

def add_comment(s: Settings, issue_key: str, comment: str) -> dict[str, Any]:
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.post(
            f"/api/v2/issues/{issue_key}/comments",
            params={"apiKey": s.backlog_api_key},
            data={"content": comment},
        )
        res.raise_for_status()
        return res.json()


def create_issue(s: Settings, payload: dict[str, str]) -> dict[str, Any]:
    project_id = payload.get("project_id") or s.default_project_id
    issue_type_id = payload.get("issue_type_id") or s.default_issue_type_id
    priority_id = payload.get("priority_id") or s.default_priority_id
    assignee_id = payload.get("assignee_id") or s.default_assignee_id

    if not project_id:
        raise ValueError("project_id is required in request_payload_json or TARGET_PROJECT_ID")
    if not issue_type_id:
        raise ValueError("issue_type_id is required in request_payload_json or BACKLOG_DEFAULT_ISSUE_TYPE_ID")
    if not priority_id:
        raise ValueError("priority_id is required in request_payload_json or BACKLOG_DEFAULT_PRIORITY_ID")

    data = {
        "projectId": project_id,
        "summary": payload["issue_title"],
        "issueTypeId": issue_type_id,
        "priorityId": priority_id,
    }
    if payload.get("issue_description"):
        data["description"] = payload["issue_description"]
    if assignee_id:
        data["assigneeId"] = assignee_id
    if payload.get("due_date"):
        data["dueDate"] = payload["due_date"]

    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.post(
            "/api/v2/issues",
            params={"apiKey": s.backlog_api_key},
            data=data,
        )
        res.raise_for_status()
        return res.json()



def change_status(s: Settings, issue_key: str, status_id: str) -> dict[str, Any]:
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.patch(
            f"/api/v2/issues/{issue_key}",
            params={"apiKey": s.backlog_api_key},
            data={"statusId": status_id},
        )
        res.raise_for_status()
        return res.json()

def change_priority(s: Settings, issue_key: str, priority_id: str) -> dict[str, Any]:
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.patch(
            f"/api/v2/issues/{issue_key}",
            params={"apiKey": s.backlog_api_key},
            data={"priorityId": priority_id},
        )
        res.raise_for_status()
        return res.json()


def change_assignee(s: Settings, issue_key: str, assignee_id: str) -> dict[str, Any]:
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.patch(
            f"/api/v2/issues/{issue_key}",
            params={"apiKey": s.backlog_api_key},
            data={"assigneeId": assignee_id},
        )
        res.raise_for_status()
        return res.json()


def change_due_date(s: Settings, issue_key: str, due_date: str) -> dict[str, Any]:
    with httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.patch(
            f"/api/v2/issues/{issue_key}",
            params={"apiKey": s.backlog_api_key},
            data={"dueDate": due_date},
        )
        res.raise_for_status()
        return res.json()

def sanitize_error(message: str, api_key: str) -> str:
    sanitized = message
    if api_key:
        sanitized = sanitized.replace(api_key, "***")
        sanitized = sanitized.replace("apiKey=" + api_key, "apiKey=***")
    return sanitized
def main() -> None:
    s = settings()
    service = get_service(s)
    status_mapping = read_status_mapping(service, s)
    priority_mapping = read_priority_mapping(service, s)
    assignee_mapping = read_assignee_mapping(service, s)
    processed = 0

    for row_no, row in read_rows(service, s):
        if processed >= s.max_rows:
            break
        if row.get("status", "").strip().lower() != "queued":
            continue

        retry = int(row.get("retry_count") or "0")
        mark_processing(service, s, row_no)

        try:
            payload = parse_payload(row)
            if s.dry_run:
                if payload["action"] == "create_issue":
                    missing = []
                    if not (payload.get("project_id") or s.default_project_id):
                        missing.append("project_id/TARGET_PROJECT_ID")
                    if not (payload.get("issue_type_id") or s.default_issue_type_id):
                        missing.append("issue_type_id/BACKLOG_DEFAULT_ISSUE_TYPE_ID")
                    if not (payload.get("priority_id") or s.default_priority_id):
                        missing.append("priority_id/BACKLOG_DEFAULT_PRIORITY_ID")
                    if missing:
                        update_cells(service, s, row_no, [
                            "on_hold", str(retry), "CREATE_ISSUE_REQUIRED_ID_MISSING",
                            "missing: " + ", ".join(missing),
                            "", "", s.worker_name,
                        ])
                    else:
                        update_cells(service, s, row_no, [
                            "validated", str(retry), "", "",
                            f"dry_run: create_issue validated: {payload['issue_title']}",
                            "", s.worker_name,
                        ])
                elif payload["action"] == "change_priority":
                    priority_id = priority_mapping.get((row.get("project_key", ""), payload["new_priority_name"]))
                    if not priority_id:
                        update_cells(service, s, row_no, [
                            "on_hold", str(retry), "PRIORITY_MAPPING_NOT_FOUND",
                            f"priority_mapping not found: {row.get('project_key', '')} / {payload['new_priority_name']}",
                            "", "", s.worker_name,
                        ])
                    else:
                        update_cells(service, s, row_no, [
                            "validated", str(retry), "", "",
                            f"dry_run: change_priority validated: {payload['new_priority_name']} ({priority_id})",
                            "", s.worker_name,
                        ])
                elif payload["action"] == "change_assignee":
                    assignee_id = assignee_mapping.get((row.get("project_key", ""), payload["assignee_name"]))
                    if not assignee_id:
                        update_cells(service, s, row_no, [
                            "on_hold", str(retry), "ASSIGNEE_MAPPING_NOT_FOUND",
                            f"assignee_mapping not found: {row.get('project_key', '')} / {payload['assignee_name']}",
                            "", "", s.worker_name,
                        ])
                    else:
                        update_cells(service, s, row_no, [
                            "validated", str(retry), "", "",
                            f"dry_run: change_assignee validated: {payload['assignee_name']} ({assignee_id})",
                            "", s.worker_name,
                        ])
                elif payload["action"] == "change_due_date":
                    update_cells(service, s, row_no, [
                        "validated", str(retry), "", "",
                        f"dry_run: change_due_date validated: {payload['due_date']}",
                        "", s.worker_name,
                    ])
                else:
                    update_cells(service, s, row_no, [
                        "validated", str(retry), "", "",
                        f"dry_run: {payload['action']} validated", "", s.worker_name,
                    ])
            elif payload["action"] == "create_issue":
                response = create_issue(s, payload)
                update_cells(service, s, row_no, [
                    "succeeded", str(retry), "", "",
                    f"issue created: issueKey={response.get('issueKey', '')} id={response.get('id', '')}",
                    datetime.now(UTC).isoformat(), s.worker_name,
                ])
            elif payload["action"] == "add_comment":
                response = add_comment(s, payload["target_issue_key"], payload["comment_body"])
                update_cells(service, s, row_no, [
                    "succeeded", str(retry), "", "",
                    f"comment added: id={response.get('id', '')}",
                    datetime.now(UTC).isoformat(), s.worker_name,
                ])
            elif payload["action"] == "change_status":
                status_id = status_mapping.get((row.get("project_key", ""), payload["new_status_name"]))
                if not status_id:
                    update_cells(service, s, row_no, [
                        "on_hold", str(retry), "STATUS_MAPPING_NOT_FOUND",
                        f"status_mapping not found: {row.get('project_key', '')} / {payload['new_status_name']}",
                        "", "", s.worker_name,
                    ])
                else:
                    response = change_status(s, payload["target_issue_key"], status_id)
                    update_cells(service, s, row_no, [
                        "succeeded", str(retry), "", "",
                        f"status changed: {payload['new_status_name']} ({status_id})",
                        datetime.now(UTC).isoformat(), s.worker_name,
                    ])
            elif payload["action"] == "change_priority":
                priority_id = priority_mapping.get((row.get("project_key", ""), payload["new_priority_name"]))
                if not priority_id:
                    update_cells(service, s, row_no, [
                        "on_hold", str(retry), "PRIORITY_MAPPING_NOT_FOUND",
                        f"priority_mapping not found: {row.get('project_key', '')} / {payload['new_priority_name']}",
                        "", "", s.worker_name,
                    ])
                else:
                    response = change_priority(s, payload["target_issue_key"], priority_id)
                    update_cells(service, s, row_no, [
                        "succeeded", str(retry), "", "",
                        f"priority changed: {payload['new_priority_name']} ({priority_id})",
                        datetime.now(UTC).isoformat(), s.worker_name,
                    ])
            elif payload["action"] == "change_assignee":
                assignee_id = assignee_mapping.get((row.get("project_key", ""), payload["assignee_name"]))
                if not assignee_id:
                    update_cells(service, s, row_no, [
                        "on_hold", str(retry), "ASSIGNEE_MAPPING_NOT_FOUND",
                        f"assignee_mapping not found: {row.get('project_key', '')} / {payload['assignee_name']}",
                        "", "", s.worker_name,
                    ])
                else:
                    response = change_assignee(s, payload["target_issue_key"], assignee_id)
                    update_cells(service, s, row_no, [
                        "succeeded", str(retry), "", "",
                        f"assignee changed: {payload['assignee_name']} ({assignee_id})",
                        datetime.now(UTC).isoformat(), s.worker_name,
                    ])
            elif payload["action"] == "change_due_date":
                response = change_due_date(s, payload["target_issue_key"], payload["due_date"])
                update_cells(service, s, row_no, [
                    "succeeded", str(retry), "", "",
                    f"due_date changed: {payload['due_date']}",
                    datetime.now(UTC).isoformat(), s.worker_name,
                ])
        except Exception as exc:
            update_cells(service, s, row_no, [
                "failed", str(retry + 1), "PROCESS_ERROR", sanitize_error(str(exc), s.backlog_api_key),
                "", "", s.worker_name,
            ])

        processed += 1

if __name__ == "__main__":
    main()
