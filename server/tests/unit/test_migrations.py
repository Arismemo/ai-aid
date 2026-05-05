import sqlite3
from pathlib import Path

from migration_runner import apply_migrations


def test_creates_tables(tmp_path):
    db = tmp_path / "t.db"
    apply_migrations(str(db))
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "requests" in tables
    assert "answers" in tables
    assert "events" in tables
    assert "_migrations" in tables


def test_idempotent(tmp_path):
    db = tmp_path / "t.db"
    apply_migrations(str(db))
    apply_migrations(str(db))  # second run must not raise
    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT version FROM _migrations"))
    versions = sorted(r[0] for r in rows)
    assert versions == ["001_init", "002_quality_signals"]


def test_records_applied_version(tmp_path):
    db = tmp_path / "t.db"
    apply_migrations(str(db))
    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT version FROM _migrations ORDER BY version"))
    assert rows == [("001_init",), ("002_quality_signals",)]
