param(
    [string]$TaskName = "Backlog IWTECH_SYSOP Delta Sync v2",
    [string]$DailyAt = "08:30",
    [int]$WriteQueueMaxRows = 20,
    [switch]$RunNow,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = "C:\backlog-sync"
$Runner = Join-Path $Root "tools\run-iwtech-sysop-delta-sync-v2.ps1"
$EnvFile = Join-Path $Root "config\backlog-sync-env.ps1"
$PythonExe = Join-Path $Root ".venv-sync\Scripts\python.exe"
$TaskPath = "\BacklogSync\"

if (-not (Test-Path $Runner)) {
    throw "Runner not found: $Runner"
}
if (-not (Test-Path $EnvFile)) {
    throw "Environment file not found: $EnvFile"
}
if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

try {
    $At = [datetime]::ParseExact($DailyAt, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
}
catch {
    throw "DailyAt must be HH:mm, for example 08:30"
}

$Existing = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing -and -not $Force) {
    throw "Scheduled task already exists: $TaskPath$TaskName. Re-run with -Force to replace it."
}
if ($Existing -and $Force) {
    Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false
}

$ActionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`" -WriteQueueMaxRows $WriteQueueMaxRows"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $ActionArgs -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings `
    -Description "Runs IWTECH_SYSOP delta sync through write_queue_v2 and reconciles sync cursors."

Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -InputObject $Task | Out-Null

if ($RunNow) {
    Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
}

Write-Output "registered=$TaskPath$TaskName"
Write-Output "daily_at=$DailyAt"
Write-Output "write_queue_max_rows=$WriteQueueMaxRows"
Write-Output "run_now=$RunNow"
