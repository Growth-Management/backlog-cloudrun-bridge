# write_queue_v2 resident PC processor

This document covers the resident-PC Backlog writer that reads Google Sheets
`write_queue_v2!A:AA` and writes to the Backlog API.

The legacy `write_queue` processor remains separate. Do not replace or rewrite
the legacy sheet during v2 rollout.

## Queue contract

`write_queue_v2` uses these 27 columns in order:

`queue_id / requested_at / requested_by / request_source / project_key / operation_type / target_issue_key / issue_title / issue_description / comment_body / new_status_name / new_priority_name / assignee_name / due_date / category_names / custom_fields_json / request_payload_json / idempotency_key / status / retry_count / last_error_code / last_error_message / result_summary / processed_at / processed_by_worker / raw_request_text / note`

One row represents one Backlog write request.

## Supported operations

The processor currently supports:

- `add_comment`
- `change_status`
- `change_priority`
- `change_assignee`
- `change_due_date`

`create_issue` should be added only after the project-specific issue type,
priority, assignee, category, and custom-field mapping policy is confirmed.

## Safety behavior

- The worker reads only rows where `status=queued`.
- `request_payload_json` and `idempotency_key` are required.
- Duplicate `idempotency_key` values are blocked when an earlier row is
  `queued`, `processing`, `validated`, or `succeeded`.
- Display values such as `new_status_name`, `new_priority_name`, and
  `assignee_name` are mapped through Sheets before Backlog API execution.
- Unknown, inactive, duplicate, or blank-ID mappings stop before Backlog API
  execution.
- `due_date` must be `yyyy-MM-dd`.
- Error messages are sanitized before being written to Sheets or logs.

## DryRun

Run validation without live Backlog writes:

```powershell
.\scripts\windows\run-write-queue-processor-v2.ps1 -DryRun
```

DryRun updates processed rows to `validated` when validation succeeds. Mapping
or validation failures are written as `on_hold`.

## Live run

Run one queued row live:

```powershell
.\scripts\windows\run-write-queue-processor-v2.ps1
```

The runner explicitly sets `WRITE_QUEUE_DRY_RUN=false` for live runs so a stale
PowerShell session does not accidentally keep the worker in validation mode.

## Row generation helpers

Paste-ready TSV helpers:

```powershell
.\scripts\windows\new-add-comment-row-v2.ps1 -IssueKey ICESAO_GENTASK-1 -CommentBody "確認しました"
.\scripts\windows\new-change-status-row-v2.ps1 -IssueKey ICESAO_GENTASK-1 -NewStatusName "処理済み"
.\scripts\windows\new-change-due-date-row-v2.ps1 -IssueKey ICESAO_GENTASK-1 -DueDate 2026-08-31
```

The helpers generate deterministic SHA-256 based idempotency suffixes.

## Recommended rollout

1. Add `write_queue_v2`, `status_mapping`, `priority_mapping`, and
   `assignee_mapping` to the existing spreadsheet.
2. Keep legacy `write_queue` unchanged.
3. Run one `add_comment` row with `-DryRun`.
4. Run one `add_comment` row live.
5. Add one field-change operation at a time, with a restore row for live tests.
6. Only expand batch size after failure handling and duplicate prevention are
   confirmed.
