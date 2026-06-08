import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import LOGGER_NAME
from app.main import app


def test_request_logging_includes_request_metadata(caplog) -> None:
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = client.get("/health", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test"

    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == LOGGER_NAME
    ]
    assert events
    assert events[-1]["event"] == "http_request"
    assert events[-1]["request_id"] == "req-test"
    assert events[-1]["method"] == "GET"
    assert events[-1]["path"] == "/health"
    assert events[-1]["status_code"] == 200
    assert "duration_ms" in events[-1]
