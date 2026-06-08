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

## Backlog Client

Backlog API access is isolated in `app/clients/backlog_client.py`. The client
adds the Backlog API key to outbound requests, normalizes issue responses, and
converts HTTP, timeout, or invalid response failures into `BacklogClientError`
without exposing secret values.
