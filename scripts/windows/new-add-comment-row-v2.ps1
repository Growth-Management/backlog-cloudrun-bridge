param(
    [Parameter(Mandatory = $true)]
    [string]$IssueKey,

    [Parameter(Mandatory = $true)]
    [string]$CommentBody,

    [string]$RequestedBy = "篠原邦昭",

    [string]$ProjectKey = "ICESAO_GENTASK"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$DatePart = Get-Date -Format "yyyyMMdd"
$HashInput = "$IssueKey`n$CommentBody"
$HashBytes = [System.Text.Encoding]::UTF8.GetBytes($HashInput)
$ShortHash = ([System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($HashBytes)) -replace "-", "").Substring(0, 12).ToLowerInvariant()
$QueueId = "WQV2-$DatePart-$ShortHash"
$IdempotencyKey = "issue:$($IssueKey):comment:$ShortHash"

$Payload = [ordered]@{
    action = "add_comment"
    project_key = $ProjectKey
    target_issue_key = $IssueKey
    comment_body = $CommentBody
} | ConvertTo-Json -Compress

$Columns = @(
    $QueueId,
    $Now,
    $RequestedBy,
    "Manual",
    $ProjectKey,
    "add_comment",
    $IssueKey,
    "",
    "",
    $CommentBody,
    "",
    "",
    "",
    "",
    "",
    "",
    $Payload,
    $IdempotencyKey,
    "queued",
    "0",
    "",
    "",
    "",
    "",
    "",
    "手動テンプレート生成",
    ""
)

$Line = $Columns -join "`t"
$Line | Set-Clipboard
$Line
Write-Host ""
Write-Host "TSV row copied to clipboard."
