#!/usr/bin/env python3
"""Prepare create_issue rows for every unmapped IWTECH_SYSOP issue not in a completed status.

This is an IWTECH_SYSOP overlay around the shared v2 create pre-queue implementation.
The shared queue schema, idempotency, mapping writes, and DryRun behavior remain in
``prepare_iwtech_sysop_queue_v2``.
"""

import os
from typing import Any

from scripts import prepare_iwtech_sysop_queue_v2 as base

DEFAULT_COMPLETED_STATUS_NAMES = ("完了",)
BACKLOG_MAX_PAGE_SIZE = 100


def completed_status_names() -> set[str]:
    raw = os.getenv("SOURCE_COMPLETED_STATUS_NAMES", ",".join(DEFAULT_COMPLETED_STATUS_NAMES))
    return {name.strip() for name in raw.split(",") if name.strip()}


def status_name(issue: dict[str, Any]) -> str:
    status = issue.get("status")
    if isinstance(status, dict):
        return str(status.get("name") or "").strip()
    return ""


def is_non_completed(issue: dict[str, Any], completed_names: set[str]) -> bool:
    return status_name(issue) not in completed_names


def source_issues(s: base.Settings) -> list[dict[str, Any]]:
    """Return explicit or project-wide source issues, excluding completed statuses.

    ``SYNC_MAX_ISSUES=0`` means no total cap. Project-wide reads are paginated with
    Backlog's maximum page size and constrained to non-completed status IDs.
    A defensive name filter is also applied to protect against stale status metadata.
    """

    completed_names = completed_status_names()
    issue_keys = [key.strip() for key in os.getenv("SOURCE_ISSUE_KEYS", "").split(",") if key.strip()]
    if issue_keys:
        issues = [base.backlog_get(s, f"/api/v2/issues/{issue_key}") for issue_key in issue_keys]
        return [issue for issue in issues if isinstance(issue, dict) and is_non_completed(issue, completed_names)]

    project = base.backlog_get(s, f"/api/v2/projects/{s.source_project_key}")
    project_id = project.get("id")
    if not project_id:
        raise RuntimeError(f"source project id not found: {s.source_project_key}")

    statuses = base.backlog_get(s, f"/api/v2/projects/{s.source_project_key}/statuses")
    if not isinstance(statuses, list):
        raise RuntimeError("Backlog statuses response was not a list")

    active_status_ids = [
        status.get("id")
        for status in statuses
        if isinstance(status, dict)
        and status.get("id") is not None
        and str(status.get("name") or "").strip() not in completed_names
    ]
    if not active_status_ids:
        return []

    max_issues = max(0, s.max_issues)
    page_size = BACKLOG_MAX_PAGE_SIZE if max_issues == 0 else min(BACKLOG_MAX_PAGE_SIZE, max_issues)
    offset = 0
    result: list[dict[str, Any]] = []

    while True:
        page = base.backlog_get(
            s,
            "/api/v2/issues",
            params={
                "projectId[]": [project_id],
                "statusId[]": active_status_ids,
                "sort": "updated",
                "order": "desc",
                "count": page_size,
                "offset": offset,
            },
        )
        if not isinstance(page, list):
            raise RuntimeError("Backlog issues response was not a list")

        valid_page = [
            issue
            for issue in page
            if isinstance(issue, dict) and is_non_completed(issue, completed_names)
        ]
        result.extend(valid_page)

        if max_issues and len(result) >= max_issues:
            return result[:max_issues]
        if len(page) < page_size:
            break
        offset += len(page)

    return result


def main() -> None:
    base.source_issues = source_issues
    base.main()


if __name__ == "__main__":
    main()
