param(
    [switch]$DryRun,
    [int]$WriteQueueMaxRows = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = "C:\backlog-sync"
$EnvFile = Join-Path $Root "config\backlog-sync-env.ps1"
$PythonExe = Join-Path $Root ".venv-sync\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"

if (-not (Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}
if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
. $EnvFile

$env:WRITE_QUEUE_SHEET_NAME = "write_queue_v2"
$env:WORKER_NAME = "backlog-sync-worker-v2"
$env:WRITE_QUEUE_MAX_ROWS = [string]$WriteQueueMaxRows
$env:CHECK_ALLOWED_ATTENTION_QUEUE_IDS = @(
    "WQV2-20260703-001",
    "WQV2-20260708-PRIORITY-DRYRUN-001",
    "WQV2-IWTECH-STATUS-20260713-060104-013-de4714",
    "WQV2-IWTECH-STATUS-20260713-060106-020-21c583"
) -join ","

if ($DryRun) {
    $env:SYNC_DRY_RUN = "true"
    $env:WRITE_QUEUE_DRY_RUN = "true"
}
else {
    $env:SYNC_DRY_RUN = "false"
    $env:WRITE_QUEUE_DRY_RUN = "false"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "iwtech-sysop-delta-sync-v2-$Timestamp.log"

function Invoke-Step {
    param(
        [string]$Name,
        [string]$Module
    )

    "step=$Name started_at=$(Get-Date -Format o)" | Tee-Object -FilePath $LogFile -Append
    $Output = & $PythonExe -m $Module 2>&1
    $ExitCode = $LASTEXITCODE

    foreach ($Item in $Output) {
        $line = $Item.ToString()
        $safeLine = $line.Replace($env:BACKLOG_API_KEY, "***")
        $safeLine | Tee-Object -FilePath $LogFile -Append
    }

    if ($ExitCode -ne 0) {
        throw "$Name failed with exit code $ExitCode. See $LogFile"
    }
    "step=$Name finished_at=$(Get-Date -Format o)" | Tee-Object -FilePath $LogFile -Append
}

Push-Location $Root
try {
    "started_at=$(Get-Date -Format o)" | Tee-Object -FilePath $LogFile
    "dry_run=$DryRun" | Tee-Object -FilePath $LogFile -Append
    "write_queue_max_rows=$env:WRITE_QUEUE_MAX_ROWS" | Tee-Object -FilePath $LogFile -Append

    Invoke-Step "comment_prequeue" "scripts.prepare_iwtech_sysop_comment_queue_v2"
    Invoke-Step "update_prequeue" "scripts.prepare_iwtech_sysop_update_queue_v2"
    if ($DryRun) {
        "step=write_queue_processor skipped_for_dry_run=true" | Tee-Object -FilePath $LogFile -Append
    }
    else {
        Invoke-Step "write_queue_processor" "scripts.process_write_queue_v2_noop_status"
    }
    if ($DryRun) {
        "step=cursor_reconcile skipped_for_dry_run=true" | Tee-Object -FilePath $LogFile -Append
    }
    else {
        Invoke-Step "cursor_reconcile" "scripts.reconcile_iwtech_sysop_sync_cursors_v2"
    }
    Invoke-Step "write_queue_status_check" "scripts.check_write_queue_v2_status"
    Invoke-Step "sync_issue_map_check" "scripts.check_sync_issue_map_v2"

    "finished_at=$(Get-Date -Format o)" | Tee-Object -FilePath $LogFile -Append
}
finally {
    Pop-Location
}