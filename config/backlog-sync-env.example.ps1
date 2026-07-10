# Copy this file to config/backlog-sync-env.ps1 and set local values.
# The copied file is excluded by .gitignore.

$env:BACKLOG_BASE_URL = "https://ice.backlog.jp"
$env:BACKLOG_API_KEY = ""

$env:GOOGLE_AUTH_MODE = "user_oauth"
$env:GOOGLE_SHEETS_SPREADSHEET_ID = ""
$env:GOOGLE_OAUTH_CLIENT_SECRET_FILE = "C:\backlog-sync\config\google-oauth-client-secret.json"
$env:GOOGLE_OAUTH_TOKEN_FILE = "C:\backlog-sync\config\google-oauth-token.json"

$env:WRITE_QUEUE_SHEET_NAME = "write_queue_v2"
$env:WRITE_QUEUE_MAX_ROWS = "20"
$env:WRITE_QUEUE_DRY_RUN = "true"
$env:WORKER_NAME = "backlog-sync-worker-v2"
$env:BACKLOG_TIMEOUT_SECONDS = "20"

$env:STATUS_MAPPING_SHEET_NAME = "status_mapping"
$env:PRIORITY_MAPPING_SHEET_NAME = "priority_mapping"
$env:ASSIGNEE_MAPPING_SHEET_NAME = "assignee_mapping"
