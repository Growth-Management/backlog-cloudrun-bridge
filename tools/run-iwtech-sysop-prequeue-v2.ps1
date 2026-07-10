param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$EnvFile = (Join-Path $RepoRoot "config\backlog-sync-env.ps1"),
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}

. $EnvFile

$env:WRITE_QUEUE_SHEET_NAME = "write_queue_v2"
$env:SOURCE_PROJECT_KEY = if ($env:SOURCE_PROJECT_KEY) { $env:SOURCE_PROJECT_KEY } else { "IWTECH_SYSOP" }
$env:TARGET_PROJECT_KEY = if ($env:TARGET_PROJECT_KEY) { $env:TARGET_PROJECT_KEY } else { "ICESAO_GENTASK" }

if ($DryRun) {
    $env:SYNC_DRY_RUN = "true"
}

$PythonExe = Join-Path $RepoRoot ".venv-sync\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

$LogDir = if ($env:BACKLOG_SYNC_LOG_DIR) {
    $env:BACKLOG_SYNC_LOG_DIR
} else {
    Join-Path $RepoRoot "logs"
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogDir "iwtech-sysop-prequeue-v2-$Timestamp.log"

Push-Location $RepoRoot
try {
    & $PythonExe -m scripts.prepare_iwtech_sysop_queue_v2 *>&1 | Tee-Object -FilePath $LogFile
    if ($LASTEXITCODE -ne 0) {
        throw "IWTECH_SYSOP pre-queue job failed with exit code $LASTEXITCODE. See $LogFile"
    }
} finally {
    Pop-Location
}
