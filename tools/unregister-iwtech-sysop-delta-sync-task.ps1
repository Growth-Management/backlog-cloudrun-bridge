param(
    [string]$TaskName = "Backlog IWTECH_SYSOP Delta Sync v2"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskPath = "\BacklogSync\"
$Existing = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $Existing) {
    Write-Output "not_found=$TaskPath$TaskName"
    exit 0
}

Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false
Write-Output "unregistered=$TaskPath$TaskName"
