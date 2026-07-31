param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$EnvFile = (Join-Path $PSScriptRoot "backlog-sync-env.ps1"),
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}

$PythonExe = Join-Path $RepoRoot ".venv-sync\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

. $EnvFile

$env:WRITE_QUEUE_MAX_ROWS = "1"
$env:WORKER_NAME = "backlog-sync-worker-v2"
if (-not $env:WRITE_QUEUE_SHEET_NAME) {
    $env:WRITE_QUEUE_SHEET_NAME = "write_queue_v2"
}

if ($DryRun) {
    $env:WRITE_QUEUE_DRY_RUN = "true"
}
else {
    $env:WRITE_QUEUE_DRY_RUN = "false"
}

$LogDir = if ($env:BACKLOG_SYNC_LOG_DIR) {
    $env:BACKLOG_SYNC_LOG_DIR
} else {
    Join-Path $RepoRoot "logs"
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "write_queue_v2-$Timestamp.log"

Push-Location $RepoRoot
try {
    "started_at=$(Get-Date -Format o)" | Tee-Object -FilePath $LogFile
    "dry_run=$env:WRITE_QUEUE_DRY_RUN" | Tee-Object -FilePath $LogFile -Append

    $Output = & $PythonExe -m scripts.process_write_queue_v2 2>&1
    $ExitCode = $LASTEXITCODE

    foreach ($Item in $Output) {
        $line = $Item.ToString()
        $safeLine = if ($env:BACKLOG_API_KEY) {
            $line.Replace($env:BACKLOG_API_KEY, "***")
        } else {
            $line
        }
        $safeLine | Tee-Object -FilePath $LogFile -Append
    }

    if ($ExitCode -ne 0) {
        throw "write_queue_v2 processor failed with exit code $ExitCode. See $LogFile"
    }

    "finished_at=$(Get-Date -Format o)" | Tee-Object -FilePath $LogFile -Append
}
finally {
    Pop-Location
}
