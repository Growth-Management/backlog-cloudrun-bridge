Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = "C:\backlog-sync"
$EnvFile = Join-Path $Root "config\backlog-sync-env.ps1"
$PythonExe = Join-Path $Root ".venv-sync\Scripts\python.exe"

if (-not (Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}
if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

. $EnvFile
$env:WRITE_QUEUE_SHEET_NAME = "write_queue_v2"

Push-Location $Root
try {
    & $PythonExe -m scripts.check_write_queue_v2_status
    if ($LASTEXITCODE -ne 0) {
        throw "write_queue_v2 status check failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
