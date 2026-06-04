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
