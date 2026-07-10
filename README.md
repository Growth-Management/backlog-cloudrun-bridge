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
tools/
  run-issues-snapshot-sync.ps1
  run-write-queue-processor.ps1
  run-write-queue-processor-v2.ps1
  run-iwtech-sysop-prequeue-v2.ps1
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

## Operation Docs

- `docs/issues-snapshot-sync.md`: Backlog issue snapshot sync and legacy write queue details
- `docs/windows-task-scheduler.md`: Windows Task Scheduler registration and logs
- `docs/write-queue-v2.md`: standard v2 queue columns, lifecycle, and IWTECH_SYSOP pre-queue scope

## Safety Rules

- Keep Backlog API keys and Google credentials only on the resident PC.
- Keep legacy `write_queue` and standard `write_queue_v2` as separate flows while v2 is being verified.
- Treat display names such as status, priority, and assignee names as input values that require mapping before Backlog API writes.
- Use `request_payload_json`, `idempotency_key`, `status`, and `retry_count` in `write_queue_v2` as the minimum safety line.
