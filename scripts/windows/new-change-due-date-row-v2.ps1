param(
    [Parameter(Mandatory = $true)]
    [string]$IssueKey,

    [Parameter(Mandatory = $true)]
    [string]$DueDate,

    [string]$RequestedBy = "篠原邦昭",

    [string]$ProjectKey = "ICESAO_GENTASK"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($DueDate -notmatch '^\d{4}-\d{2}-\d{2}$') {
    throw "DueDate must be yyyy-MM-dd"
}

$Now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$DatePart = Get-Date -Format "yyyyMMdd"
$HashInput = "$IssueKey`n$DueDate"
$HashBytes = [System.Text.Encoding]::UTF8.GetBytes($HashInput)
$ShortHash = ([System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($HashBytes)) -replace "-", "").Substring(0, 12).ToLowerInvariant()
$QueueId = "WQV2-$DatePart-$ShortHash"
$IdempotencyKey = "issue:$($IssueKey):due:$DueDate"

$Payload = [ordered]@{
    action = "change_due_date"
    project_key = $ProjectKey
    target_issue_key = $IssueKey
    due_date = $DueDate
} | ConvertTo-Json -Compress

$Columns = @(
    $QueueId, $Now, $RequestedBy, "Manual", $ProjectKey,
    "change_due_date", $IssueKey, "", "", "",
    "", "", "", $DueDate, "", "",
    $Payload, $IdempotencyKey, "queued", "0",
    "", "", "", "", "", "手動テンプレート生成",
    "due_date は yyyy-MM-dd"
)

$OutDir = Join-Path (Get-Location) "output"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutFile = Join-Path $OutDir "$QueueId.tsv"

$Line = $Columns -join "`t"
$Line | Set-Content -Path $OutFile -Encoding UTF8
$Line
Write-Host ""
Write-Host "TSV row written to: $OutFile"
