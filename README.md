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
