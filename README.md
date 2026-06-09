# Backlog Cloud Run Bridge

Cloud Run 上で動作する Backlog 連携 API です。

## Local Run

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## Health Check

```bash
curl http://localhost:8080/health
```

## Auth Check

Business API routes use Bearer authentication. `/health` remains public for
Cloud Run availability checks.

```bash
export API_AUTH_TOKEN="change-me"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
curl -H "Authorization: Bearer change-me" http://localhost:8080/auth/check
```

## Configuration

The service reads configuration from environment variables. Secret values must
be provided through Cloud Run environment variables or Secret Manager.

| Name | Default | Required |
| --- | --- | --- |
| `APP_ENV` | `local` | no |
| `API_AUTH_TOKEN` | none | yes |
| `BACKLOG_BASE_URL` | `https://ice.backlog.jp` | no |
| `BACKLOG_API_KEY` | none | yes |
| `BACKLOG_PROJECT_KEY` | `ICESAO_GENTASK` | no |
| `BACKLOG_TIMEOUT_SECONDS` | `10` | no |

Request logs are emitted as JSON and include `request_id`, HTTP method, path,
status code, and duration. Secret values are not included in log output.

## Operations

Cloud Run deploys are managed by GitHub Actions. See
[`docs/operations.md`](docs/operations.md) for CI, deploy, health check,
Secret Manager, Artifact Registry, and rollback verification steps.

## Backlog Client

Backlog API access is isolated in `app/clients/backlog_client.py`. The client
adds the Backlog API key to outbound requests, normalizes issue responses, and
converts HTTP, timeout, or invalid response failures into `BacklogClientError`
without exposing secret values.

## Create Issue

`POST /issues` creates a Backlog issue. This route requires Bearer
authentication.

```bash
curl -X POST http://localhost:8080/issues \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Example issue",
    "description": "Issue body",
    "issue_type_id": 5,
    "priority": "normal",
    "assignee_id": 10
  }'
```

Backlog requires numeric IDs for issue type, priority, and assignee values.
The API accepts `priority` as `high`, `normal`, or `low` and converts it to a
Backlog `priorityId`. Use `issue_type_id` directly, or provide
`issue_type_name` so the API can resolve it from the configured Backlog project.
Assignees must be sent as `assignee_id`; display names are not forwarded to
Backlog.

## Search and Get Issues

`GET /issues` searches Backlog issues in the configured project. This route
requires Bearer authentication.

```bash
curl -H "Authorization: Bearer change-me" \
  "http://localhost:8080/issues?keyword=Example&status_id=1&assignee_id=10"
```

Use repeated query parameters to send multiple status or assignee IDs:
`status_id=1&status_id=2`. The response contains a normalized issue list,
`count`, and `offset`.

`GET /issues/{issue_key}` returns details for a confirmed Backlog issue key:

```bash
curl -H "Authorization: Bearer change-me" \
  http://localhost:8080/issues/ICESAO_GENTASK-1
```

## Update Issue

`PATCH /issues/{issue_key}` updates a confirmed Backlog issue key. This route
requires Bearer authentication.

```bash
curl -X PATCH http://localhost:8080/issues/ICESAO_GENTASK-1 \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "summary": "Updated summary",
    "status": "in_progress",
    "priority": "normal",
    "assignee_id": 10
  }'
```

The API accepts direct `status_id` and `priority_id` values for environments
with custom Backlog IDs. It also supports default name mappings:
`open` -> `1`, `in_progress` -> `2`, `resolved` -> `3`, `closed` -> `4` and
`high` -> `2`, `normal` -> `3`, `low` -> `4`. Assignees must be sent as
`assignee_id`; display names are not forwarded to Backlog.
