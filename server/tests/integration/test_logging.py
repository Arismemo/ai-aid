"""Logging tests — at least one /health hit produces a JSON log line."""

import json
import logging

from fastapi.testclient import TestClient

from ai_aid.main import create_app


def test_health_emits_json_log_line(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("AI_AID_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("AI_AID_RATE_LIMIT_PER_MIN", "30")
    monkeypatch.setenv("AI_AID_MAX_BODY_KB", "100")
    monkeypatch.setenv("AI_AID_EVENT_BUFFER", "1000")
    app = create_app()
    with caplog.at_level(logging.INFO, logger="ai_aid.access"):
        with TestClient(app) as c:
            r = c.get("/health")
            assert r.status_code == 200
    # The middleware should have logged at least one record.
    records = [r for r in caplog.records if r.name == "ai_aid.access"]
    assert len(records) >= 1
    # The message should be a JSON object with the expected keys.
    payload = json.loads(records[-1].message)
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["status"] == 200
    assert "duration_ms" in payload
    assert "ts" in payload


def test_logging_setup_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_AID_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("AI_AID_RATE_LIMIT_PER_MIN", "30")
    monkeypatch.setenv("AI_AID_MAX_BODY_KB", "100")
    monkeypatch.setenv("AI_AID_EVENT_BUFFER", "1000")
    # Calling create_app twice should not error or duplicate handlers.
    create_app()
    create_app()
