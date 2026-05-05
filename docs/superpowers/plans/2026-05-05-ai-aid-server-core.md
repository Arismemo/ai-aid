# ai-aid Server Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI + SQLite HTTP server for ai-aid: structured help requests, multi-answer responses, self-solve prevention, rate limiting. AIs can fully use the system via curl after this plan.

**Architecture:** Single FastAPI app, SQLite single-file storage with hand-written SQL migrations, Pydantic v2 for request/response validation, layered modules (routes → validators → db). No SSE, no web dashboard, no client skills in this plan — those land in plans 2 and 3.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic v2, sqlite3 (stdlib), pytest, httpx (TestClient).

---

## File Structure

Files this plan creates:

```
server/
  pyproject.toml                 # Project metadata + dependencies
  ai_aid/
    __init__.py                  # Package marker
    main.py                      # FastAPI app factory + endpoint registration
    config.py                    # Env-var settings (Settings dataclass)
    db.py                        # SQLite connection + low-level CRUD
    models.py                    # Pydantic models (request/response shapes)
    validators.py                # Custom validation (self-solve, body size)
    rate_limit.py                # Per-client_id sliding window rate limiter
    errors.py                    # Error response builder + custom exceptions
    routes/
      __init__.py                # Router registration
      requests.py                # POST/GET/DELETE /api/requests
      answers.py                 # POST /api/requests/{id}/answers
      lifecycle.py               # POST /api/requests/{id}/close
      health.py                  # GET /health
  migrations/
    001_init.sql                 # Initial schema (requests, answers, _migrations)
  migration_runner.py            # Applies pending migrations on startup
  tests/
    conftest.py                  # Shared fixtures (temp db, client)
    unit/
      __init__.py
      test_config.py
      test_db.py
      test_validators.py
      test_rate_limit.py
      test_models.py
    integration/
      __init__.py
      test_health.py
      test_post_requests.py
      test_get_requests.py
      test_get_request_detail.py
      test_post_answers.py
      test_close_request.py
      test_delete_request.py
      test_error_shape.py
```

**Boundaries:**
- `db.py` knows SQL only — no HTTP concepts.
- `routes/*.py` knows HTTP only — delegates persistence to `db.py`, validation to `validators.py`/Pydantic.
- `validators.py` is pure functions on already-parsed Pydantic models.
- `errors.py` provides one consistent JSON shape for every non-2xx response.

---

### Task 0: Pre-flight (git init + commit existing docs)

**Files:**
- Create: `/Users/liukun/j/ai-aid/.gitignore`

- [ ] **Step 1: Init git repo if missing**

```bash
cd /Users/liukun/j/ai-aid
if [ ! -d .git ]; then
  git init
  git config user.email "$(git config --global user.email || echo 'liukun@local')"
  git config user.name  "$(git config --global user.name  || echo 'liukun')"
fi
```

- [ ] **Step 2: Write `.gitignore`**

`.gitignore`:
```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.venv/
venv/
*.egg-info/
build/
dist/
data/
*.db
*.db-journal
*.db-wal
*.db-shm
.coverage
htmlcov/
.DS_Store
```

- [ ] **Step 3: Commit existing docs + gitignore**

```bash
cd /Users/liukun/j/ai-aid
git add .gitignore docs/
git commit -m "chore: initial commit with design + plan documents"
```

Expected: commit succeeds. `git log --oneline` shows one commit.

---

### Task 1: Project scaffolding

**Files:**
- Create: `server/pyproject.toml`
- Create: `server/ai_aid/__init__.py` (empty)
- Create: `server/ai_aid/main.py` (minimal FastAPI app)
- Create: `server/tests/__init__.py` (empty)
- Create: `server/tests/conftest.py`

- [ ] **Step 1: Write the failing test**

`server/tests/conftest.py`:
```python
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
```

`server/tests/integration/__init__.py`: empty file

`server/tests/integration/test_health.py`:
```python
def test_app_boots(client):
    # Smoke: app boots and returns 404 for unknown route (proving FastAPI is wired)
    response = client.get("/this-does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/integration/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_aid'` (or similar import error)

- [ ] **Step 3: Write minimal implementation**

`server/pyproject.toml`:
```toml
[project]
name = "ai-aid"
version = "0.1.0"
description = "AI help-network server"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
]

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["ai_aid*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`server/ai_aid/__init__.py`: empty

`server/ai_aid/main.py`:
```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="ai-aid", version="0.1.0")
    return app
```

`server/tests/__init__.py`: empty

- [ ] **Step 4: Install + verify test passes**

Run:
```bash
cd server
pip install -e ".[test]"
pytest tests/integration/test_health.py -v
```
Expected: PASS — 1 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add pyproject.toml ai_aid/ tests/
git commit -m "feat(server): scaffold FastAPI app with test harness"
```

---

### Task 2: Config module

**Files:**
- Create: `server/ai_aid/config.py`
- Create: `server/tests/unit/__init__.py` (empty)
- Create: `server/tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

`server/tests/unit/__init__.py`: empty

`server/tests/unit/test_config.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/unit/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_aid.config'`

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/config.py`:
```python
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    max_body_kb: int
    rate_limit_per_min: int
    event_buffer: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=os.environ.get("AI_AID_DB_PATH", "/data/ai-aid.db"),
            max_body_kb=int(os.environ.get("AI_AID_MAX_BODY_KB", "100")),
            rate_limit_per_min=int(os.environ.get("AI_AID_RATE_LIMIT_PER_MIN", "30")),
            event_buffer=int(os.environ.get("AI_AID_EVENT_BUFFER", "1000")),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/unit/test_config.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/config.py tests/unit/test_config.py tests/unit/__init__.py
git commit -m "feat(server): add Settings.from_env config loader"
```

---

### Task 3: Migration runner + initial schema

**Files:**
- Create: `server/migrations/001_init.sql`
- Create: `server/migration_runner.py`
- Create: `server/tests/unit/test_migrations.py`

- [ ] **Step 1: Write the failing test**

`server/tests/unit/test_migrations.py`:
```python
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
    assert versions == ["001_init"]


def test_records_applied_version(tmp_path):
    db = tmp_path / "t.db"
    apply_migrations(str(db))
    conn = sqlite3.connect(db)
    rows = list(conn.execute("SELECT version FROM _migrations ORDER BY version"))
    assert rows == [("001_init",)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/unit/test_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migration_runner'`

- [ ] **Step 3: Write minimal implementation**

`server/migrations/001_init.sql`:
```sql
CREATE TABLE requests (
    id           TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL,
    model        TEXT NOT NULL,
    goal         TEXT NOT NULL,
    context      TEXT NOT NULL,
    tried        TEXT NOT NULL,
    error        TEXT,
    constraints  TEXT,
    question     TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    created_at   INTEGER NOT NULL,
    closed_at    INTEGER
);

CREATE INDEX idx_requests_status ON requests(status);
CREATE INDEX idx_requests_client ON requests(client_id);
CREATE INDEX idx_requests_created ON requests(created_at DESC);

CREATE TABLE answers (
    id                TEXT PRIMARY KEY,
    request_id        TEXT NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    solver_client_id  TEXT NOT NULL,
    solver_model      TEXT NOT NULL,
    summary           TEXT NOT NULL,
    solution          TEXT,
    reasoning         TEXT,
    caveats           TEXT,
    created_at        INTEGER NOT NULL
);

CREATE INDEX idx_answers_request ON answers(request_id);

CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE INDEX idx_events_id ON events(id DESC);
```

`server/migration_runner.py`:
```python
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def apply_migrations(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations ("
        "version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM _migrations")}

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for path in files:
        version = path.stem
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO _migrations (version, applied_at) VALUES (?, strftime('%s','now')*1000)",
            (version,),
        )
        conn.commit()
    conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/unit/test_migrations.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add migrations/ migration_runner.py tests/unit/test_migrations.py
git commit -m "feat(server): add SQL migration runner with initial schema"
```

---

### Task 4: DB layer (CRUD primitives)

**Files:**
- Create: `server/ai_aid/db.py`
- Create: `server/tests/unit/test_db.py`

- [ ] **Step 1: Write the failing test**

`server/tests/unit/test_db.py`:
```python
import pytest

from ai_aid import db
from migration_runner import apply_migrations


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "t.db"
    apply_migrations(str(path))
    return db.Store(str(path))


def _sample_request(client_id="alice", model="haiku-4.5"):
    return {
        "client_id": client_id,
        "model": model,
        "goal": "g",
        "context": "c",
        "tried": "t",
        "error": None,
        "constraints": None,
        "question": "q",
    }


def test_create_request_returns_id_and_persists(store):
    rid = store.create_request(_sample_request())
    assert isinstance(rid, str) and len(rid) == 36
    row = store.get_request(rid)
    assert row["id"] == rid
    assert row["status"] == "open"
    assert row["created_at"] > 0
    assert row["closed_at"] is None


def test_get_request_returns_none_when_missing(store):
    assert store.get_request("nope") is None


def test_list_requests_filters_status_and_excludes_client(store):
    a = store.create_request(_sample_request("alice"))
    b = store.create_request(_sample_request("bob"))
    store.close_request(a)
    open_only = store.list_requests(status="open", exclude_client=None, only_client=None)
    assert {r["id"] for r in open_only} == {b}
    not_alice = store.list_requests(status="all", exclude_client="alice", only_client=None)
    assert {r["id"] for r in not_alice} == {b}
    only_alice = store.list_requests(status="all", exclude_client=None, only_client="alice")
    assert {r["id"] for r in only_alice} == {a}


def test_close_request_idempotency_signal(store):
    rid = store.create_request(_sample_request())
    assert store.close_request(rid) is True
    assert store.close_request(rid) is False  # already closed


def test_create_answer_and_list(store):
    rid = store.create_request(_sample_request("alice"))
    aid = store.create_answer(rid, {
        "solver_client_id": "bob",
        "solver_model": "opus-4.7",
        "summary": "s",
        "solution": None,
        "reasoning": None,
        "caveats": None,
    })
    answers = store.list_answers(rid)
    assert len(answers) == 1
    assert answers[0]["id"] == aid
    assert answers[0]["solver_client_id"] == "bob"


def test_delete_request_cascades_answers(store):
    rid = store.create_request(_sample_request("alice"))
    store.create_answer(rid, {
        "solver_client_id": "bob", "solver_model": "m",
        "summary": "s", "solution": None, "reasoning": None, "caveats": None,
    })
    assert store.delete_request(rid) is True
    assert store.get_request(rid) is None
    assert store.list_answers(rid) == []


def test_count_recent_requests_for_client(store):
    for _ in range(5):
        store.create_request(_sample_request("alice"))
    assert store.count_recent_requests("alice", window_ms=60_000) == 5
    assert store.count_recent_requests("bob", window_ms=60_000) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/unit/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_aid.db'` or similar

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/db.py`:
```python
import sqlite3
import time
import uuid
from typing import Any, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


class Store:
    def __init__(self, path: str):
        self.path = path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_request(self, payload: dict) -> str:
        rid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO requests "
                "(id, client_id, model, goal, context, tried, error, constraints, question, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
                (
                    rid, payload["client_id"], payload["model"],
                    payload["goal"], payload["context"], payload["tried"],
                    payload.get("error"), payload.get("constraints"),
                    payload["question"], _now_ms(),
                ),
            )
        return rid

    def get_request(self, rid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM requests WHERE id = ?", (rid,)).fetchone()
            return dict(row) if row else None

    def list_requests(
        self,
        *,
        status: str,
        exclude_client: Optional[str],
        only_client: Optional[str],
    ) -> list[dict]:
        sql = "SELECT * FROM requests WHERE 1=1"
        params: list[Any] = []
        if status != "all":
            sql += " AND status = ?"
            params.append(status)
        if exclude_client:
            sql += " AND client_id != ?"
            params.append(exclude_client)
        if only_client:
            sql += " AND client_id = ?"
            params.append(only_client)
        sql += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close_request(self, rid: str) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE requests SET status='closed', closed_at=? WHERE id=? AND status='open'",
                (_now_ms(), rid),
            )
            return cur.rowcount == 1

    def delete_request(self, rid: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM requests WHERE id = ?", (rid,))
            return cur.rowcount == 1

    def create_answer(self, rid: str, payload: dict) -> str:
        aid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO answers "
                "(id, request_id, solver_client_id, solver_model, summary, solution, reasoning, caveats, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    aid, rid, payload["solver_client_id"], payload["solver_model"],
                    payload["summary"], payload.get("solution"),
                    payload.get("reasoning"), payload.get("caveats"), _now_ms(),
                ),
            )
        return aid

    def list_answers(self, rid: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM answers WHERE request_id = ? ORDER BY created_at ASC",
                (rid,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_recent_requests(self, client_id: str, window_ms: int) -> int:
        cutoff = _now_ms() - window_ms
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) FROM requests WHERE client_id = ? AND created_at >= ?",
                (client_id, cutoff),
            ).fetchone()
            return int(row[0])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/unit/test_db.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/db.py tests/unit/test_db.py
git commit -m "feat(server): add SQLite Store with CRUD + cascade + filters"
```

---

### Task 5: Pydantic models

**Files:**
- Create: `server/ai_aid/models.py`
- Create: `server/tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

`server/tests/unit/test_models.py`:
```python
import pytest
from pydantic import ValidationError

from ai_aid.models import (
    AskRequest, AnswerRequest, RequestSummary, RequestDetail, AnswerOut,
)


def _ask_payload(**overrides):
    base = {
        "client_id": "alice",
        "model": "haiku-4.5",
        "goal": "g",
        "context": "c",
        "tried": "t",
        "error": None,
        "constraints": None,
        "question": "q",
    }
    base.update(overrides)
    return base


def test_ask_accepts_valid():
    m = AskRequest(**_ask_payload())
    assert m.client_id == "alice"
    assert m.error is None


def test_ask_rejects_empty_string_required():
    with pytest.raises(ValidationError):
        AskRequest(**_ask_payload(goal=""))


def test_ask_rejects_whitespace_only_required():
    with pytest.raises(ValidationError):
        AskRequest(**_ask_payload(question="   "))


def test_ask_optional_fields_can_be_empty_string_treated_as_none():
    m = AskRequest(**_ask_payload(error="", constraints="  "))
    assert m.error is None
    assert m.constraints is None


def test_ask_rejects_missing_required_field():
    payload = _ask_payload()
    del payload["client_id"]
    with pytest.raises(ValidationError):
        AskRequest(**payload)


def test_answer_requires_summary():
    with pytest.raises(ValidationError):
        AnswerRequest(
            solver_client_id="bob",
            solver_model="m",
            summary="",
            solution=None,
            reasoning=None,
            caveats=None,
        )


def test_answer_optional_fields_default_none():
    a = AnswerRequest(
        solver_client_id="bob", solver_model="m", summary="ok"
    )
    assert a.solution is None
    assert a.reasoning is None
    assert a.caveats is None


def test_request_summary_serializes_with_answer_count():
    s = RequestSummary(
        id="x", client_id="alice", model="haiku-4.5", goal="g",
        status="open", created_at=1, closed_at=None, answer_count=2,
    )
    assert s.model_dump()["answer_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/unit/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'AskRequest' from 'ai_aid.models'`

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/models.py`:
```python
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


def _required_nonblank(v: str) -> str:
    if v is None or not str(v).strip():
        raise ValueError("must be a non-empty string")
    return v


def _optional_blank_to_none(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if not str(v).strip():
        return None
    return v


class AskRequest(BaseModel):
    client_id: str
    model: str
    goal: str
    context: str
    tried: str
    error: Optional[str] = None
    constraints: Optional[str] = None
    question: str

    @field_validator("client_id", "model", "goal", "context", "tried", "question")
    @classmethod
    def _nonblank(cls, v: str) -> str:
        return _required_nonblank(v)

    @field_validator("error", "constraints")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        return _optional_blank_to_none(v)


class AnswerRequest(BaseModel):
    solver_client_id: str
    solver_model: str
    summary: str
    solution: Optional[str] = None
    reasoning: Optional[str] = None
    caveats: Optional[str] = None

    @field_validator("solver_client_id", "solver_model", "summary")
    @classmethod
    def _nonblank(cls, v: str) -> str:
        return _required_nonblank(v)

    @field_validator("solution", "reasoning", "caveats")
    @classmethod
    def _blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        return _optional_blank_to_none(v)


class RequestSummary(BaseModel):
    id: str
    client_id: str
    model: str
    goal: str
    status: Literal["open", "closed"]
    created_at: int
    closed_at: Optional[int]
    answer_count: int


class AnswerOut(BaseModel):
    id: str
    solver_client_id: str
    solver_model: str
    summary: str
    solution: Optional[str]
    reasoning: Optional[str]
    caveats: Optional[str]
    created_at: int


class RequestDetail(BaseModel):
    id: str
    client_id: str
    model: str
    goal: str
    context: str
    tried: str
    error: Optional[str]
    constraints: Optional[str]
    question: str
    status: Literal["open", "closed"]
    created_at: int
    closed_at: Optional[int]
    answers: list[AnswerOut]


class CreateResponse(BaseModel):
    id: str
    status: Literal["open", "closed"]
    created_at: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/unit/test_models.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/models.py tests/unit/test_models.py
git commit -m "feat(server): add Pydantic models with non-blank validation"
```

---

### Task 6: Error helpers

**Files:**
- Create: `server/ai_aid/errors.py`
- Create: `server/tests/unit/test_errors.py`

- [ ] **Step 1: Write the failing test**

`server/tests/unit/test_errors.py`:
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_aid.errors import (
    AidError, conflict, forbidden, not_found, payload_too_large,
    rate_limited, register_handlers,
)


def _make_app():
    app = FastAPI()
    register_handlers(app)

    @app.get("/raise/{kind}")
    def raise_handler(kind: str):
        if kind == "404":
            raise not_found("missing thing")
        if kind == "403":
            raise forbidden("cannot solve own request", request_id="r1")
        if kind == "409":
            raise conflict("request not open", status="closed")
        if kind == "413":
            raise payload_too_large(150)
        if kind == "429":
            raise rate_limited(client_id="alice", limit=30)
        return {"ok": True}

    return app


def test_not_found_returns_404_with_shape():
    client = TestClient(_make_app())
    r = client.get("/raise/404")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not_found"
    assert "missing thing" in body["message"]


def test_forbidden_includes_extra_fields():
    client = TestClient(_make_app())
    r = client.get("/raise/403")
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "forbidden"
    assert body["request_id"] == "r1"


def test_conflict_includes_status():
    client = TestClient(_make_app())
    r = client.get("/raise/409")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "conflict"
    assert body["status"] == "closed"


def test_payload_too_large():
    client = TestClient(_make_app())
    r = client.get("/raise/413")
    assert r.status_code == 413
    body = r.json()
    assert body["error"] == "payload_too_large"


def test_rate_limited_includes_limit_and_client():
    client = TestClient(_make_app())
    r = client.get("/raise/429")
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "rate_limited"
    assert body["client_id"] == "alice"
    assert body["limit"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/unit/test_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_aid.errors'`

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/errors.py`:
```python
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AidError(Exception):
    def __init__(self, status_code: int, error: str, message: str, **extra: Any):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
        self.extra = extra


def not_found(message: str, **extra) -> AidError:
    return AidError(404, "not_found", message, **extra)


def forbidden(message: str, **extra) -> AidError:
    return AidError(403, "forbidden", message, **extra)


def conflict(message: str, **extra) -> AidError:
    return AidError(409, "conflict", message, **extra)


def payload_too_large(actual_kb: int, **extra) -> AidError:
    return AidError(413, "payload_too_large", f"body {actual_kb}KB exceeds limit", **extra)


def rate_limited(client_id: str, limit: int, **extra) -> AidError:
    return AidError(
        429, "rate_limited",
        f"client {client_id} exceeded {limit}/min",
        client_id=client_id, limit=limit, **extra,
    )


def bad_request(message: str, **extra) -> AidError:
    return AidError(400, "bad_request", message, **extra)


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AidError)
    async def _aid_handler(request: Request, exc: AidError):
        body = {"error": exc.error, "message": exc.message, **exc.extra}
        return JSONResponse(status_code=exc.status_code, content=body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/unit/test_errors.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/errors.py tests/unit/test_errors.py
git commit -m "feat(server): add unified AidError exception + JSON handler"
```

---

### Task 7: Rate limiter

**Files:**
- Create: `server/ai_aid/rate_limit.py`
- Create: `server/tests/unit/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

`server/tests/unit/test_rate_limit.py`:
```python
import time
import pytest
from ai_aid.rate_limit import SlidingWindow


def test_first_n_pass(monkeypatch):
    rl = SlidingWindow(limit=3, window_ms=60_000)
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: 1000)
    assert rl.allow("alice") is True
    assert rl.allow("alice") is True
    assert rl.allow("alice") is True


def test_n_plus_one_blocked(monkeypatch):
    rl = SlidingWindow(limit=3, window_ms=60_000)
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: 1000)
    for _ in range(3):
        rl.allow("alice")
    assert rl.allow("alice") is False


def test_clients_independent(monkeypatch):
    rl = SlidingWindow(limit=2, window_ms=60_000)
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: 1000)
    rl.allow("alice")
    rl.allow("alice")
    assert rl.allow("alice") is False
    assert rl.allow("bob") is True


def test_window_expiry_releases_slots(monkeypatch):
    rl = SlidingWindow(limit=2, window_ms=1000)
    fake = {"t": 1000}
    monkeypatch.setattr("ai_aid.rate_limit._now_ms", lambda: fake["t"])
    rl.allow("alice")
    rl.allow("alice")
    assert rl.allow("alice") is False
    fake["t"] = 3000  # advance beyond window
    assert rl.allow("alice") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/unit/test_rate_limit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai_aid.rate_limit'`

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/rate_limit.py`:
```python
import time
from collections import defaultdict, deque
from threading import Lock


def _now_ms() -> int:
    return int(time.time() * 1000)


class SlidingWindow:
    def __init__(self, limit: int, window_ms: int):
        self.limit = limit
        self.window_ms = window_ms
        self._buckets: dict[str, deque[int]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = _now_ms()
        cutoff = now - self.window_ms
        with self._lock:
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/unit/test_rate_limit.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/rate_limit.py tests/unit/test_rate_limit.py
git commit -m "feat(server): add per-client sliding window rate limiter"
```

---

### Task 8: App factory wires everything + body size middleware + health endpoint

**Files:**
- Modify: `server/ai_aid/main.py`
- Create: `server/ai_aid/routes/__init__.py` (empty)
- Create: `server/ai_aid/routes/health.py`
- Modify: `server/tests/integration/test_health.py`

- [ ] **Step 1: Write the failing test**

Replace `server/tests/integration/test_health.py`:
```python
def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["db"] == "ok"
    assert body["events_buffered"] == 0


def test_oversized_body_rejected(client):
    huge = "x" * (101 * 1024)  # 101KB > 100KB cap
    r = client.post("/api/requests", json={"x": huge})
    assert r.status_code == 413
    body = r.json()
    assert body["error"] == "payload_too_large"


def test_app_boots(client):
    r = client.get("/this-does-not-exist")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/integration/test_health.py -v`
Expected: FAIL — `/health` returns 404, no body-size middleware

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/routes/__init__.py`: empty

`server/ai_aid/routes/health.py`:
```python
import sqlite3
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    store = request.app.state.store
    db_ok = "ok"
    try:
        with sqlite3.connect(settings.db_path) as c:
            c.execute("SELECT 1").fetchone()
    except Exception as e:
        db_ok = f"error: {e}"
    return {"ok": db_ok == "ok", "db": db_ok, "events_buffered": 0}
```

Replace `server/ai_aid/main.py`:
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai_aid.config import Settings
from ai_aid.db import Store
from ai_aid.errors import register_handlers, payload_too_large
from ai_aid.rate_limit import SlidingWindow
from ai_aid.routes import health
from migration_runner import apply_migrations


def create_app() -> FastAPI:
    settings = Settings.from_env()
    apply_migrations(settings.db_path)

    app = FastAPI(title="ai-aid", version="0.1.0")
    app.state.settings = settings
    app.state.store = Store(settings.db_path)
    app.state.rate_limiter = SlidingWindow(
        limit=settings.rate_limit_per_min, window_ms=60_000
    )

    register_handlers(app)

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        max_bytes = settings.max_body_kb * 1024
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > max_bytes:
            err = payload_too_large(int(cl) // 1024)
            return JSONResponse(
                status_code=err.status_code,
                content={"error": err.error, "message": err.message, **err.extra},
            )
        return await call_next(request)

    app.include_router(health.router)
    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/integration/test_health.py -v`
Expected: PASS — 3 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/main.py ai_aid/routes/ tests/integration/test_health.py
git commit -m "feat(server): wire app factory with health, body limit, store, rate limiter"
```

---

### Task 9: POST /api/requests

**Files:**
- Create: `server/ai_aid/routes/requests.py`
- Modify: `server/ai_aid/main.py` (register router)
- Create: `server/tests/integration/test_post_requests.py`

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_post_requests.py`:
```python
def _payload(**overrides):
    base = {
        "client_id": "alice",
        "model": "haiku-4.5",
        "goal": "g",
        "context": "c",
        "tried": "t",
        "error": None,
        "constraints": None,
        "question": "q",
    }
    base.update(overrides)
    return base


def test_create_returns_201_with_id(client):
    r = client.post("/api/requests", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["status"] == "open"
    assert body["created_at"] > 0


def test_missing_required_field_returns_400(client):
    payload = _payload()
    del payload["goal"]
    r = client.post("/api/requests", json=payload)
    assert r.status_code == 400 or r.status_code == 422


def test_blank_required_field_returns_validation_error(client):
    r = client.post("/api/requests", json=_payload(question="   "))
    assert r.status_code == 400 or r.status_code == 422


def test_optional_fields_can_be_omitted(client):
    payload = _payload()
    del payload["error"]
    del payload["constraints"]
    r = client.post("/api/requests", json=payload)
    assert r.status_code == 201


def test_rate_limit_blocks_after_n(client, monkeypatch):
    # The fixture sets limit=30, so 31st should fail
    last_status = None
    for i in range(31):
        r = client.post("/api/requests", json=_payload())
        last_status = r.status_code
    assert last_status == 429
    body = r.json()
    assert body["error"] == "rate_limited"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/integration/test_post_requests.py -v`
Expected: FAIL — `/api/requests` returns 404

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/routes/requests.py`:
```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ai_aid.errors import rate_limited
from ai_aid.models import AskRequest, CreateResponse

router = APIRouter(prefix="/api/requests")


@router.post("", status_code=201, response_model=CreateResponse)
async def create_request(payload: AskRequest, request: Request):
    settings = request.app.state.settings
    rl = request.app.state.rate_limiter
    if not rl.allow(payload.client_id):
        raise rate_limited(client_id=payload.client_id, limit=settings.rate_limit_per_min)
    store = request.app.state.store
    rid = store.create_request(payload.model_dump())
    row = store.get_request(rid)
    return {"id": row["id"], "status": row["status"], "created_at": row["created_at"]}
```

Modify `server/ai_aid/main.py` — add at bottom of `create_app` before `return app`:
```python
    from ai_aid.routes import requests as requests_routes
    app.include_router(requests_routes.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/integration/test_post_requests.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/routes/requests.py ai_aid/main.py tests/integration/test_post_requests.py
git commit -m "feat(server): POST /api/requests with rate limit + validation"
```

---

### Task 10: GET /api/requests with filters

**Files:**
- Modify: `server/ai_aid/routes/requests.py`
- Create: `server/tests/integration/test_get_requests.py`

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_get_requests.py`:
```python
def _post(client, **overrides):
    base = {
        "client_id": "alice", "model": "haiku-4.5",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    r = client.post("/api/requests", json=base)
    assert r.status_code == 201
    return r.json()["id"]


def test_default_returns_open_only(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="bob")
    client.post(f"/api/requests/{a}/close")
    r = client.get("/api/requests")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert b in ids
    assert a not in ids


def test_status_all_returns_both(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="bob")
    client.post(f"/api/requests/{a}/close")
    r = client.get("/api/requests?status=all")
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert {a, b} <= ids


def test_exclude_client_filters_out(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="bob")
    r = client.get("/api/requests?exclude_client=alice")
    ids = {x["id"] for x in r.json()}
    assert b in ids
    assert a not in ids


def test_mine_returns_own_requests_in_all_statuses(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="alice")
    _post(client, client_id="bob")
    client.post(f"/api/requests/{a}/close")
    r = client.get("/api/requests?status=all&client_id=alice&mine=1")
    ids = {x["id"] for x in r.json()}
    assert ids == {a, b}


def test_summary_includes_answer_count(client):
    a = _post(client, client_id="alice")
    client.post(f"/api/requests/{a}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    client.post(f"/api/requests/{a}/answers", json={
        "solver_client_id": "carol", "solver_model": "m", "summary": "s",
    })
    r = client.get("/api/requests?status=all")
    item = next(x for x in r.json() if x["id"] == a)
    assert item["answer_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/integration/test_get_requests.py -v`
Expected: FAIL — depends on close + answer endpoints not yet built; isolate the GET test:
```bash
cd server && pytest tests/integration/test_get_requests.py::test_default_returns_open_only -v
```
Expected: 405 or 404 on GET (route not yet registered)

- [ ] **Step 3: Write minimal implementation**

Modify `server/ai_aid/routes/requests.py` — add at end:
```python
from typing import Optional
from fastapi import Query
from ai_aid.models import RequestSummary


@router.get("", response_model=list[RequestSummary])
async def list_requests(
    request: Request,
    status: str = Query("open", pattern="^(open|closed|all)$"),
    exclude_client: Optional[str] = None,
    client_id: Optional[str] = None,
    mine: int = 0,
):
    store = request.app.state.store
    only = client_id if mine == 1 else None
    rows = store.list_requests(status=status, exclude_client=exclude_client, only_client=only)
    out = []
    for row in rows:
        answers = store.list_answers(row["id"])
        out.append({
            "id": row["id"], "client_id": row["client_id"], "model": row["model"],
            "goal": row["goal"], "status": row["status"],
            "created_at": row["created_at"], "closed_at": row["closed_at"],
            "answer_count": len(answers),
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

(Tests for close + answers depend on later tasks. Run only the standalone GET assertions:)

Run: `cd server && pytest tests/integration/test_get_requests.py::test_exclude_client_filters_out -v`
Expected: PASS

Other tests in this file will pass once Tasks 11–12 land. Mark this task done; full file passes by Task 12.

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/routes/requests.py tests/integration/test_get_requests.py
git commit -m "feat(server): GET /api/requests with status/exclude_client/mine filters"
```

---

### Task 11: POST /api/requests/{id}/answers (with self-solve check)

**Files:**
- Create: `server/ai_aid/routes/answers.py`
- Modify: `server/ai_aid/main.py` (register router)
- Create: `server/tests/integration/test_post_answers.py`

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_post_answers.py`:
```python
def _post_request(client, client_id="alice"):
    r = client.post("/api/requests", json={
        "client_id": client_id, "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    return r.json()["id"]


def _ans(**overrides):
    base = {"solver_client_id": "bob", "solver_model": "m", "summary": "s"}
    base.update(overrides)
    return base


def test_create_answer_returns_201(client):
    rid = _post_request(client, "alice")
    r = client.post(f"/api/requests/{rid}/answers", json=_ans())
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["created_at"] > 0


def test_self_solve_returns_403(client):
    rid = _post_request(client, "alice")
    r = client.post(
        f"/api/requests/{rid}/answers",
        json=_ans(solver_client_id="alice"),
    )
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "forbidden"
    assert body["request_id"] == rid


def test_answer_on_unknown_request_returns_404(client):
    r = client.post(
        "/api/requests/00000000-0000-0000-0000-000000000000/answers",
        json=_ans(),
    )
    assert r.status_code == 404


def test_missing_summary_returns_validation_error(client):
    rid = _post_request(client, "alice")
    r = client.post(
        f"/api/requests/{rid}/answers",
        json={"solver_client_id": "bob", "solver_model": "m"},
    )
    assert r.status_code in (400, 422)


def test_blank_summary_rejected(client):
    rid = _post_request(client, "alice")
    r = client.post(
        f"/api/requests/{rid}/answers",
        json=_ans(summary="   "),
    )
    assert r.status_code in (400, 422)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/integration/test_post_answers.py -v`
Expected: FAIL — `/api/requests/{id}/answers` returns 405

- [ ] **Step 3: Write minimal implementation**

`server/ai_aid/routes/answers.py`:
```python
from fastapi import APIRouter, Request

from ai_aid.errors import forbidden, not_found, conflict
from ai_aid.models import AnswerRequest

router = APIRouter(prefix="/api/requests")


@router.post("/{rid}/answers", status_code=201)
async def create_answer(rid: str, payload: AnswerRequest, request: Request):
    store = request.app.state.store
    req_row = store.get_request(rid)
    if req_row is None:
        raise not_found(f"request {rid} not found", request_id=rid)
    if req_row["status"] != "open":
        raise conflict("request not open", status=req_row["status"], request_id=rid)
    if req_row["client_id"] == payload.solver_client_id:
        raise forbidden("cannot solve own request", request_id=rid)
    aid = store.create_answer(rid, payload.model_dump())
    answers = store.list_answers(rid)
    new_one = next(a for a in answers if a["id"] == aid)
    return {"id": aid, "created_at": new_one["created_at"]}
```

Modify `server/ai_aid/main.py` — register router with the rest:
```python
    from ai_aid.routes import answers as answers_routes
    app.include_router(answers_routes.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/integration/test_post_answers.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/routes/answers.py ai_aid/main.py tests/integration/test_post_answers.py
git commit -m "feat(server): POST /api/requests/{id}/answers with self-solve guard"
```

---

### Task 12: GET /api/requests/{id}, POST close, DELETE

**Files:**
- Modify: `server/ai_aid/routes/requests.py`
- Create: `server/ai_aid/routes/lifecycle.py`
- Modify: `server/ai_aid/main.py`
- Create: `server/tests/integration/test_get_request_detail.py`
- Create: `server/tests/integration/test_close_request.py`
- Create: `server/tests/integration/test_delete_request.py`

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_get_request_detail.py`:
```python
def _post(client, client_id="alice"):
    r = client.post("/api/requests", json={
        "client_id": client_id, "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": "e", "constraints": "k", "question": "q",
    })
    return r.json()["id"]


def test_detail_returns_full_request(client):
    rid = _post(client)
    r = client.get(f"/api/requests/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == rid
    assert body["context"] == "c"
    assert body["error"] == "e"
    assert body["answers"] == []


def test_detail_includes_answers_in_order(client):
    rid = _post(client, "alice")
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "first",
    })
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "carol", "solver_model": "m", "summary": "second",
    })
    r = client.get(f"/api/requests/{rid}")
    body = r.json()
    assert [a["summary"] for a in body["answers"]] == ["first", "second"]


def test_detail_404_for_missing(client):
    r = client.get("/api/requests/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
```

`server/tests/integration/test_close_request.py`:
```python
def _post(client):
    r = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    return r.json()["id"]


def test_close_open_returns_200(client):
    rid = _post(client)
    r = client.post(f"/api/requests/{rid}/close")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_close_already_closed_returns_409(client):
    rid = _post(client)
    client.post(f"/api/requests/{rid}/close")
    r = client.post(f"/api/requests/{rid}/close")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "conflict"
    assert body["status"] == "closed"


def test_close_unknown_returns_404(client):
    r = client.post("/api/requests/00000000-0000-0000-0000-000000000000/close")
    assert r.status_code == 404


def test_solve_after_close_returns_409(client):
    rid = _post(client)
    client.post(f"/api/requests/{rid}/close")
    r = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    assert r.status_code == 409
```

`server/tests/integration/test_delete_request.py`:
```python
def _post(client):
    r = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    return r.json()["id"]


def test_delete_returns_204(client):
    rid = _post(client)
    r = client.delete(f"/api/requests/{rid}")
    assert r.status_code == 204
    assert client.get(f"/api/requests/{rid}").status_code == 404


def test_delete_cascades_answers(client):
    rid = _post(client)
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    client.delete(f"/api/requests/{rid}")
    # Recreate request with same client; ensure no orphan rows surface in detail
    r2 = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    rid2 = r2.json()["id"]
    detail = client.get(f"/api/requests/{rid2}").json()
    assert detail["answers"] == []


def test_delete_unknown_returns_404(client):
    r = client.delete("/api/requests/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd server && pytest tests/integration/test_get_request_detail.py tests/integration/test_close_request.py tests/integration/test_delete_request.py -v
```
Expected: most FAIL — endpoints not yet defined.

- [ ] **Step 3: Write minimal implementation**

Modify `server/ai_aid/routes/requests.py` — append:
```python
from fastapi import status as http_status
from fastapi.responses import Response

from ai_aid.errors import not_found
from ai_aid.models import RequestDetail, AnswerOut


@router.get("/{rid}", response_model=RequestDetail)
async def get_request(rid: str, request: Request):
    store = request.app.state.store
    row = store.get_request(rid)
    if row is None:
        raise not_found(f"request {rid} not found", request_id=rid)
    answers = [
        AnswerOut(**{
            "id": a["id"], "solver_client_id": a["solver_client_id"],
            "solver_model": a["solver_model"], "summary": a["summary"],
            "solution": a["solution"], "reasoning": a["reasoning"],
            "caveats": a["caveats"], "created_at": a["created_at"],
        }).model_dump()
        for a in store.list_answers(rid)
    ]
    return {**row, "answers": answers}


@router.delete("/{rid}", status_code=204)
async def delete_request(rid: str, request: Request):
    store = request.app.state.store
    if not store.delete_request(rid):
        raise not_found(f"request {rid} not found", request_id=rid)
    return Response(status_code=204)
```

`server/ai_aid/routes/lifecycle.py`:
```python
from fastapi import APIRouter, Request

from ai_aid.errors import not_found, conflict

router = APIRouter(prefix="/api/requests")


@router.post("/{rid}/close")
async def close_request(rid: str, request: Request):
    store = request.app.state.store
    row = store.get_request(rid)
    if row is None:
        raise not_found(f"request {rid} not found", request_id=rid)
    if not store.close_request(rid):
        raise conflict("request not open", status=row["status"], request_id=rid)
    closed = store.get_request(rid)
    return {"id": rid, "status": closed["status"], "closed_at": closed["closed_at"]}
```

Modify `server/ai_aid/main.py` — register lifecycle router:
```python
    from ai_aid.routes import lifecycle as lifecycle_routes
    app.include_router(lifecycle_routes.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd server && pytest tests/integration/ -v
```
Expected: all pass — including previously partial test_get_requests.py file from Task 10.

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/routes/requests.py ai_aid/routes/lifecycle.py ai_aid/main.py \
  tests/integration/test_get_request_detail.py \
  tests/integration/test_close_request.py \
  tests/integration/test_delete_request.py
git commit -m "feat(server): GET detail, POST close, DELETE request endpoints"
```

---

### Task 13: Error response shape consistency

**Files:**
- Create: `server/tests/integration/test_error_shape.py`
- Modify: `server/ai_aid/main.py` (catch Pydantic validation errors → unified shape)

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_error_shape.py`:
```python
def test_validation_error_uses_unified_shape(client):
    r = client.post("/api/requests", json={"client_id": "x"})  # missing many fields
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "bad_request"
    assert "message" in body
    assert "fields" in body  # list of offending field paths


def test_404_shape(client):
    r = client.get("/api/requests/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not_found"
    assert "message" in body


def test_403_self_solve_shape(client):
    r = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    rid = r.json()["id"]
    r2 = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "alice", "solver_model": "m", "summary": "s",
    })
    body = r2.json()
    assert r2.status_code == 403
    assert body["error"] == "forbidden"
    assert body["request_id"] == rid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/integration/test_error_shape.py -v`
Expected: `test_validation_error_uses_unified_shape` FAILs — Pydantic returns 422 with FastAPI's default shape, not our `error` key.

- [ ] **Step 3: Write minimal implementation**

Modify `server/ai_aid/main.py` — add validation handler inside `create_app`, after `register_handlers(app)`:
```python
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()]
        return JSONResponse(
            status_code=400,
            content={
                "error": "bad_request",
                "message": "validation failed",
                "fields": fields,
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest tests/integration/test_error_shape.py -v`
Expected: PASS — 3 passed

Then run full suite:
```bash
cd server && pytest -v
```
Expected: all unit + integration tests pass.

- [ ] **Step 5: Commit**

```bash
cd server
git add ai_aid/main.py tests/integration/test_error_shape.py
git commit -m "feat(server): unify Pydantic 422 -> 400 with bad_request shape"
```

---

### Task 14: Manual smoke test against running server

**Files:** none (verification only)

- [ ] **Step 1: Start the server locally**

Run:
```bash
cd server
mkdir -p /tmp/ai-aid-data
AI_AID_DB_PATH=/tmp/ai-aid-data/dev.db uvicorn ai_aid.main:create_app --factory --reload
```
Expected: server logs show `Application startup complete` on `http://127.0.0.1:8000`.

- [ ] **Step 2: Smoke test each endpoint with curl**

In a second terminal:
```bash
curl -s http://127.0.0.1:8000/health
# Expect: {"ok":true,"db":"ok","events_buffered":0}

curl -s -X POST http://127.0.0.1:8000/api/requests \
  -H "Content-Type: application/json" \
  -d '{"client_id":"alice","model":"haiku-4.5","goal":"PG fts cn","context":"PG16","tried":"to_tsvector simple","question":"how"}'
# Expect: {"id":"<uuid>","status":"open","created_at":<int>}

RID="<paste id from above>"

curl -s http://127.0.0.1:8000/api/requests
curl -s "http://127.0.0.1:8000/api/requests?status=all&client_id=alice&mine=1"
curl -s "http://127.0.0.1:8000/api/requests/$RID"

# Self-solve attempt (should 403)
curl -s -X POST "http://127.0.0.1:8000/api/requests/$RID/answers" \
  -H "Content-Type: application/json" \
  -d '{"solver_client_id":"alice","solver_model":"m","summary":"s"}'
# Expect: 403 with {"error":"forbidden","message":"cannot solve own request","request_id":"..."}

# Different client solving
curl -s -X POST "http://127.0.0.1:8000/api/requests/$RID/answers" \
  -H "Content-Type: application/json" \
  -d '{"solver_client_id":"bob","solver_model":"opus-4.7","summary":"use pg_trgm"}'
# Expect: 201

curl -s "http://127.0.0.1:8000/api/requests/$RID"
# Expect: detail with one answer

curl -s -X POST "http://127.0.0.1:8000/api/requests/$RID/close"
# Expect: {"id":"...","status":"closed","closed_at":<int>}

curl -s -X DELETE "http://127.0.0.1:8000/api/requests/$RID" -w "\n%{http_code}\n"
# Expect: 204
```

All responses match expectations → continue.

- [ ] **Step 3: Stop server**

Ctrl-C in the uvicorn terminal.

- [ ] **Step 4: Cleanup**

```bash
rm -rf /tmp/ai-aid-data
```

- [ ] **Step 5: Commit verification note**

No code changes; nothing to commit. Skip.

---

### Task 15: Final test run + plan-1 wrap

**Files:** none (verification + tag)

- [ ] **Step 1: Run full pytest suite**

Run:
```bash
cd server && pytest -v --tb=short
```
Expected: all tests pass. Capture final count (should be 30+).

- [ ] **Step 2: Verify import graph is clean**

Run:
```bash
cd server && python -c "from ai_aid.main import create_app; app = create_app(); print('routes:', sorted(r.path for r in app.routes if hasattr(r, 'path')))"
```
Expected: prints route list including `/health`, `/api/requests`, `/api/requests/{rid}`, `/api/requests/{rid}/answers`, `/api/requests/{rid}/close`.

- [ ] **Step 3: Tag**

```bash
cd /Users/liukun/j/ai-aid
git tag -a server-core-v0.1.0 -m "Plan 1 complete: server core API working"
```

- [ ] **Step 4: Hand off**

Plan 1 done. Server core works. Next: Plan 2 (SSE + Web dashboard).
