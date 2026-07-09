# backlog-sync-bridge

Backlog and Google Sheets sync tools for a resident Windows PC inside the Backlog allowed-IP network.

This repository is intentionally local-run first. It is not a Cloud Run service and does not expose a public API. The spreadsheet is the handoff interface between operators, ChatGPT-assisted queue preparation, and the resident PC worker.

## What This Syncs

- Backlog issues -> Google Sheets `issues_snapshot`
- Google Sheets legacy `write_queue` -> Backlog writeback
- Google Sheets standard `write_queue_v2` -> Backlog writeback
- `IWTECH_SYSOP` source issues -> `write_queue_v2` `create_issue` rows for `ICESAO_GENTASK`

## Runtime Shape

```text
Backlog API
  ^
  | allowed-IP resident Windows PC
  |
Google Sheets
  - issues_snapshot
  - write_queue
  - write_queue_v2
  - sync_issue_map
  - sync_comment_map
  - sync_error_log
```

## Main Files

```text
scripts/
  google_sheets_auth.py
  sync_issues_snapshot.py
  process_write_queue.py
  process_write_queue_v2.py
  prepare_iwtech_sysop_queue_v2.py
scripts/windows/
  backlog-sync-env.example.ps1
  run-issues-snapshot-sync.ps1
  run-write-queue-processor.ps1
  run-write-queue-processor-v2.ps1
  run-iwtech-sysop-prequeue-v2.ps1
docs/
  issues-snapshot-sync.md
  windows-task-scheduler.md
  write-queue-v2.md
```

## Local Setup

```powershell
python -m venv .venv-sync
.\.venv-sync\Scripts\python.exe -m pip install -r requirements-sync.txt
Copy-Item .\scripts\windows\backlog-sync-env.example.ps1 .\scripts\windows\backlog-sync-env.ps1
notepad .\scripts\windows\backlog-sync-env.ps1
```

Do not commit `backlog-sync-env.ps1`, OAuth tokens, API keys, or Google client secrets.

## Manual Runs

```powershell
.\scripts\windows\run-issues-snapshot-sync.ps1
.\scripts\windows\run-write-queue-processor.ps1 -DryRun
.\scripts\windows\run-iwtech-sysop-prequeue-v2.ps1 -DryRun
.\scripts\windows\run-write-queue-processor-v2.ps1 -DryRun
```

## Operation Docs

- `docs/issues-snapshot-sync.md`: Backlog issue snapshot sync and legacy write queue details
- `docs/windows-task-scheduler.md`: Windows Task Scheduler registration and logs
- `docs/write-queue-v2.md`: standard v2 queue columns, lifecycle, and IWTECH_SYSOP pre-queue scope

## Safety Rules

- Keep Backlog API keys and Google credentials only on the resident PC.
- Keep legacy `write_queue` and standard `write_queue_v2` as separate flows while v2 is being verified.
- Treat display names such as status, priority, and assignee names as input values that require mapping before Backlog API writes.
- Use `request_payload_json`, `idempotency_key`, `status`, and `retry_count` in `write_queue_v2` as the minimum safety line.
