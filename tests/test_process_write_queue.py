from scripts.process_write_queue import (
    QueueRow,
    column_letter,
    process_queue_row,
    process_queue_rows,
    should_process,
)


class FakeBacklogWriteClient:
    def __init__(self) -> None:
        self.created = []
        self.updated = []
        self.comments = []

    def create_issue(self, row: dict[str, str]) -> dict:
        self.created.append(row)
        return {
            "issueKey": "ICESAO_GENTASK-10",
            "summary": row["summary"],
            "status": {"name": "Open"},
        }

    def update_issue(self, row: dict[str, str]) -> dict:
        self.updated.append(row)
        return {
            "issueKey": row["issue_key"],
            "summary": row.get("summary"),
            "status": {"name": "In Progress"},
        }

    def add_comment(self, row: dict[str, str]) -> dict:
        self.comments.append(row)
        return {
            "id": 55,
            "content": row["comment"],
        }


def test_should_process_only_approved_and_queued() -> None:
    assert should_process({"approval_status": "approved", "execution_status": "queued"})
    assert not should_process({"approval_status": "pending", "execution_status": "queued"})
    assert not should_process({"approval_status": "approved", "execution_status": "applied"})


def test_process_queue_rows_skips_non_ready_rows() -> None:
    client = FakeBacklogWriteClient()
    rows = [
        QueueRow(
            sheet_row_number=2,
            values={
                "approval_status": "pending",
                "execution_status": "queued",
                "operation": "add_comment",
                "issue_key": "ICESAO_GENTASK-1",
                "comment": "Skip",
            },
        ),
        QueueRow(
            sheet_row_number=3,
            values={
                "approval_status": "approved",
                "execution_status": "queued",
                "operation": "add_comment",
                "issue_key": "ICESAO_GENTASK-1",
                "comment": "Apply",
            },
        ),
    ]

    results = process_queue_rows(rows, client, max_rows=10)

    assert len(results) == 1
    assert results[0][0] == 3
    assert results[0][1].execution_status == "applied"
    assert len(client.comments) == 1


def test_process_queue_row_supports_dry_run_without_calling_backlog() -> None:
    client = FakeBacklogWriteClient()

    result = process_queue_row(
        {
            "operation": "update_issue",
            "issue_key": "ICESAO_GENTASK-1",
            "summary": "Updated",
            "retry_count": "0",
        },
        client,
        dry_run=True,
    )

    assert result.execution_status == "validated"
    assert result.applied_at == ""
    assert '"dry_run":true' in result.backlog_response
    assert client.updated == []


def test_process_queue_row_validates_required_fields() -> None:
    client = FakeBacklogWriteClient()

    result = process_queue_row(
        {
            "operation": "create_issue",
            "summary": "Missing IDs",
            "retry_count": "1",
        },
        client,
    )

    assert result.execution_status == "failed"
    assert result.retry_count == 2
    assert "issue_type_id is required" in result.validation_error
    assert client.created == []


def test_process_queue_row_rejects_unsupported_operation() -> None:
    client = FakeBacklogWriteClient()

    result = process_queue_row(
        {
            "operation": "delete_issue",
            "issue_key": "ICESAO_GENTASK-1",
        },
        client,
    )

    assert result.execution_status == "failed"
    assert result.validation_error == "Unsupported operation: delete_issue"


def test_column_letter_handles_multi_letter_columns() -> None:
    assert column_letter(1) == "A"
    assert column_letter(20) == "T"
    assert column_letter(27) == "AA"
