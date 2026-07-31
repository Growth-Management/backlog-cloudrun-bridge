# Copy this file to backlog-sync-env.ps1 on the resident Windows PC.
# Keep the copied file local and do not commit real secrets.

$env:BACKLOG_BASE_URL = "https://ice.backlog.jp"
$env:BACKLOG_API_KEY = "set-backlog-api-key-locally"

$env:GOOGLE_AUTH_MODE = "user_oauth"
$env:GOOGLE_SHEETS_SPREADSHEET_ID = "1muUdmTqJYQV9FOzoCR1lkM-ie9QWfYjQYf__6YF_Hlo"
$env:GOOGLE_OAUTH_CLIENT_SECRET_FILE = "C:\secure\google-oauth-client-secret.json"
$env:GOOGLE_OAUTH_TOKEN_FILE = "C:\secure\google-oauth-token.json"

$env:WRITE_QUEUE_SHEET_NAME = "write_queue_v2"
$env:WRITE_QUEUE_MAX_ROWS = "1"
$env:WRITE_QUEUE_DRY_RUN = "false"
$env:WORKER_NAME = "backlog-sync-worker-v2"

$env:STATUS_MAPPING_SHEET_NAME = "status_mapping"
$env:PRIORITY_MAPPING_SHEET_NAME = "priority_mapping"
$env:ASSIGNEE_MAPPING_SHEET_NAME = "assignee_mapping"

$env:BACKLOG_TIMEOUT_SECONDS = "20"
$env:BACKLOG_SYNC_LOG_DIR = "C:\Users\sinohara\backlog-cloudrun-bridge\logs"
