# Backlog issues_snapshot 同期 agent

Backlog の許可IP内にある常時起動PCで実行する読み取り専用の同期 agent です。
Backlog API から課題一覧を取得し、Google Sheets の `issues_snapshot` シートへ反映します。

## 初期スコープ

- Backlog -> Google Sheets の読み取り同期のみ
- Backlog への書き込みは行わない
- `issues_snapshot` は原則 read-only として扱う
- `write_queue` による Backlog 反映は後続タスクで実装する

## 前提

- 実行PCが Backlog の許可IP内にある
- Backlog API key を発行済み
- Google Cloud のサービスアカウントを用意済み
- 対象 Google Spreadsheet にサービスアカウントの編集権限を付与済み

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

Google サービスアカウントキーを実行PC上に配置し、Spreadsheet をそのサービスアカウントに共有します。

## 環境変数

必須:

```bash
export BACKLOG_API_KEY="Backlog API key"
export GOOGLE_SHEETS_SPREADSHEET_ID="Google Spreadsheet ID"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

任意:

```bash
export BACKLOG_BASE_URL="https://ice.backlog.jp"
export BACKLOG_PROJECT_KEY="ICESAO_GENTASK"
export ISSUES_SNAPSHOT_SHEET_NAME="issues_snapshot"
export ISSUES_SYNC_PAGE_SIZE="100"
export ISSUES_SYNC_MAX_PAGES="10"
export BACKLOG_TIMEOUT_SECONDS="20"
```

## 手動実行

```bash
python scripts/sync_issues_snapshot.py
```

成功時は次のような JSON を標準出力に出します。

```json
{"status":"ok","sheet":"issues_snapshot","synced_count":120,"synced_at":"2026-06-10T00:00:00+00:00"}
```

## 同期頻度

初期推奨:

- 通常同期: 15分ごと
- master系同期: 後続タスクで 1日1回
- Backlog反映キュー: 後続タスクで 5分ごと

## Windows タスクスケジューラ例

15分ごとに実行する場合:

```powershell
schtasks /Create /SC MINUTE /MO 15 /TN "BacklogIssuesSnapshotSync" /TR "C:\path\to\repo\.venv-sync\Scripts\python.exe C:\path\to\repo\scripts\sync_issues_snapshot.py"
```

環境変数は、実行ユーザーのユーザー環境変数、または `.cmd` ラッパーで設定します。

## セキュリティ

- Backlog API key は許可IP内PCのみに配置する
- Google サービスアカウントは対象 Spreadsheet への最小権限にする
- サービスアカウントキーは一般ユーザーが読める場所に置かない
- PCを外部公開しない
- `issues_snapshot` は同期結果として扱い、人手編集しない
- Backlogへの書き込みは後続の `write_queue` 実装まで行わない

## トラブルシュート

Backlog API が 403 の場合:

- 実行PCが Backlog 許可IP内にいるか確認
- API key が `https://ice.backlog.jp` のものか確認
- API key 発行ユーザーが `ICESAO_GENTASK` を参照できるか確認

Google Sheets API が 403 の場合:

- Spreadsheet がサービスアカウントに共有されているか確認
- `GOOGLE_APPLICATION_CREDENTIALS` の JSON が正しいか確認
- Google Sheets API が有効か確認
