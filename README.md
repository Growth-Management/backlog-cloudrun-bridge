# backlog-sync-bridge

Backlog and Google Sheets sync tools for the resident Windows PC at `C:\backlog-sync` inside the Backlog allowed-IP network.

This repository is local-run first. It is not a Cloud Run service and does not expose a public API. Google Sheets is the handoff interface between operators, ChatGPT-assisted queue preparation, and the resident PC worker.

## Local Directory Shape

The resident PC layout is:

```text
C:\backlog-sync\
  .venv-sync\
  config\
  logs\
  output\
  scripts\
  tools\
  assignee_mapping.tsv
  priority_mapping.tsv
```

Repository-managed source should live in `scripts/`, `tools/`, `config/`, `docs/`, and root reference files. Runtime output stays local and is ignored.

## What This Syncs

- Backlog issues -> Google Sheets `issues_snapshot`
- Google Sheets legacy `write_queue` -> Backlog writeback
- Google Sheets standard `write_queue_v2` -> Backlog writeback
- `IWTECH_SYSOP` source issues -> `write_queue_v2` `create_issue` rows for `ICESAO_GENTASK`

## Main Files

```text
scripts/
  google_sheets_auth.py
  sync_issues_snapshot.py
  process_write_queue.py
  process_write_queue_v2.py
  prepare_iwtech_sysop_queue_v2.py
  prepare_iwtech_sysop_comment_queue_v2.py
  prepare_iwtech_sysop_update_queue_v2.py
  reconcile_iwtech_sysop_sync_cursors_v2.py
  check_write_queue_v2_status.py
  check_sync_issue_map_v2.py
tools/
  run-issues-snapshot-sync.ps1
  run-write-queue-processor.ps1
  run-write-queue-processor-v2.ps1
  run-iwtech-sysop-prequeue-v2.ps1
  run-iwtech-sysop-comment-prequeue-v2.ps1
  run-iwtech-sysop-update-prequeue-v2.ps1
  run-reconcile-iwtech-sysop-cursors-v2.ps1
  run-iwtech-sysop-delta-sync-v2.ps1
  register-iwtech-sysop-delta-sync-task.ps1
  unregister-iwtech-sysop-delta-sync-task.ps1
  check-write-queue-v2-status.ps1
  check-sync-issue-map-v2.ps1
config/
  backlog-sync-env.example.ps1
docs/
  issues-snapshot-sync.md
  windows-task-scheduler.md
  write-queue-v2.md
```

## Local Setup

```powershell
cd C:\backlog-sync
python -m venv .venv-sync
.\.venv-sync\Scripts\python.exe -m pip install -r requirements-sync.txt
Copy-Item .\config\backlog-sync-env.example.ps1 .\config\backlog-sync-env.ps1
notepad .\config\backlog-sync-env.ps1
```

Do not commit `config\backlog-sync-env.ps1`, OAuth tokens, API keys, Google client secrets, logs, or output files.

## Manual Runs

```powershell
.\tools\run-issues-snapshot-sync.ps1
.\tools\run-write-queue-processor.ps1 -DryRun
.\tools\run-iwtech-sysop-prequeue-v2.ps1 -DryRun
.\tools\run-write-queue-processor-v2.ps1 -DryRun
```

## IWTECH_SYSOP Delta Sync

Use the combined runner for normal delta operation after the initial create/comment/update sync has been reconciled.

```powershell
.\tools\run-iwtech-sysop-delta-sync-v2.ps1 -DryRun
.\tools\run-iwtech-sysop-delta-sync-v2.ps1
```

The dry-run mode runs the pre-queue and check steps but skips the write queue processor so existing `queued` rows are not changed to `validated` by accident.

For a small controlled batch, set the worker limit:

```powershell
.\tools\run-iwtech-sysop-delta-sync-v2.ps1 -WriteQueueMaxRows 5
```

## Windows Task Scheduler

Register the normal IWTECH_SYSOP delta sync as the current Windows user. The task runs only when that user is logged on, which keeps Google OAuth token access aligned with the resident PC setup.

```powershell
.\tools\register-iwtech-sysop-delta-sync-task.ps1 -DailyAt 08:30 -WriteQueueMaxRows 20
```

Replace an existing task or start it immediately:

```powershell
.\tools\register-iwtech-sysop-delta-sync-task.ps1 -DailyAt 08:30 -WriteQueueMaxRows 20 -Force
.\tools\register-iwtech-sysop-delta-sync-task.ps1 -DailyAt 08:30 -WriteQueueMaxRows 20 -Force -RunNow
```

Remove the task:

```powershell
.\tools\unregister-iwtech-sysop-delta-sync-task.ps1
```

## Daily Checks

```powershell
.\tools\check-write-queue-v2-status.ps1
.\tools\check-sync-issue-map-v2.ps1
```

`check-write-queue-v2-status.ps1` reports `queued`, `processing`, `failed`, and `on_hold` rows that need attention. `check-sync-issue-map-v2.ps1` reports map inconsistencies such as duplicate source/target issue keys or created rows without a target issue key.

## Operation Docs

- `docs/issues-snapshot-sync.md`: Backlog issue snapshot sync and legacy write queue details
- `docs/windows-task-scheduler.md`: Windows Task Scheduler registration and logs
- `docs/write-queue-v2.md`: standard v2 queue columns, lifecycle, and IWTECH_SYSOP pre-queue scope

## Safety Rules

- Keep Backlog API keys and Google credentials only on the resident PC.
- Keep legacy `write_queue` and standard `write_queue_v2` as separate flows while v2 is being verified.
- Treat display names such as status, priority, and assignee names as input values that require mapping before Backlog API writes.
- Use `request_payload_json`, `idempotency_key`, `status`, and `retry_count` in `write_queue_v2` as the minimum safety line.
