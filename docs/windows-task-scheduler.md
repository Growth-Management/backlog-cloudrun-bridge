# Windows Task Scheduler setup

Backlog の許可IP内PCで `issues_snapshot` 同期と `write_queue` 反映を定期実行するための手順です。

## ファイル構成

```text
scripts/windows/
  backlog-sync-env.example.ps1
  backlog-sync-env.ps1        # ローカル作成。秘密情報を含むためコミットしない
  run-issues-snapshot-sync.ps1
  run-write-queue-processor.ps1
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

## 3. タスクスケジューラへ登録

初期推奨は次の頻度です。

- `issues_snapshot`: 30分ごと
- `write_queue`: 5分ごと

PowerShell を管理者として開き、必要に応じてパスを実PCのリポジトリ場所に合わせて実行します。

```powershell
$RepoRoot = "C:\Users\sinohara\backlog-cloudrun-bridge"
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

schtasks /Create /F /SC MINUTE /MO 30 /TN "Backlog Issues Snapshot Sync" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-issues-snapshot-sync.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00

schtasks /Create /F /SC MINUTE /MO 5 /TN "Backlog Write Queue Processor" /TR "`"$PowerShell`" -NoProfile -ExecutionPolicy Bypass -File `"$RepoRoot\scripts\windows\run-write-queue-processor.ps1`" -RepoRoot `"$RepoRoot`"" /ST 09:00
```

## 4. 登録後の確認

登録済みタスクを確認します。

```powershell
schtasks /Query /TN "Backlog Issues Snapshot Sync" /V /FO LIST
schtasks /Query /TN "Backlog Write Queue Processor" /V /FO LIST
```

手動で即時実行します。

```powershell
schtasks /Run /TN "Backlog Issues Snapshot Sync"
schtasks /Run /TN "Backlog Write Queue Processor"
```

ログは `BACKLOG_SYNC_LOG_DIR` に出力されます。

```powershell
Get-ChildItem C:\Users\sinohara\backlog-cloudrun-bridge\logs | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-Content C:\Users\sinohara\backlog-cloudrun-bridge\logs\write_queue-*.log -Tail 20
```

## 5. 停止・削除

一時停止する場合:

```powershell
schtasks /Change /TN "Backlog Issues Snapshot Sync" /DISABLE
schtasks /Change /TN "Backlog Write Queue Processor" /DISABLE
```

再開する場合:

```powershell
schtasks /Change /TN "Backlog Issues Snapshot Sync" /ENABLE
schtasks /Change /TN "Backlog Write Queue Processor" /ENABLE
```

削除する場合:

```powershell
schtasks /Delete /TN "Backlog Issues Snapshot Sync" /F
schtasks /Delete /TN "Backlog Write Queue Processor" /F
```

## 運用メモ

- `backlog-sync-env.ps1` には Backlog API key を含めるため、許可IP内PCだけに保存します。
- Google OAuth token は `C:\secure` など、通常ユーザー以外が読めない場所へ置きます。
- `write_queue` は `approval_status=approved` かつ `execution_status=queued` の行だけ処理します。
- 失敗時は `execution_status=failed`、`validation_error`、`retry_count` を確認します。
- 大量反映を避けるため、初期値では `WRITE_QUEUE_MAX_ROWS=20` にしています。
