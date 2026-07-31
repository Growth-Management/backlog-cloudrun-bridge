# write_queue_v2

`write_queue_v2` is the standard spreadsheet queue for Backlog write requests. It runs beside the legacy 20-column `write_queue` until v2 behavior is verified.

## Standard Columns

```text
queue_id / requested_at / requested_by / request_source / project_key / operation_type / target_issue_key / issue_title / issue_description / comment_body / new_status_name / new_priority_name / assignee_name / due_date / category_names / custom_fields_json / request_payload_json / idempotency_key / status / retry_count / last_error_code / last_error_message / result_summary / processed_at / processed_by_worker / raw_request_text / note
```

## Initial Operations

- `add_comment`
- `create_issue`

The legacy `write_queue` processor remains available for the old 20-column flow.

## Required Safety Fields

- `request_payload_json`: normalized worker input, not raw natural language
- `idempotency_key`: duplicate prevention key
- `status`: queue lifecycle state
- `retry_count`: retry counter

## Status Lifecycle

- `queued`: ready to process
- `processing`: worker has picked up the row
- `validated`: dry-run validation succeeded
- `succeeded`: Backlog write succeeded
- `failed`: automatic processing failed
- `on_hold`: manual confirmation required
- `cancelled`: intentionally skipped

## create_issue Payload

`create_issue` requires Backlog numeric IDs. Pass them in `request_payload_json` or resident-PC environment variables.

```json
{
  "action": "create_issue",
  "project_key": "ICESAO_GENTASK",
  "project_id": "12345",
  "issue_title": "Example issue",
  "issue_description": "Issue body",
  "issue_type_id": "67890",
  "priority_id": "3",
  "assignee_id": "115000"
}
```

Required environment values for the IWTECH_SYSOP pre-queue job:

```powershell
$env:TARGET_PROJECT_ID = "ICESAO_GENTASK project id"
$env:BACKLOG_DEFAULT_ISSUE_TYPE_ID = "default issue type id"
$env:BACKLOG_DEFAULT_PRIORITY_ID = "3"
$env:BACKLOG_DEFAULT_ASSIGNEE_ID = "115000"
```

## IWTECH_SYSOP Pre-Queue Scope

`scripts.prepare_iwtech_sysop_queue_v2` reads source issues from `IWTECH_SYSOP`, skips rows already present in `sync_issue_map` or already queued by `idempotency_key`, and appends `create_issue` rows to `write_queue_v2`.

Initial scope:

- Create target issue queue rows only
- Preserve source people and notified users as text
- Do not sync attachments
- Do not reconcile created target issue keys yet
- Do not sync comments yet

Follow-up work should reconcile `create_queue_id` to the created target issue and then enable comment synchronization through `sync_comment_map`.
