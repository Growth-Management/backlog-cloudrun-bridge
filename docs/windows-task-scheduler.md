# Windows Task Scheduler Setup

Backlog allowed-IP resident PC tasks for `backlog-sync-bridge`.

## Files

```text
scripts/windows/
  backlog-sync-env.example.ps1
  backlog-sync-env.ps1        # local only, contains secrets
  run-issues-snapshot-sync.ps1
  run-write-queue-processor.ps1
  run-write-queue-processor-v2.ps1
  run-iwtech-sysop-prequeue-v2.ps1
```

## Setup

```powershell
$RepoRoot = "C:\Users\sinohara\backlog-sync-bridge"
Copy-Item "$RepoRoot\scripts\windows\backlog-sync-env.example.ps1" "$RepoRoot\scripts\windows\backlog-sync-env.ps1"
notepad "$RepoRoot\scripts\windows\backlog-sync-env.ps1"
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

```powershell
.\scripts\windows\run-issues-snapshot-sync.ps1
.\scripts\windows\run-write-queue-processor.ps1 -DryRun
.\scripts\windows\run-iwtech-sysop-prequeue-v2.ps1 -DryRun
.\scripts\windows\run-write-queue-processor-v2.ps1 -DryRun
```

For a controlled IWTECH_SYSOP test, limit the source issue set first:

```powershell
$env:SOURCE_ISSUE_KEYS = "IWTECH_SYSOP-1"
.\scripts\windows\run-iwtech-sysop-prequeue-v2.ps1 -DryRun
```

## Suggested Tasks

Initial frequency:

- `issues_snapshot`: every 30 minutes
- legacy `write_queue`: every 5 minutes
- `IWTECH_SYSOP` pre-queue: every 15 minutes
- `write_queue_v2`: every 15 minutes

```powershell
$RepoRoot = "C:\Users\sinohara\backlog-sync-bridge"
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

schtasks /Create /F /SC MINUTE /MO 30 /TN "Backlog Issues Snapshot Sync" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-issues-snapshot-sync.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00

schtasks /Create /F /SC MINUTE /MO 5 /TN "Backlog Write Queue Processor" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-write-queue-processor.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00

schtasks /Create /F /SC MINUTE /MO 15 /TN "Backlog IWTECH SYSOP Prequeue V2" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-iwtech-sysop-prequeue-v2.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00

schtasks /Create /F /SC MINUTE /MO 15 /TN "Backlog Write Queue V2 Processor" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-write-queue-processor-v2.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00
```

## Logs

```powershell
Get-ChildItem C:\Users\sinohara\backlog-sync-bridge\logs | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-Content C:\Users\sinohara\backlog-sync-bridge\logs\write_queue_v2-*.log -Tail 20
Get-Content C:\Users\sinohara\backlog-sync-bridge\logs\iwtech-sysop-prequeue-v2-*.log -Tail 20
```

## Safety Notes

- `backlog-sync-env.ps1` stays local and must not be committed.
- Keep OAuth tokens and Backlog API keys outside the repository when possible.
- Legacy `write_queue` processes `approval_status=approved` and `execution_status=queued`.
- `write_queue_v2` processes `status=queued`.
- v2 must keep `request_payload_json`, `idempotency_key`, `status`, and `retry_count`.
