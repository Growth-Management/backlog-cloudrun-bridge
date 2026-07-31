param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$EnvFile = (Join-Path $RepoRoot "config\backlog-sync-env.ps1")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}

. $EnvFile

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
$LogFile = Join-Path $LogDir "issues_snapshot-$Timestamp.log"

Push-Location $RepoRoot
try {
    & $PythonExe -m scripts.sync_issues_snapshot *>&1 | Tee-Object -FilePath $LogFile
    if ($LASTEXITCODE -ne 0) {
        throw "issues_snapshot sync failed with exit code $LASTEXITCODE. See $LogFile"
    }
} finally {
    Pop-Location
}
