#!/usr/bin/env python3
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts import process_write_queue_v2 as base

_original_change_status = base.change_status
_original_update_cells = base.update_cells
_last_noop_status: dict[str, str] = {}


def _current_issue(s: base.Settings, issue_key: str) -> dict[str, Any]:
    with base.httpx.Client(base_url=s.backlog_base_url.rstrip("/"), timeout=s.timeout_seconds) as client:
        res = client.get(
            f"/api/v2/issues/{issue_key}",
            params={"apiKey": s.backlog_api_key},
        )
        base.raise_for_backlog_status(res, s.backlog_api_key)
        issue = res.json()
        if not isinstance(issue, dict):
            raise RuntimeError(f"Backlog issue response was not an object: {issue_key}")
        return issue


def _status_id(issue: dict[str, Any]) -> str:
    status = issue.get("status")
    if isinstance(status, dict):
        return str(status.get("id") or "").strip()
    return ""


def _status_name(issue: dict[str, Any]) -> str:
    status = issue.get("status")
    if isinstance(status, dict):
        return str(status.get("name") or "").strip()
    return ""


def change_status_noop_guard(
    s: base.Settings,
    issue_key: str,
    status_id: str,
    comment: str = "",
) -> dict[str, Any]:
    issue = _current_issue(s, issue_key)
    if _status_id(issue) == str(status_id):
        status_name = _status_name(issue) or "unknown"
        _last_noop_status["summary"] = f"no-op: status already {status_name} ({status_id})"
        return issue

    _last_noop_status.clear()
    return _original_change_status(s, issue_key, status_id, comment)


def update_cells_noop_summary(service, s: base.Settings, row_no: int, values: list[str]) -> None:
    if (
        _last_noop_status
        and len(values) >= 5
        and values[0] == "succeeded"
        and values[4].startswith("status changed:")
    ):
        values = list(values)
        values[2] = ""
        values[3] = ""
        values[4] = _last_noop_status["summary"]
        values[5] = datetime.now(UTC).isoformat()
        _last_noop_status.clear()

    _original_update_cells(service, s, row_no, values)


base.change_status = change_status_noop_guard
base.update_cells = update_cells_noop_summary


if __name__ == "__main__":
    base.main()
