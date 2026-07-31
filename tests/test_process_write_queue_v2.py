import sys
import types
import unittest

sys.modules.setdefault("httpx", types.SimpleNamespace(Client=object))

from scripts.process_write_queue_v2 import (
    HEADERS,
    find_duplicate_idempotency,
    parse_payload,
    sanitize_error,
)


def row(**overrides):
    values = {header: "" for header in HEADERS}
    values.update(
        {
            "queue_id": "WQV2-TEST-001",
            "project_key": "ICESAO_GENTASK",
            "target_issue_key": "ICESAO_GENTASK-1",
            "idempotency_key": "issue:ICESAO_GENTASK-1:status:処理済み",
            "status": "queued",
            "retry_count": "0",
        }
    )
    values.update(overrides)
    return values


class ProcessWriteQueueV2Tests(unittest.TestCase):
    def test_parse_change_due_date_payload(self):
        payload = parse_payload(
            row(
                operation_type="change_due_date",
                due_date="2026-08-31",
                request_payload_json='{"action":"change_due_date","target_issue_key":"ICESAO_GENTASK-1","due_date":"2026-08-31"}',
            )
        )

        self.assertEqual(
            payload,
            {
                "action": "change_due_date",
                "target_issue_key": "ICESAO_GENTASK-1",
                "due_date": "2026-08-31",
            },
        )

    def test_parse_change_due_date_rejects_invalid_date(self):
        with self.assertRaisesRegex(ValueError, "yyyy-MM-dd"):
            parse_payload(
                row(
                    operation_type="change_due_date",
                    due_date="2026/08/31",
                    request_payload_json='{"action":"change_due_date","target_issue_key":"ICESAO_GENTASK-1","due_date":"2026/08/31"}',
                )
            )

    def test_parse_payload_requires_idempotency_key(self):
        with self.assertRaisesRegex(ValueError, "idempotency_key is required"):
            parse_payload(
                row(
                    idempotency_key="",
                    operation_type="add_comment",
                    comment_body="確認しました",
                    request_payload_json='{"action":"add_comment","target_issue_key":"ICESAO_GENTASK-1","comment_body":"確認しました"}',
                )
            )

    def test_duplicate_idempotency_blocks_later_rows(self):
        first = row(status="succeeded", idempotency_key="issue:1:comment:abc")
        second = row(queue_id="WQV2-TEST-002", idempotency_key="issue:1:comment:abc")

        self.assertEqual(
            find_duplicate_idempotency([(2, first), (3, second)], 3, second),
            (2, "succeeded"),
        )

    def test_sanitize_error_masks_api_key(self):
        self.assertEqual(
            sanitize_error("request failed apiKey=secret-token", "secret-token"),
            "request failed apiKey=***",
        )


if __name__ == "__main__":
    unittest.main()
