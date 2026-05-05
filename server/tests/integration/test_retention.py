"""Retention tests — auto-trim closed requests > N days."""

import time

import pytest
from fastapi.testclient import TestClient

from ai_aid.main import create_app


def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def _build_client(tmp_path, monkeypatch, retention_days="7"):
    monkeypatch.setenv("AI_AID_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("AI_AID_RATE_LIMIT_PER_MIN", "30")
    monkeypatch.setenv("AI_AID_MAX_BODY_KB", "100")
    monkeypatch.setenv("AI_AID_EVENT_BUFFER", "1000")
    monkeypatch.setenv("AI_AID_RETENTION_DAYS", retention_days)
    app = create_app()
    return TestClient(app)


def test_prune_leaves_open_requests(tmp_path, monkeypatch):
    """Open requests must never be pruned even if old."""
    c = _build_client(tmp_path, monkeypatch, retention_days="7")
    with c:
        store = c.app.state.store
        # Create open request, backdate it artificially via direct SQL.
        rid = store.create_request(_payload(client_id="alice"))
        # Backdate created_at to 100 days ago — but it's still open, so safe.
        with store._conn() as conn:
            old = int(time.time() * 1000) - 100 * 86_400_000
            conn.execute("UPDATE requests SET created_at = ? WHERE id = ?", (old, rid))
        # Trigger prune via posting another request (or call directly).
        deleted = store.prune_old_closed(days=7)
        assert deleted == 0
        assert store.get_request(rid) is not None


def test_prune_removes_closed_requests_older_than_threshold(tmp_path, monkeypatch):
    c = _build_client(tmp_path, monkeypatch, retention_days="7")
    with c:
        store = c.app.state.store
        rid = store.create_request(_payload(client_id="alice"))
        store.close_request(rid)
        # Backdate closed_at to 30 days ago.
        with store._conn() as conn:
            old = int(time.time() * 1000) - 30 * 86_400_000
            conn.execute("UPDATE requests SET closed_at = ? WHERE id = ?", (old, rid))
        deleted = store.prune_old_closed(days=7)
        assert deleted == 1
        assert store.get_request(rid) is None


def test_prune_leaves_recently_closed_within_threshold(tmp_path, monkeypatch):
    c = _build_client(tmp_path, monkeypatch, retention_days="7")
    with c:
        store = c.app.state.store
        rid = store.create_request(_payload(client_id="alice"))
        store.close_request(rid)
        # closed just now → within 7 day window.
        deleted = store.prune_old_closed(days=7)
        assert deleted == 0
        assert store.get_request(rid) is not None


def test_retention_days_zero_is_noop(tmp_path, monkeypatch):
    c = _build_client(tmp_path, monkeypatch, retention_days="0")
    with c:
        store = c.app.state.store
        rid = store.create_request(_payload(client_id="alice"))
        store.close_request(rid)
        # Backdate to ancient.
        with store._conn() as conn:
            old = int(time.time() * 1000) - 100 * 86_400_000
            conn.execute("UPDATE requests SET closed_at = ? WHERE id = ?", (old, rid))
        deleted = store.prune_old_closed(days=0)
        assert deleted == 0
        assert store.get_request(rid) is not None


def test_settings_retention_days_from_env(monkeypatch):
    from ai_aid.config import Settings
    monkeypatch.setenv("AI_AID_RETENTION_DAYS", "7")
    s = Settings.from_env()
    assert s.retention_days == 7


def test_settings_retention_days_default_zero(monkeypatch):
    from ai_aid.config import Settings
    monkeypatch.delenv("AI_AID_RETENTION_DAYS", raising=False)
    s = Settings.from_env()
    assert s.retention_days == 0


def test_settings_retention_days_invalid_raises(monkeypatch):
    from ai_aid.config import Settings
    monkeypatch.setenv("AI_AID_RETENTION_DAYS", "not-a-number")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_post_request_triggers_prune(tmp_path, monkeypatch):
    """Posting a request runs prune as a side-effect when retention_days > 0."""
    c = _build_client(tmp_path, monkeypatch, retention_days="7")
    with c:
        store = c.app.state.store
        rid = store.create_request(_payload(client_id="alice"))
        store.close_request(rid)
        with store._conn() as conn:
            old = int(time.time() * 1000) - 30 * 86_400_000
            conn.execute("UPDATE requests SET closed_at = ? WHERE id = ?", (old, rid))
        # Now post a fresh request — that should trigger prune.
        r = c.post("/api/requests", json=_payload(client_id="bob"))
        assert r.status_code == 201
        # The old closed alice request should be gone.
        assert store.get_request(rid) is None


def test_startup_runs_prune(tmp_path, monkeypatch):
    """Building the app re-runs prune at startup."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("AI_AID_DB_PATH", str(db_path))
    monkeypatch.setenv("AI_AID_RATE_LIMIT_PER_MIN", "30")
    monkeypatch.setenv("AI_AID_MAX_BODY_KB", "100")
    monkeypatch.setenv("AI_AID_EVENT_BUFFER", "1000")
    monkeypatch.setenv("AI_AID_RETENTION_DAYS", "7")

    # First boot: create an old closed request with retention=0 so it lingers.
    monkeypatch.setenv("AI_AID_RETENTION_DAYS", "0")
    app1 = create_app()
    with TestClient(app1) as c1:
        store = c1.app.state.store
        rid = store.create_request(_payload(client_id="alice"))
        store.close_request(rid)
        with store._conn() as conn:
            old = int(time.time() * 1000) - 30 * 86_400_000
            conn.execute("UPDATE requests SET closed_at = ? WHERE id = ?", (old, rid))

    # Second boot with retention_days=7 — startup prune should remove rid.
    monkeypatch.setenv("AI_AID_RETENTION_DAYS", "7")
    app2 = create_app()
    with TestClient(app2) as c2:
        store2 = c2.app.state.store
        assert store2.get_request(rid) is None
