# backlog-sync-bridge

BacklogとGoogle Sheetsを、許可IP内のWindows常駐PCから同期するためのローカル実行基盤です。

## 現在の構成

```text
C:\backlog-sync
├─ config/
│  └─ backlog-sync-env.ps1          # ローカル専用。Git管理外
├─ scripts/
│  ├─ __init__.py
│  ├─ google_sheets_auth.py
│  └─ process_write_queue_v2.py
├─ tools/
│  ├─ new-add-comment-row.ps1
│  ├─ new-change-status-row.ps1
│  └─ run-write-queue-processor-v2.ps1
├─ logs/                             # Git管理外
├─ output/                           # Git管理外
├─ assignee_mapping.tsv
└─ priority_mapping.tsv
```

## 実行概要

1. `config/backlog-sync-env.ps1` にローカル環境変数を設定する。
2. `tools/run-write-queue-processor-v2.ps1` を実行する。
3. Google Sheetsの `write_queue_v2` から承認済み・実行待ちの行を取得する。
4. 設定に応じてDryRun検証またはBacklog APIへの書き込みを行う。
5. 処理結果を `write_queue_v2` に書き戻す。

## セキュリティ

以下はGitHubへ登録しません。

- Backlog APIキー
- Google OAuthクライアントシークレット
- OAuthトークン
- `config/backlog-sync-env.ps1`
- `logs/`、`output/`、`.venv-sync/`

実設定は `config/backlog-sync-env.example.ps1` をコピーして作成します。

## 開発方針

- `main`: 常時実行可能な基準ブランチ
- `feature/*`: 機能開発ブランチ
- 変更はPull Requestでレビューしてから `main` へ反映

次の開発対象は、`IWTECH_SYSOP` の未完了課題・コメントを `ICESAO_GENTASK` へ同期する機能です。詳細は `docs/iwtech-sysop-sync.md` を参照してください。
