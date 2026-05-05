import pytest
from fastapi.testclient import TestClient
from ai_aid.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("AI_AID_DB_PATH", str(db_path))
    monkeypatch.setenv("AI_AID_RATE_LIMIT_PER_MIN", "30")
    monkeypatch.setenv("AI_AID_MAX_BODY_KB", "100")
    monkeypatch.setenv("AI_AID_EVENT_BUFFER", "1000")
    app = create_app()
    with TestClient(app) as c:
        yield c
