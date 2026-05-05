import pytest
from ai_aid.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("AI_AID_DB_PATH", raising=False)
    monkeypatch.delenv("AI_AID_MAX_BODY_KB", raising=False)
    monkeypatch.delenv("AI_AID_RATE_LIMIT_PER_MIN", raising=False)
    monkeypatch.delenv("AI_AID_EVENT_BUFFER", raising=False)
    s = Settings.from_env()
    assert s.db_path == "/data/ai-aid.db"
    assert s.max_body_kb == 100
    assert s.rate_limit_per_min == 30
    assert s.event_buffer == 1000


def test_overrides_from_env(monkeypatch):
    monkeypatch.setenv("AI_AID_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("AI_AID_MAX_BODY_KB", "50")
    monkeypatch.setenv("AI_AID_RATE_LIMIT_PER_MIN", "5")
    monkeypatch.setenv("AI_AID_EVENT_BUFFER", "200")
    s = Settings.from_env()
    assert s.db_path == "/tmp/x.db"
    assert s.max_body_kb == 50
    assert s.rate_limit_per_min == 5
    assert s.event_buffer == 200


def test_invalid_int_raises(monkeypatch):
    monkeypatch.setenv("AI_AID_MAX_BODY_KB", "not-a-number")
    with pytest.raises(ValueError):
        Settings.from_env()
