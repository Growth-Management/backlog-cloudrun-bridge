# Windows Task Scheduler setup

Backlog の許可IP内PCで `issues_snapshot` 同期、旧 `write_queue` 反映、標準列ベースの `write_queue_v2` 反映を定期実行するための手順です。

## ファイル構成

```text
scripts/windows/
  backlog-sync-env.example.ps1
  backlog-sync-env.ps1        # ローカル作成。秘密情報を含むためコミットしない
  run-issues-snapshot-sync.ps1
  run-write-queue-processor.ps1
  run-write-queue-processor-v2.ps1
  run-iwtech-sysop-prequeue-v2.ps1
```

## 1. ローカル環境設定ファイルを作成

リポジトリ直下で実行します。

```powershell
Copy-Item .\scripts\windows\backlog-sync-env.example.ps1 .\scripts\windows\backlog-sync-env.ps1
notepad .\scripts\windows\backlog-sync-env.ps1
```

最低限、次の値を実環境に合わせます。

```powershell
$env:BACKLOG_API_KEY = "Backlog API key"
$env:GOOGLE_OAUTH_CLIENT_SECRET_FILE = "C:\secure\google-oauth-client-secret.json"
$env:GOOGLE_OAUTH_TOKEN_FILE = "C:\secure\google-oauth-token.json"
$env:BACKLOG_SYNC_LOG_DIR = "C:\Users\sinohara\backlog-cloudrun-bridge\logs"
```

`write_queue_v2` の `create_issue` と IWTECH_SYSOP 前段処理を使う場合は、Backlog の実環境値を確認して次も設定します。

```powershell
$env:TARGET_PROJECT_ID = "ICESAO_GENTASK project id"
$env:BACKLOG_DEFAULT_ISSUE_TYPE_ID = "default issue type id"
$env:BACKLOG_DEFAULT_PRIORITY_ID = "3"
$env:BACKLOG_DEFAULT_ASSIGNEE_ID = "115000"
$env:SOURCE_PROJECT_KEY = "IWTECH_SYSOP"
$env:TARGET_PROJECT_KEY = "ICESAO_GENTASK"
```

対象スプレッドシートは次のIDを既定値にしています。

```text
1muUdmTqJYQV9FOzoCR1lkM-ie9QWfYjQYf__6YF_Hlo
```

## 2. 手動確認

タスク登録前に、PowerShell から手動実行します。

```powershell
.\scripts\windows\run-issues-snapshot-sync.ps1
.\scripts\windows\run-write-queue-processor.ps1 -DryRun
```

実反映を有効にする場合は、`backlog-sync-env.ps1` で次の値にします。

```powershell
$env:WRITE_QUEUE_DRY_RUN = "false"
```

そのうえで実行します。

```powershell
.\scripts\windows\run-write-queue-processor.ps1
```

## 3. write_queue_v2 の手動確認

v2 は旧 `write_queue` を置き換えず、`write_queue_v2` として並走確認します。

まず前段処理を DryRun で実行します。特定課題だけで確認したい場合は `SOURCE_ISSUE_KEYS` を指定します。

```powershell
$env:SOURCE_ISSUE_KEYS = "IWTECH_SYSOP-1"
.\scripts\windows\run-iwtech-sysop-prequeue-v2.ps1 -DryRun
```

生成内容に問題がなければ、前段処理で `write_queue_v2` と `sync_issue_map` に追記します。

```powershell
.\scripts\windows\run-iwtech-sysop-prequeue-v2.ps1
```

次に v2 キュー処理を DryRun で検証します。

```powershell
.\scripts\windows\run-write-queue-processor-v2.ps1 -DryRun
```

実反映する場合は、既存の v2 スケジュールを一時停止した状態で 1 件ずつ手動実行します。

```powershell
.\scripts\windows\run-write-queue-processor-v2.ps1
```

## 4. タスクスケジューラへ登録

初期推奨は次の頻度です。

- `issues_snapshot`: 30分ごと
- legacy `write_queue`: 5分ごと
- `IWTECH_SYSOP` pre-queue: 15分ごと
- `write_queue_v2`: 15分ごと

PowerShell を管理者として開き、必要に応じてパスを実PCのリポジトリ場所に合わせて実行します。

```powershell
$RepoRoot = "C:\Users\sinohara\backlog-cloudrun-bridge"
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

schtasks /Create /F /SC MINUTE /MO 30 /TN "Backlog Issues Snapshot Sync" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-issues-snapshot-sync.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00

schtasks /Create /F /SC MINUTE /MO 5 /TN "Backlog Write Queue Processor" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-write-queue-processor.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00

schtasks /Create /F /SC MINUTE /MO 15 /TN "Backlog IWTECH SYSOP Prequeue V2" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-iwtech-sysop-prequeue-v2.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00

schtasks /Create /F /SC MINUTE /MO 15 /TN "Backlog Write Queue V2 Processor" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-write-queue-processor-v2.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00
```

## 5. 登録後の確認

登録済みタスクを確認します。

```powershell
schtasks /Query /TN "Backlog Issues Snapshot Sync" /V /FO LIST
schtasks /Query /TN "Backlog Write Queue Processor" /V /FO LIST
schtasks /Query /TN "Backlog IWTECH SYSOP Prequeue V2" /V /FO LIST
schtasks /Query /TN "Backlog Write Queue V2 Processor" /V /FO LIST
```

手動で即時実行します。

```powershell
schtasks /Run /TN "Backlog Issues Snapshot Sync"
schtasks /Run /TN "Backlog Write Queue Processor"
schtasks /Run /TN "Backlog IWTECH SYSOP Prequeue V2"
schtasks /Run /TN "Backlog Write Queue V2 Processor"
```

ログは `BACKLOG_SYNC_LOG_DIR` に出力されます。

```powershell
Get-ChildItem C:\Users\sinohara\backlog-cloudrun-bridge\logs | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-Content C:\Users\sinohara\backlog-cloudrun-bridge\logs\write_queue-*.log -Tail 20
Get-Content C:\Users\sinohara\backlog-cloudrun-bridge\logs\write_queue_v2-*.log -Tail 20
Get-Content C:\Users\sinohara\backlog-cloudrun-bridge\logs\iwtech-sysop-prequeue-v2-*.log -Tail 20
```

## 6. 停止・削除

一時停止する場合:

```powershell
schtasks /Change /TN "Backlog Issues Snapshot Sync" /DISABLE
schtasks /Change /TN "Backlog Write Queue Processor" /DISABLE
schtasks /Change /TN "Backlog IWTECH SYSOP Prequeue V2" /DISABLE
schtasks /Change /TN "Backlog Write Queue V2 Processor" /DISABLE
```

再開する場合:

```powershell
schtasks /Change /TN "Backlog Issues Snapshot Sync" /ENABLE
schtasks /Change /TN "Backlog Write Queue Processor" /ENABLE
schtasks /Change /TN "Backlog IWTECH SYSOP Prequeue V2" /ENABLE
schtasks /Change /TN "Backlog Write Queue V2 Processor" /ENABLE
```

削除する場合:

```powershell
schtasks /Delete /TN "Backlog Issues Snapshot Sync" /F
schtasks /Delete /TN "Backlog Write Queue Processor" /F
schtasks /Delete /TN "Backlog IWTECH SYSOP Prequeue V2" /F
schtasks /Delete /TN "Backlog Write Queue V2 Processor" /F
```

## 運用メモ

- `backlog-sync-env.ps1` には Backlog API key を含めるため、許可IP内PCだけに保存します。
- Google OAuth token は `C:\secure` など、通常ユーザー以外が読めない場所へ置きます。
- 旧 `write_queue` は `approval_status=approved` かつ `execution_status=queued` の行だけ処理します。
- `write_queue_v2` は `status=queued` の行だけ処理します。
- `write_queue_v2` では `request_payload_json`、`idempotency_key`、`status`、`retry_count` を最小安全ラインとして維持します。
- `new_status_name`、`new_priority_name`、`assignee_name` は表示値であり、Backlog API に直接送らない前提です。
- v2 の初期実装では `add_comment` と `create_issue` を対象にし、IWTECH_SYSOP 前段処理は未同期元課題の create キュー投入までを担当します。
- v2 の失敗時は `status=failed`、`last_error_code`、`last_error_message`、`retry_count` を確認します。
- 大量反映を避けるため、初期値では `WRITE_QUEUE_MAX_ROWS=20` にしています。
