param(
    [switch]$DryRun
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

$env:WRITE_QUEUE_MAX_ROWS = "1"
$env:WORKER_NAME = "backlog-sync-worker-v2"

if ($DryRun) {
    $env:WRITE_QUEUE_DRY_RUN = "true"
}
else {
    $env:WRITE_QUEUE_DRY_RUN = "false"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "write_queue_v2-$Timestamp.log"

Push-Location $Root
try {
    "started_at=$(Get-Date -Format o)" | Tee-Object -FilePath $LogFile
    "dry_run=$env:WRITE_QUEUE_DRY_RUN" | Tee-Object -FilePath $LogFile -Append

    $Output = & $PythonExe -m scripts.process_write_queue_v2 2>&1
    $ExitCode = $LASTEXITCODE

    foreach ($Item in $Output) {
        $line = $Item.ToString()
        $safeLine = $line.Replace($env:BACKLOG_API_KEY, "***")
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

