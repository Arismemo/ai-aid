"""Re-running apply_migrations on an existing DB must preserve all data and
not break schema. Adding a hypothetical second migration must not corrupt v1."""
import json
import sqlite3
from pathlib import Path

import pytest

import sys
SERVER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER))

from migration_runner import apply_migrations, MIGRATIONS_DIR
from ai_aid import db as db_mod


def _seed(store: db_mod.Store) -> tuple[str, str]:
    rid = store.create_request({
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    aid = store.create_answer(rid, {
        "solver_client_id": "bob", "solver_model": "m",
        "summary": "s", "solution": "sol", "reasoning": "r", "caveats": "c",
    })
    store.append_event("request.created", {"id": rid})
    store.append_event("answer.created", {"id": aid, "request_id": rid})
    return rid, aid


def test_rerun_migrations_preserves_data(tmp_path):
    db_path = str(tmp_path / "x.db")
    apply_migrations(db_path)
    store = db_mod.Store(db_path)
    rid, aid = _seed(store)

    apply_migrations(db_path)
    apply_migrations(db_path)

    after = store.get_request(rid)
    assert after is not None
    assert after["goal"] == "g"
    assert store.list_answers(rid)[0]["id"] == aid
    assert store.count_events() == 2


def test_migration_runner_handles_new_migration(tmp_path):
    """Drop a fake 002_*.sql in, re-run; first migration's data preserved."""
    db_path = str(tmp_path / "x.db")
    apply_migrations(db_path)
    store = db_mod.Store(db_path)
    rid, _ = _seed(store)

    # Drop a fake migration alongside the real ones
    fake = MIGRATIONS_DIR / "002_test_idempotency.sql"
    fake.write_text("CREATE TABLE _harmless (x TEXT);\n", encoding="utf-8")
    try:
        apply_migrations(db_path)
        # Verify both migrations applied
        conn = sqlite3.connect(db_path)
        versions = sorted(r[0] for r in conn.execute("SELECT version FROM _migrations"))
        assert versions == ["001_init", "002_test_idempotency"]
        # Data preserved
        assert store.get_request(rid) is not None
        # New table exists
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "_harmless" in tables
    finally:
        fake.unlink(missing_ok=True)


def test_fk_cascade_on_request_delete(tmp_path):
    db_path = str(tmp_path / "x.db")
    apply_migrations(db_path)
    store = db_mod.Store(db_path)
    rid, aid = _seed(store)
    assert store.delete_request(rid)
    assert store.list_answers(rid) == []  # cascade

    conn = sqlite3.connect(db_path)
    n_orphans = conn.execute(
        "SELECT COUNT(*) FROM answers WHERE request_id = ?", (rid,)
    ).fetchone()[0]
    assert n_orphans == 0
