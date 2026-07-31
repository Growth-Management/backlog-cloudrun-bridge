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

Push-Location $Root
try {
    & $PythonExe -m scripts.check_sync_issue_map_v2
    if ($LASTEXITCODE -ne 0) {
        throw "sync_issue_map check failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
