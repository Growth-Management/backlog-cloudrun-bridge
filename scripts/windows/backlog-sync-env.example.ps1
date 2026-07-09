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

# Legacy write_queue. Keep this for the current v1 flow.
$env:WRITE_QUEUE_SHEET_NAME = "write_queue"
$env:WRITE_QUEUE_MAX_ROWS = "20"
$env:WRITE_QUEUE_DRY_RUN = "false"

# write_queue_v2. The v2 runners set WRITE_QUEUE_SHEET_NAME=write_queue_v2
# at runtime, so the legacy runner can continue using write_queue.
$env:WORKER_NAME = "backlog-sync-worker-v2"
$env:TARGET_PROJECT_ID = "set-target-project-id-locally"
$env:BACKLOG_DEFAULT_ISSUE_TYPE_ID = "set-default-issue-type-id-locally"
$env:BACKLOG_DEFAULT_PRIORITY_ID = "3"
$env:BACKLOG_DEFAULT_ASSIGNEE_ID = "115000"

# IWTECH_SYSOP -> ICESAO_GENTASK pre-queue job.
$env:SOURCE_PROJECT_KEY = "IWTECH_SYSOP"
$env:TARGET_PROJECT_KEY = "ICESAO_GENTASK"
$env:SYNC_CONFIG_SHEET_NAME = "sync_config"
$env:SYNC_ISSUE_MAP_SHEET_NAME = "sync_issue_map"
$env:SYNC_MAX_ISSUES = "20"
$env:SYNC_REQUESTED_BY = "iwtech-sysop-sync"
# Optional: set comma-separated issue keys to limit a test run.
# $env:SOURCE_ISSUE_KEYS = "IWTECH_SYSOP-1"

$env:BACKLOG_TIMEOUT_SECONDS = "20"
$env:BACKLOG_SYNC_LOG_DIR = "C:\Users\sinohara\backlog-sync-bridge\logs"
