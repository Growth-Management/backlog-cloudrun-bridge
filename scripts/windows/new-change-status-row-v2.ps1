param(
    [Parameter(Mandatory = $true)]
    [string]$IssueKey,

    [Parameter(Mandatory = $true)]
    [string]$NewStatusName,

    [string]$RequestedBy = "篠原邦昭",

    [string]$ProjectKey = "ICESAO_GENTASK"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$DatePart = Get-Date -Format "yyyyMMdd"
$HashInput = "$IssueKey`n$NewStatusName"
$HashBytes = [System.Text.Encoding]::UTF8.GetBytes($HashInput)
$ShortHash = ([System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($HashBytes)) -replace "-", "").Substring(0, 12).ToLowerInvariant()
$QueueId = "WQV2-$DatePart-$ShortHash"
$IdempotencyKey = "issue:$($IssueKey):status:$NewStatusName"

$Payload = [ordered]@{
    action = "change_status"
    project_key = $ProjectKey
    target_issue_key = $IssueKey
    new_status_name = $NewStatusName
} | ConvertTo-Json -Compress

$Columns = @(
    $QueueId, $Now, $RequestedBy, "Manual", $ProjectKey,
    "change_status", $IssueKey, "", "", "",
    $NewStatusName, "", "", "", "", "",
    $Payload, $IdempotencyKey, "queued", "0",
    "", "", "", "", "", "手動テンプレート生成",
    "status_mapping に対象状態がある場合のみ本実行可"
)

$OutDir = Join-Path (Get-Location) "output"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutFile = Join-Path $OutDir "$QueueId.tsv"

$Line = $Columns -join "`t"
$Line | Set-Content -Path $OutFile -Encoding UTF8
$Line
Write-Host ""
Write-Host "TSV row written to: $OutFile"
