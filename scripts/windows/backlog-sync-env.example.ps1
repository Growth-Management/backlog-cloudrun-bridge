# Copy this file to backlog-sync-env.ps1 on the allowed-IP Windows PC.
# Keep the copied file local and do not commit real secrets.

$env:BACKLOG_BASE_URL = "https://ice.backlog.jp"
$env:BACKLOG_PROJECT_KEY = "ICESAO_GENTASK"
$env:BACKLOG_API_KEY = "set-backlog-api-key-locally"

$env:GOOGLE_AUTH_MODE = "user_oauth"
$env:GOOGLE_SHEETS_SPREADSHEET_ID = "1muUdmTqJYQV9FOzoCR1lkM-ie9QWfYjQYf__6YF_Hlo"
$env:GOOGLE_OAUTH_CLIENT_SECRET_FILE = "C:\secure\google-oauth-client-secret.json"
$env:GOOGLE_OAUTH_TOKEN_FILE = "C:\secure\google-oauth-token.json"

$env:ISSUES_SNAPSHOT_SHEET_NAME = "issues_snapshot"
$env:ISSUES_SYNC_PAGE_SIZE = "100"
$env:ISSUES_SYNC_MAX_PAGES = "10"

$env:WRITE_QUEUE_SHEET_NAME = "write_queue"
$env:WRITE_QUEUE_MAX_ROWS = "20"
$env:WRITE_QUEUE_DRY_RUN = "false"

$env:BACKLOG_TIMEOUT_SECONDS = "20"
$env:BACKLOG_SYNC_LOG_DIR = "C:\Users\sinohara\backlog-cloudrun-bridge\logs"
