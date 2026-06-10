# Backlog issues_snapshot 同期 agent

Backlog の許可IP内にある常時起動PCで実行する読み取り専用の同期 agent です。
Backlog API から課題一覧を取得し、Google Sheets の `issues_snapshot` シートへ反映します。

## 初期スコープ

- Backlog -> Google Sheets の読み取り同期のみ
- `issues_snapshot` は原則 read-only として扱う
- Backlog への書き込みは `write_queue` に承認済み要求を積み、許可IP内PCの agent から反映する

## 前提

- 実行PCが Backlog の許可IP内にある
- Backlog API key を発行済み
- 対象 Google Spreadsheet を操作できる Google ユーザーを用意済み
- Google Workspace の共有ポリシーでサービスアカウントを追加できない場合は、ユーザーOAuth方式を使う

## 同期先シート

既定のシート名は `issues_snapshot` です。
存在しない場合は自動作成します。

列:

| 列 | 内容 |
|---|---|
| `issue_key` | Backlog課題キー |
| `issue_id` | Backlog内部ID |
| `project_key` | Backlogプロジェクトキー |
| `summary` | 件名 |
| `description` | 説明 |
| `status_id` / `status_name` | 状態 |
| `priority_id` / `priority_name` | 優先度 |
| `issue_type_id` / `issue_type_name` | 種別 |
| `assignee_id` / `assignee_name` | 担当者 |
| `start_date` / `due_date` | 開始日・期限 |
| `created` / `updated` | Backlog側日時 |
| `url` | Backlog課題URL |
| `last_synced_at` | 同期日時 |
| `row_hash` | 差分検知用ハッシュ |

## セットアップ

```bash
python -m venv .venv-sync
source .venv-sync/bin/activate
python -m pip install -r requirements-sync.txt
```

Google Sheets 認証は、ユーザーOAuth方式とサービスアカウント方式に対応しています。
Google Workspace の共有ポリシーで `gserviceaccount.com` を Spreadsheet に共有できない場合は、ユーザーOAuth方式を使います。

ユーザーOAuth方式では、Google Cloud Console で OAuth クライアントを作成し、デスクトップアプリ用の client secret JSON を実行PCに配置します。

## 環境変数

必須:

```bash
export BACKLOG_API_KEY="Backlog API key"
export GOOGLE_SHEETS_SPREADSHEET_ID="Google Spreadsheet ID"
```

任意:

```bash
export BACKLOG_BASE_URL="https://ice.backlog.jp"
export BACKLOG_PROJECT_KEY="ICESAO_GENTASK"
export GOOGLE_AUTH_MODE="user_oauth"
export GOOGLE_OAUTH_CLIENT_SECRET_FILE="/path/to/oauth-client-secret.json"
export GOOGLE_OAUTH_TOKEN_FILE="/path/to/google-oauth-token.json"
export ISSUES_SNAPSHOT_SHEET_NAME="issues_snapshot"
export ISSUES_SYNC_PAGE_SIZE="100"
export ISSUES_SYNC_MAX_PAGES="10"
export BACKLOG_TIMEOUT_SECONDS="20"
```

サービスアカウント方式を使う場合:

```bash
export GOOGLE_AUTH_MODE="service_account"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

## 手動実行

```bash
python scripts/sync_issues_snapshot.py
```

ユーザーOAuth方式では、初回実行時にブラウザ認証が開きます。
認証後、`GOOGLE_OAUTH_TOKEN_FILE` にトークンが保存され、以降の定期実行では保存済みトークンを利用します。

成功時は次のような JSON を標準出力に出します。

```json
{"status":"ok","sheet":"issues_snapshot","synced_count":120,"synced_at":"2026-06-10T00:00:00+00:00"}
```

## 同期頻度

初期推奨:

- 通常同期: 15分ごと
- master系同期: 後続タスクで 1日1回
- Backlog反映キュー: 5分ごと

## Windows タスクスケジューラ例

15分ごとに実行する場合:

```powershell
schtasks /Create /SC MINUTE /MO 15 /TN "BacklogIssuesSnapshotSync" /TR "C:\path\to\repo\.venv-sync\Scripts\python.exe C:\path\to\repo\scripts\sync_issues_snapshot.py"
```

環境変数は、実行ユーザーのユーザー環境変数、または `.cmd` ラッパーで設定します。

## セキュリティ

- Backlog API key は許可IP内PCのみに配置する
- Google OAuth client secret と token は一般ユーザーが読める場所に置かない
- サービスアカウント方式を使う場合は、対象 Spreadsheet への最小権限にする
- PCを外部公開しない
- `issues_snapshot` は同期結果として扱い、人手編集しない
- Backlogへの書き込みは `write_queue` 経由に限定する

## write_queue 反映

`write_queue` シートに承認済みの変更要求を登録し、許可IP内PCの agent が Backlog API へ反映します。

初期対応操作:

- `create_issue`
- `update_issue`
- `add_comment`

対象外:

- 課題削除
- 添付ファイル
- プロジェクト移動
- 一括大量更新

列:

| 列 | 内容 |
|---|---|
| `request_id` | 一意ID |
| `operation` | `create_issue`, `update_issue`, `add_comment` |
| `issue_key` | 更新・コメント対象の課題キー |
| `summary` | 件名 |
| `description` | 説明 |
| `issue_type_id` | 新規作成時の種別ID |
| `priority_id` | 優先度ID |
| `status_id` | 状態ID |
| `assignee_id` | 担当者ID |
| `start_date` / `due_date` | 開始日・期限 |
| `comment` | 追加コメント |
| `requested_by` | 依頼者 |
| `requested_at` | 依頼日時 |
| `approval_status` | `approved` のみ処理 |
| `execution_status` | `queued` のみ処理 |
| `validation_error` | 検証・反映エラー |
| `applied_at` | 反映日時 |
| `backlog_response` | Backlog応答要約 |
| `retry_count` | 失敗回数 |

処理条件:

```text
approval_status = approved
execution_status = queued
```

手動実行:

```bash
python scripts/process_write_queue.py
```

dry-run:

```bash
WRITE_QUEUE_DRY_RUN=true python scripts/process_write_queue.py
```

環境変数:

```bash
export WRITE_QUEUE_SHEET_NAME="write_queue"
export WRITE_QUEUE_MAX_ROWS="20"
export WRITE_QUEUE_DRY_RUN="false"
```

成功時:

```json
{"status":"ok","sheet":"write_queue","processed_count":1,"dry_run":false}
```

Windows タスクスケジューラ例:

```powershell
schtasks /Create /SC MINUTE /MO 5 /TN "BacklogWriteQueueProcessor" /TR "C:\path\to\repo\.venv-sync\Scripts\python.exe C:\path\to\repo\scripts\process_write_queue.py"
```

## トラブルシュート

Backlog API が 403 の場合:

- 実行PCが Backlog 許可IP内にいるか確認
- API key が `https://ice.backlog.jp` のものか確認
- API key 発行ユーザーが `ICESAO_GENTASK` を参照できるか確認

Google Sheets API が 403 の場合:

- `GOOGLE_AUTH_MODE=user_oauth` の場合は、認証したGoogleユーザーが Spreadsheet を編集できるか確認
- `GOOGLE_AUTH_MODE=service_account` の場合は、Spreadsheet がサービスアカウントに共有されているか確認
- `GOOGLE_APPLICATION_CREDENTIALS` の JSON が正しいか確認
- Google Sheets API が有効か確認

Google Workspace の共有ポリシーでサービスアカウントを追加できない場合:

- `GOOGLE_AUTH_MODE=user_oauth` に切り替える
- `GOOGLE_OAUTH_CLIENT_SECRET_FILE` にデスクトップアプリ用 OAuth client secret JSON を指定する
- 初回実行時にブラウザで対象Spreadsheetへアクセスできるユーザーとして認証する
