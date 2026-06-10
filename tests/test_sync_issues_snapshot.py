from scripts.sync_issues_snapshot import (
    ISSUES_SNAPSHOT_HEADERS,
    build_issue_rows,
    build_issue_url,
    build_row_hash,
)


def test_build_issue_rows_normalizes_backlog_issue() -> None:
    rows = build_issue_rows(
        [
            {
                "id": 123,
                "issueKey": "ICESAO_GENTASK-1",
                "summary": "Example issue",
                "description": "Body",
                "status": {"id": 1, "name": "Open"},
                "priority": {"id": 3, "name": "Normal"},
                "issueType": {"id": 5, "name": "Task"},
                "assignee": {"id": 10, "name": "篠原邦昭"},
                "startDate": "2026-06-10",
                "dueDate": "2026-06-17",
                "created": "2026-06-09T00:00:00Z",
                "updated": "2026-06-10T00:00:00Z",
            }
        ],
        project_key="ICESAO_GENTASK",
        backlog_base_url="https://ice.backlog.jp",
        synced_at="2026-06-10T00:00:00+00:00",
    )

    row = dict(zip(ISSUES_SNAPSHOT_HEADERS, rows[0], strict=True))
    assert row["issue_key"] == "ICESAO_GENTASK-1"
    assert row["issue_id"] == 123
    assert row["project_key"] == "ICESAO_GENTASK"
    assert row["summary"] == "Example issue"
    assert row["status_id"] == 1
    assert row["status_name"] == "Open"
    assert row["priority_id"] == 3
    assert row["issue_type_name"] == "Task"
    assert row["assignee_name"] == "篠原邦昭"
    assert row["url"] == "https://ice.backlog.jp/view/ICESAO_GENTASK-1"
    assert row["last_synced_at"] == "2026-06-10T00:00:00+00:00"
    assert len(row["row_hash"]) == 64


def test_build_issue_rows_handles_missing_nested_values() -> None:
    rows = build_issue_rows(
        [{"issueKey": "ICESAO_GENTASK-2", "summary": "No assignee"}],
        project_key="ICESAO_GENTASK",
        backlog_base_url="https://ice.backlog.jp/",
        synced_at="2026-06-10T00:00:00+00:00",
    )

    row = dict(zip(ISSUES_SNAPSHOT_HEADERS, rows[0], strict=True))
    assert row["description"] == ""
    assert row["status_id"] == ""
    assert row["assignee_id"] == ""
    assert row["url"] == "https://ice.backlog.jp/view/ICESAO_GENTASK-2"


def test_build_issue_url_returns_blank_without_issue_key() -> None:
    assert build_issue_url("https://ice.backlog.jp", "") == ""


def test_build_row_hash_ignores_sync_metadata() -> None:
    base = {"issue_key": "A-1", "summary": "Same", "last_synced_at": "old"}
    newer = {"issue_key": "A-1", "summary": "Same", "last_synced_at": "new"}

    assert build_row_hash(base) == build_row_hash(newer)
