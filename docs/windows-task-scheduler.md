# Windows Task Scheduler Setup

Backlog allowed-IP resident PC tasks for `C:\backlog-sync`.

## Files

```text
config/
  backlog-sync-env.example.ps1
  backlog-sync-env.ps1        # local only, contains secrets
tools/
  run-issues-snapshot-sync.ps1
  run-write-queue-processor.ps1
  run-write-queue-processor-v2.ps1
  run-iwtech-sysop-delta-sync-v2.ps1
  register-iwtech-sysop-delta-sync-task.ps1
  unregister-iwtech-sysop-delta-sync-task.ps1
  check-write-queue-v2-status.ps1
  check-sync-issue-map-v2.ps1
```

## Setup

```powershell
$RepoRoot = "C:\backlog-sync"
Copy-Item "$RepoRoot\config\backlog-sync-env.example.ps1" "$RepoRoot\config\backlog-sync-env.ps1"
notepad "$RepoRoot\config\backlog-sync-env.ps1"
```

Set real values for:

```powershell
$env:BACKLOG_API_KEY = "Backlog API key"
$env:GOOGLE_OAUTH_CLIENT_SECRET_FILE = "C:\secure\google-oauth-client-secret.json"
$env:GOOGLE_OAUTH_TOKEN_FILE = "C:\secure\google-oauth-token.json"
$env:TARGET_PROJECT_ID = "ICESAO_GENTASK project id"
$env:BACKLOG_DEFAULT_ISSUE_TYPE_ID = "default issue type id"
$env:BACKLOG_DEFAULT_PRIORITY_ID = "3"
$env:BACKLOG_DEFAULT_ASSIGNEE_ID = "115000"
```

## Manual Verification

Run these before registering the scheduled task:

```powershell
cd C:\backlog-sync
.\tools\check-write-queue-v2-status.ps1
.\tools\check-sync-issue-map-v2.ps1
.\tools\run-iwtech-sysop-delta-sync-v2.ps1 -DryRun
```

If the dry-run output is safe, run one real delta pass manually:

```powershell
.\tools\run-iwtech-sysop-delta-sync-v2.ps1 -WriteQueueMaxRows 5
```

Increase `-WriteQueueMaxRows` after confirming the first scheduled run behavior.

## Register IWTECH_SYSOP Delta Sync

The registration script creates this task:

- Task path: `\BacklogSync\`
- Task name: `Backlog IWTECH_SYSOP Delta Sync v2`
- Action: `tools\run-iwtech-sysop-delta-sync-v2.ps1`
- Principal: current Windows user, interactive logon
- Multiple instances: ignore new runs while one is still running
- Execution time limit: 2 hours

Register a daily task:

```powershell
cd C:\backlog-sync
.\tools\register-iwtech-sysop-delta-sync-task.ps1 -DailyAt 08:30 -WriteQueueMaxRows 20
```

Replace an existing task:

```powershell
.\tools\register-iwtech-sysop-delta-sync-task.ps1 -DailyAt 08:30 -WriteQueueMaxRows 20 -Force
```

Register and start immediately:

```powershell
.\tools\register-iwtech-sysop-delta-sync-task.ps1 -DailyAt 08:30 -WriteQueueMaxRows 20 -Force -RunNow
```

Unregister:

```powershell
.\tools\unregister-iwtech-sysop-delta-sync-task.ps1
```

## Verify Scheduled Task

```powershell
Get-ScheduledTask -TaskPath "\BacklogSync\" -TaskName "Backlog IWTECH_SYSOP Delta Sync v2"
Get-ScheduledTaskInfo -TaskPath "\BacklogSync\" -TaskName "Backlog IWTECH_SYSOP Delta Sync v2"
```

Start manually from Task Scheduler:

```powershell
Start-ScheduledTask -TaskPath "\BacklogSync\" -TaskName "Backlog IWTECH_SYSOP Delta Sync v2"
```

## Logs

```powershell
Get-ChildItem C:\backlog-sync\logs | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-Content C:\backlog-sync\logs\iwtech-sysop-delta-sync-v2-*.log -Tail 80
```

A healthy delta run ends with both checks:

```text
"status": "ok"
"warning_count": 0
```

## Suggested Operating Rhythm

Initial production rhythm:

- Daily IWTECH_SYSOP delta sync at 08:30
- Manual `check-write-queue-v2-status.ps1` after the first few scheduled runs
- Increase `WriteQueueMaxRows` only after queue volume and run time are stable

If near-real-time syncing is needed later, add a second scheduled task at another time or move to a repeated trigger after confirming API and Sheets quota behavior.

## Safety Notes

- `config\backlog-sync-env.ps1` stays local and must not be committed.
- Keep OAuth tokens and Backlog API keys outside the repository when possible.
- The combined runner skips the write queue processor in dry-run mode.
- `write_queue_v2` processes `status=queued`.
- v2 must keep `request_payload_json`, `idempotency_key`, `status`, and `retry_count`.
- The scheduled task runs as the current Windows user because Google OAuth token access is user-scoped.
