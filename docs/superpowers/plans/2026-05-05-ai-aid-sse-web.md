# ai-aid SSE + Web Dashboard Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Server-Sent Events streaming and a single-page HTML dashboard that displays help requests in real time, with manual close/delete admin controls.

**Architecture:** Persist every state-change as a row in the `events` table (schema already exists from Plan 1). Each REST handler that mutates state appends an event. SSE endpoint polls events table on a 1-second tick, supports `Last-Event-ID` replay, emits `replay-gap` when buffer trimmed beyond client cursor. Single-page HTML/JS dashboard uses `EventSource` plus initial REST fetch.

**Tech Stack:** sse-starlette (server-side SSE for FastAPI), vanilla JavaScript + Pico.css (CDN) + highlight.js (CDN) for the dashboard.

---

## File Structure

Files this plan adds or modifies:

```
server/
  pyproject.toml                  # +sse-starlette dep
  ai_aid/
    db.py                         # +event CRUD methods
    events.py                     # NEW - event payload helpers
    routes/
      requests.py                 # mutate handlers append events
      answers.py                  # mutate handlers append events
      lifecycle.py                # mutate handlers append events
      sse.py                      # NEW - /events endpoint
      health.py                   # report real events_buffered count
    main.py                       # mount SSE router + static files
  tests/
    unit/
      test_events.py              # NEW - event payloads + db trim
    integration/
      test_sse.py                 # NEW - subscribe + receive events
      test_sse_replay.py          # NEW - Last-Event-ID replay + gap
      test_event_emission.py      # NEW - mutate endpoints emit events
      test_health.py              # update events_buffered assertion
web/
  index.html                      # NEW - dashboard markup
  app.js                          # NEW - state, render, EventSource
  style.css                       # NEW - small overrides on top of Pico
```

**Boundaries:**
- `events.py` builds typed payload dicts; pure functions, no DB.
- `db.py` gains `append_event`, `list_events_after`, `trim_events`. SQL only.
- `routes/sse.py` orchestrates: read events, format SSE frames, poll loop.
- Each mutation route gains a single `append_event(...)` call after the DB write.
- Web layer is fully static — FastAPI just `StaticFiles` mounts `web/`.

---

### Task 1: Add sse-starlette dependency

**Files:**
- Modify: `server/pyproject.toml`

- [ ] **Step 1: Update dependencies**

Edit the `dependencies` list in `server/pyproject.toml` to include sse-starlette:
```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "sse-starlette>=2.1",
]
```

- [ ] **Step 2: Reinstall**

Run:
```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -q
```
Expected: 61 passed (no regressions).

- [ ] **Step 3: Commit**

```bash
git add server/pyproject.toml
git commit -m "chore(server): add sse-starlette dependency"
```

---

### Task 2: Event payload helpers + DB ops

**Files:**
- Create: `server/ai_aid/events.py`
- Modify: `server/ai_aid/db.py` (append_event, list_events_after, count_events, trim_events, max_event_id)
- Create: `server/tests/unit/test_events.py`

- [ ] **Step 1: Write the failing test**

`server/tests/unit/test_events.py`:
```python
import pytest

from ai_aid import db, events
from migration_runner import apply_migrations


@pytest.fixture
def store(tmp_path):
    p = tmp_path / "t.db"
    apply_migrations(str(p))
    return db.Store(str(p))


def test_request_created_payload_shape():
    p = events.request_created({
        "id": "r1", "client_id": "alice", "model": "m",
        "goal": "g", "status": "open", "created_at": 1, "closed_at": None,
    }, answer_count=0)
    assert p["id"] == "r1"
    assert p["client_id"] == "alice"
    assert p["status"] == "open"
    assert p["answer_count"] == 0


def test_answer_created_payload_shape():
    p = events.answer_created("r1", {
        "id": "a1", "solver_client_id": "bob", "solver_model": "m",
        "summary": "s", "solution": None, "reasoning": None, "caveats": None,
        "created_at": 2,
    })
    assert p["request_id"] == "r1"
    assert p["id"] == "a1"
    assert p["solver_client_id"] == "bob"


def test_request_closed_payload_shape():
    p = events.request_closed("r1", closed_at=42)
    assert p == {"id": "r1", "status": "closed", "closed_at": 42}


def test_request_deleted_payload_shape():
    p = events.request_deleted("r1")
    assert p == {"id": "r1"}


def test_append_and_list_events_after(store):
    a = store.append_event("request.created", {"id": "r1"})
    b = store.append_event("answer.created", {"id": "a1"})
    rows = store.list_events_after(0, limit=10)
    assert [r["id"] for r in rows] == [a, b]
    assert rows[0]["kind"] == "request.created"
    rows_after_a = store.list_events_after(a, limit=10)
    assert [r["id"] for r in rows_after_a] == [b]


def test_trim_events_keeps_newest(store):
    ids = [store.append_event("request.created", {"i": i}) for i in range(5)]
    store.trim_events(keep=3)
    rows = store.list_events_after(0, limit=10)
    assert sorted(r["id"] for r in rows) == sorted(ids[-3:])


def test_count_events(store):
    store.append_event("request.created", {})
    store.append_event("answer.created", {})
    assert store.count_events() == 2


def test_max_event_id(store):
    assert store.max_event_id() == 0
    store.append_event("request.created", {})
    last = store.append_event("answer.created", {})
    assert store.max_event_id() == last
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: No module named 'ai_aid.events'`.

Run: `cd server && .venv/bin/pytest tests/unit/test_events.py -v`

- [ ] **Step 3: Implement**

`server/ai_aid/events.py`:
```python
from typing import Optional


def request_created(row: dict, *, answer_count: int = 0) -> dict:
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "model": row["model"],
        "goal": row["goal"],
        "status": row["status"],
        "created_at": row["created_at"],
        "closed_at": row["closed_at"],
        "answer_count": answer_count,
    }


def answer_created(request_id: str, ans: dict) -> dict:
    return {
        "request_id": request_id,
        "id": ans["id"],
        "solver_client_id": ans["solver_client_id"],
        "solver_model": ans["solver_model"],
        "summary": ans["summary"],
        "solution": ans["solution"],
        "reasoning": ans["reasoning"],
        "caveats": ans["caveats"],
        "created_at": ans["created_at"],
    }


def request_closed(rid: str, *, closed_at: int) -> dict:
    return {"id": rid, "status": "closed", "closed_at": closed_at}


def request_deleted(rid: str) -> dict:
    return {"id": rid}
```

Append to `server/ai_aid/db.py`:
```python
import json as _json


    def append_event(self, kind: str, payload: dict) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO events (kind, payload, created_at) VALUES (?, ?, ?)",
                (kind, _json.dumps(payload), _now_ms()),
            )
            return int(cur.lastrowid)

    def list_events_after(self, last_id: int, *, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
                (last_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = _json.loads(d["payload"])
            out.append(d)
        return out

    def count_events(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def trim_events(self, *, keep: int) -> None:
        with self._conn() as c:
            c.execute(
                "DELETE FROM events WHERE id NOT IN ("
                "SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                (keep,),
            )

    def max_event_id(self) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
            return int(row[0])

    def min_event_id(self) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COALESCE(MIN(id), 0) FROM events").fetchone()
            return int(row[0])
```

When pasting, place these methods inside the existing `Store` class (just append before the closing of the class). Add `import json as _json` near the top of the file.

- [ ] **Step 4: Run tests, expect PASS — 8 passed.**

- [ ] **Step 5: Commit**

```bash
git add server/ai_aid/events.py server/ai_aid/db.py server/tests/unit/test_events.py
git commit -m "feat(server): add event payload builders + Store event ops"
```

---

### Task 3: Wire event emission into mutation handlers

**Files:**
- Modify: `server/ai_aid/routes/requests.py` (POST + DELETE)
- Modify: `server/ai_aid/routes/answers.py` (POST)
- Modify: `server/ai_aid/routes/lifecycle.py` (close)
- Create: `server/tests/integration/test_event_emission.py`

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_event_emission.py`:
```python
def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def test_post_request_emits_request_created(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("request.created", rid) in kinds


def test_post_answer_emits_answer_created(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    a = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    aid = a.json()["id"]
    store = client.app.state.store
    rows = store.list_events_after(0, limit=20)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("answer.created", aid) in kinds


def test_close_emits_request_closed(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    client.post(f"/api/requests/{rid}/close")
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("request.closed", rid) in kinds


def test_delete_emits_request_deleted(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    client.delete(f"/api/requests/{rid}")
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("request.deleted", rid) in kinds


def test_failed_self_solve_emits_no_event(client):
    r = client.post("/api/requests", json=_payload(client_id="alice"))
    rid = r.json()["id"]
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "alice", "solver_model": "m", "summary": "s",
    })
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    # only request.created event, no answer.created since solve was rejected
    answer_events = [k for k in kinds if k[0] == "answer.created"]
    assert answer_events == []
```

- [ ] **Step 2: Run, expect FAIL** — events not yet emitted.

Run: `cd server && .venv/bin/pytest tests/integration/test_event_emission.py -v`

- [ ] **Step 3: Implement**

In `server/ai_aid/routes/requests.py`, modify `create_request` and `delete_request`. After the DB mutation succeeds, call `store.append_event(...)`:

```python
from ai_aid import events as event_payloads


# In create_request, after rid is returned and row fetched:
async def create_request(payload: AskRequest, request: Request):
    settings = request.app.state.settings
    rl = request.app.state.rate_limiter
    if not rl.allow(payload.client_id):
        raise rate_limited(client_id=payload.client_id, limit=settings.rate_limit_per_min)
    store = request.app.state.store
    rid = store.create_request(payload.model_dump())
    row = store.get_request(rid)
    store.append_event("request.created", event_payloads.request_created(row, answer_count=0))
    store.trim_events(keep=settings.event_buffer)
    return {"id": row["id"], "status": row["status"], "created_at": row["created_at"]}


# In delete_request, after the delete succeeds:
async def delete_request(rid: str, request: Request):
    store = request.app.state.store
    if not store.delete_request(rid):
        raise not_found(f"request {rid} not found", request_id=rid)
    settings = request.app.state.settings
    store.append_event("request.deleted", event_payloads.request_deleted(rid))
    store.trim_events(keep=settings.event_buffer)
    return Response(status_code=204)
```

In `server/ai_aid/routes/answers.py`, modify `create_answer`. After `aid = store.create_answer(...)` succeeds:

```python
from ai_aid import events as event_payloads


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
    settings = request.app.state.settings
    store.append_event("answer.created", event_payloads.answer_created(rid, new_one))
    store.trim_events(keep=settings.event_buffer)
    return {"id": aid, "created_at": new_one["created_at"]}
```

In `server/ai_aid/routes/lifecycle.py`, modify `close_request`. After successful close:

```python
from ai_aid import events as event_payloads


async def close_request(rid: str, request: Request):
    store = request.app.state.store
    row = store.get_request(rid)
    if row is None:
        raise not_found(f"request {rid} not found", request_id=rid)
    if not store.close_request(rid):
        raise conflict("request not open", status=row["status"], request_id=rid)
    closed = store.get_request(rid)
    settings = request.app.state.settings
    store.append_event(
        "request.closed",
        event_payloads.request_closed(rid, closed_at=closed["closed_at"]),
    )
    store.trim_events(keep=settings.event_buffer)
    return {"id": rid, "status": closed["status"], "closed_at": closed["closed_at"]}
```

- [ ] **Step 4: Run tests, expect PASS — 5 passed.**

Then run full suite:
```bash
cd /Users/liukun/j/ai-aid/server && .venv/bin/pytest -q
```
Expected: 74 passed (61 + 8 from Task 2 + 5 from Task 3).

- [ ] **Step 5: Commit**

```bash
git add server/ai_aid/routes/ server/tests/integration/test_event_emission.py
git commit -m "feat(server): emit events on request/answer/close/delete"
```

---

### Task 4: Update /health to report buffered event count

**Files:**
- Modify: `server/ai_aid/routes/health.py`
- Modify: `server/tests/integration/test_health.py`

- [ ] **Step 1: Write the failing test**

Replace `test_health_returns_ok` in `server/tests/integration/test_health.py`:
```python
def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["db"] == "ok"
    assert body["events_buffered"] == 0


def test_health_reports_buffered_count(client):
    client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    r = client.get("/health")
    body = r.json()
    assert body["events_buffered"] == 1
```

(Keep `test_oversized_body_rejected` and `test_app_boots` as-is.)

- [ ] **Step 2: Run, expect 1 fail** (`test_health_reports_buffered_count` — count is hardcoded 0).

Run: `cd server && .venv/bin/pytest tests/integration/test_health.py -v`

- [ ] **Step 3: Implement**

Replace `server/ai_aid/routes/health.py`:
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
    except Exception:
        db_ok = "error"
    events_buffered = store.count_events() if db_ok == "ok" else 0
    return {"ok": db_ok == "ok", "db": db_ok, "events_buffered": events_buffered}
```

- [ ] **Step 4: Run tests, expect PASS — all 4 pass.**

- [ ] **Step 5: Commit**

```bash
git add server/ai_aid/routes/health.py server/tests/integration/test_health.py
git commit -m "feat(server): /health reports actual buffered event count"
```

---

### Task 5: SSE /events endpoint

**Files:**
- Create: `server/ai_aid/routes/sse.py`
- Modify: `server/ai_aid/main.py` (register SSE router)
- Create: `server/tests/integration/test_sse.py`

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_sse.py`:
```python
import json
import re


def _read_sse_events(response):
    """Parse SSE wire format, return list of (id, event, data)."""
    events = []
    current = {}
    for line in response.iter_lines():
        if line is None:
            continue
        line = line if isinstance(line, str) else line.decode()
        if line == "":
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):
            continue
        if ":" in line:
            field, _, value = line.partition(":")
            value = value.lstrip(" ")
            if field == "id":
                current["id"] = int(value)
            elif field == "event":
                current["event"] = value
            elif field == "data":
                current["data"] = value
    if current:
        events.append(current)
    return events


def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def test_sse_endpoint_returns_text_event_stream(client):
    # Quick handshake check (close immediately by making the request and not iterating)
    with client.stream("GET", "/events?last_event_id=0&max_seconds=0") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")


def test_sse_replays_existing_events(client):
    client.post("/api/requests", json=_payload())
    client.post("/api/requests", json=_payload())
    with client.stream("GET", "/events?last_event_id=0&max_seconds=0") as r:
        events = _read_sse_events(r)
    kinds = [e.get("event") for e in events if e.get("event")]
    assert kinds.count("request.created") == 2


def test_sse_skips_events_before_last_event_id(client):
    r1 = client.post("/api/requests", json=_payload())
    store = client.app.state.store
    last_id = store.max_event_id()
    client.post("/api/requests", json=_payload())  # second event
    with client.stream(
        "GET", f"/events?last_event_id={last_id}&max_seconds=0"
    ) as r:
        events = _read_sse_events(r)
    kinds = [e.get("event") for e in events if e.get("event")]
    # Only one request.created should appear (the second post)
    assert kinds == ["request.created"]
```

NOTE: The endpoint accepts `last_event_id` as a query param for tests; in production browsers, it'll arrive via the standard `Last-Event-ID` HTTP header. The endpoint must accept both. The `max_seconds` query param is a test-only knob to make the polling loop exit so the test can finish.

- [ ] **Step 2: Run, expect FAIL** (`/events` returns 404).

Run: `cd server && .venv/bin/pytest tests/integration/test_sse.py -v`

- [ ] **Step 3: Implement**

`server/ai_aid/routes/sse.py`:
```python
import asyncio
import json
import time
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


def _sse_frame(*, event: str, data: dict, event_id: Optional[int] = None) -> bytes:
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    parts.append("")
    parts.append("")
    return "\n".join(parts).encode("utf-8")


async def _stream(
    request: Request,
    initial_last_id: int,
    poll_interval: float,
    max_seconds: Optional[float],
) -> AsyncGenerator[bytes, None]:
    store = request.app.state.store

    # 1) Replay-gap detection: if buffer doesn't contain initial_last_id,
    #    emit a replay-gap event before resuming.
    if initial_last_id > 0:
        min_id = store.min_event_id()
        if min_id > 0 and initial_last_id < min_id - 1:
            yield _sse_frame(
                event="replay-gap",
                data={"requested": initial_last_id, "available_from": min_id},
            )

    last_id = initial_last_id
    started = time.monotonic()
    sent_initial_batch = False
    while True:
        if await request.is_disconnected():
            return
        rows = store.list_events_after(last_id, limit=100)
        for row in rows:
            yield _sse_frame(event=row["kind"], data=row["payload"], event_id=row["id"])
            last_id = row["id"]
        sent_initial_batch = True
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            return
        await asyncio.sleep(poll_interval)


@router.get("/events")
async def events(request: Request):
    headers = request.headers
    qp = request.query_params
    last_id_str = qp.get("last_event_id") or headers.get("last-event-id") or "0"
    try:
        initial_last_id = int(last_id_str)
    except ValueError:
        initial_last_id = 0
    poll_str = qp.get("poll_interval", "1.0")
    try:
        poll_interval = float(poll_str)
    except ValueError:
        poll_interval = 1.0
    max_seconds_str = qp.get("max_seconds")
    max_seconds = None
    if max_seconds_str is not None:
        try:
            max_seconds = float(max_seconds_str)
        except ValueError:
            max_seconds = None
    return StreamingResponse(
        _stream(request, initial_last_id, poll_interval, max_seconds),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

Modify `server/ai_aid/main.py` — register router with the rest:
```python
    from ai_aid.routes import sse as sse_routes
    app.include_router(sse_routes.router)
```

- [ ] **Step 4: Run tests, expect PASS — 3 passed.**

Run full suite. Expected: 77 passed.

- [ ] **Step 5: Commit**

```bash
git add server/ai_aid/routes/sse.py server/ai_aid/main.py server/tests/integration/test_sse.py
git commit -m "feat(server): add /events SSE endpoint with replay support"
```

---

### Task 6: Replay-gap test

**Files:**
- Create: `server/tests/integration/test_sse_replay.py`

- [ ] **Step 1: Write the failing test**

`server/tests/integration/test_sse_replay.py`:
```python
def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def _read_sse_events(response):
    events = []
    current = {}
    for line in response.iter_lines():
        line = line if isinstance(line, str) else line.decode()
        if line == "":
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):
            continue
        if ":" in line:
            field, _, value = line.partition(":")
            value = value.lstrip(" ")
            if field == "id":
                current["id"] = int(value)
            elif field == "event":
                current["event"] = value
            elif field == "data":
                current["data"] = value
    if current:
        events.append(current)
    return events


def test_sse_emits_replay_gap_when_buffer_trimmed_past_cursor(client, monkeypatch):
    # Force tiny buffer so trim is observable
    monkeypatch.setenv("AI_AID_EVENT_BUFFER", "2")
    # Reload the limiter for the same client by re-creating events
    store = client.app.state.store
    # Insert 5 events directly so trim has work to do
    ids = [store.append_event("request.created", {"i": i}) for i in range(5)]
    store.trim_events(keep=2)
    # Cursor below the trimmed range
    with client.stream(
        "GET", f"/events?last_event_id={ids[0]}&max_seconds=0"
    ) as r:
        events = _read_sse_events(r)
    event_kinds = [e.get("event") for e in events if e.get("event")]
    assert "replay-gap" in event_kinds


def test_sse_no_replay_gap_when_cursor_in_range(client):
    store = client.app.state.store
    ids = [store.append_event("request.created", {"i": i}) for i in range(3)]
    with client.stream(
        "GET", f"/events?last_event_id={ids[1]}&max_seconds=0"
    ) as r:
        events = _read_sse_events(r)
    event_kinds = [e.get("event") for e in events if e.get("event")]
    assert "replay-gap" not in event_kinds
```

- [ ] **Step 2: Run, expect 2 failures or initial unclear behavior.**

- [ ] **Step 3: Verify implementation already supports this**

The Task 5 implementation already includes replay-gap logic. If the tests fail, fix the SSE handler (probably an off-by-one).

Re-examine `_stream` in `routes/sse.py`. The condition is `initial_last_id < min_id - 1`. After deleting events 1, 2, 3 keeping 4, 5: `min_id=4`. Cursor=1: `1 < 3` → True → emit gap. Cursor=4: `4 < 3` → False → no gap. Both correct.

If the first test still fails, ensure that monkeypatch.setenv only affects tests, not the live store fixture. The test inserts events directly via `store.append_event` and trims directly via `store.trim_events`, so env var is irrelevant; remove the monkeypatch line if it complicates the fixture. The simpler form:

```python
def test_sse_emits_replay_gap_when_buffer_trimmed_past_cursor(client):
    store = client.app.state.store
    ids = [store.append_event("request.created", {"i": i}) for i in range(5)]
    store.trim_events(keep=2)
    with client.stream(
        "GET", f"/events?last_event_id={ids[0]}&max_seconds=0"
    ) as r:
        events = _read_sse_events(r)
    event_kinds = [e.get("event") for e in events if e.get("event")]
    assert "replay-gap" in event_kinds
```

- [ ] **Step 4: Run tests, expect PASS — 2 passed.**

Full suite expected: 79 passed.

- [ ] **Step 5: Commit**

```bash
git add server/tests/integration/test_sse_replay.py
git commit -m "test(server): cover SSE replay-gap behavior"
```

---

### Task 7: Web dashboard scaffolding (HTML + CSS)

**Files:**
- Create: `web/index.html`
- Create: `web/style.css`
- Create: `web/app.js` (placeholder, expanded in Task 8)
- Modify: `server/ai_aid/main.py` (mount StaticFiles)

- [ ] **Step 1: Create the HTML shell**

`web/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ai-aid Dashboard</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.10.0/build/styles/github.min.css">
  <link rel="stylesheet" href="/web/style.css">
  <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.10.0/build/highlight.min.js"></script>
</head>
<body>
  <main class="container">
    <header>
      <h1>ai-aid <small>help network</small></h1>
      <div id="stats">
        <span id="count-open">open: 0</span>
        <span id="count-closed">closed: 0</span>
        <span id="live-badge" data-state="connecting">● connecting</span>
      </div>
      <nav>
        <select id="filter-status">
          <option value="all">all</option>
          <option value="open" selected>open only</option>
          <option value="closed">closed only</option>
        </select>
        <input id="filter-search" placeholder="search goal/context...">
      </nav>
    </header>
    <section id="cards"></section>
  </main>
  <template id="card-template">
    <article class="card" data-id="">
      <header>
        <span class="badge-id"></span>
        <span class="badge-status"></span>
        <span class="badge-model"></span>
        <span class="badge-time"></span>
      </header>
      <h3 class="goal"></h3>
      <p class="meta">from <span class="client-id"></span> · <span class="answer-count">0</span> answers</p>
      <details>
        <summary>show details</summary>
        <div class="full-body"></div>
        <div class="answers"></div>
      </details>
      <footer>
        <button class="btn-close">close</button>
        <button class="btn-delete">delete</button>
      </footer>
    </article>
  </template>
  <script src="/web/app.js" type="module"></script>
</body>
</html>
```

`web/style.css`:
```css
header h1 { display: inline-block; margin-right: 1rem; }
header h1 small { font-size: 0.6em; color: var(--pico-muted-color); }

#stats { display: inline-flex; gap: 1rem; align-items: center; }
#stats span { padding: 0.2rem 0.6rem; background: var(--pico-card-background-color); border-radius: 0.3rem; }

#live-badge[data-state="connected"] { color: green; }
#live-badge[data-state="reconnecting"] { color: orange; }
#live-badge[data-state="disconnected"] { color: red; }

nav { display: flex; gap: 0.5rem; margin: 1rem 0; }
nav select, nav input { flex: 0 0 auto; }
nav input { flex: 1; }

#cards { display: grid; gap: 1rem; }
.card[data-status="closed"] { opacity: 0.7; }
.card.flash { animation: flash 1s ease-in-out; }
@keyframes flash {
  from { background: #fffbcc; }
  to { background: transparent; }
}

.card header { display: flex; gap: 0.5rem; align-items: center; }
.badge-id, .badge-status, .badge-model { font-family: monospace; font-size: 0.85em; }
.badge-time { margin-left: auto; color: var(--pico-muted-color); font-size: 0.85em; }

.full-body { display: grid; gap: 0.5rem; margin: 1rem 0; }
.full-body dt { font-weight: bold; margin-top: 0.5rem; }

.answers .answer { border-left: 3px solid var(--pico-primary); padding-left: 1rem; margin: 1rem 0; }

.btn-delete { background-color: var(--pico-del-color); }
```

`web/app.js` (placeholder for Task 7; full impl in Task 8):
```javascript
console.log("ai-aid dashboard loading...");
```

Modify `server/ai_aid/main.py` — mount static files. Add near the bottom of `create_app`:
```python
    from fastapi.staticfiles import StaticFiles
    from pathlib import Path

    web_dir = Path(__file__).parent.parent.parent / "web"
    if web_dir.exists():
        app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")

        @app.get("/")
        async def index():
            from fastapi.responses import FileResponse
            return FileResponse(str(web_dir / "index.html"))
```

- [ ] **Step 2: Smoke check**

Start uvicorn:
```bash
cd /Users/liukun/j/ai-aid/server
mkdir -p /tmp/aid-web
AI_AID_DB_PATH=/tmp/aid-web/dev.db .venv/bin/uvicorn ai_aid.main:create_app --factory --host 127.0.0.1 --port 18002 &
sleep 2
curl -s -o /tmp/aid-html.txt -w "HTTP %{http_code}\n" http://127.0.0.1:18002/
grep -c "ai-aid Dashboard" /tmp/aid-html.txt   # Expect: 1
curl -s -o /tmp/aid-css.txt -w "HTTP %{http_code}\n" http://127.0.0.1:18002/web/style.css
grep -c "card" /tmp/aid-css.txt                # Expect: positive
kill %1
rm -rf /tmp/aid-web /tmp/aid-html.txt /tmp/aid-css.txt
```

- [ ] **Step 3: Commit**

```bash
git add web/ server/ai_aid/main.py
git commit -m "feat(web): scaffold dashboard HTML + CSS, mount via StaticFiles"
```

---

### Task 8: Web dashboard JavaScript

**Files:**
- Modify: `web/app.js`

- [ ] **Step 1: Replace `web/app.js` with full implementation**

```javascript
const API_BASE = "";
const SSE_URL = "/events";

const state = {
  cardsById: new Map(),
  lastEventId: 0,
  filter: { status: "open", search: "" },
};

const el = {
  cards: document.getElementById("cards"),
  template: document.getElementById("card-template"),
  filterStatus: document.getElementById("filter-status"),
  filterSearch: document.getElementById("filter-search"),
  liveBadge: document.getElementById("live-badge"),
  countOpen: document.getElementById("count-open"),
  countClosed: document.getElementById("count-closed"),
};

function fmtTime(ms) {
  if (!ms) return "";
  const d = new Date(ms);
  return d.toLocaleString();
}

function updateCounts() {
  let open = 0, closed = 0;
  for (const c of state.cardsById.values()) {
    if (c.data.status === "open") open++;
    else closed++;
  }
  el.countOpen.textContent = `open: ${open}`;
  el.countClosed.textContent = `closed: ${closed}`;
}

function applyFilter(card) {
  const d = card.data;
  const okStatus =
    state.filter.status === "all" ||
    state.filter.status === d.status;
  const search = state.filter.search.toLowerCase();
  const okSearch =
    !search ||
    (d.goal || "").toLowerCase().includes(search) ||
    (d.context || "").toLowerCase().includes(search);
  card.node.style.display = okStatus && okSearch ? "" : "none";
}

function applyFilterAll() {
  for (const card of state.cardsById.values()) applyFilter(card);
}

function renderCardChrome(node, d) {
  node.dataset.id = d.id;
  node.dataset.status = d.status;
  node.querySelector(".badge-id").textContent = `#${d.id.slice(0, 6)}`;
  node.querySelector(".badge-status").textContent = d.status;
  node.querySelector(".badge-model").textContent = d.model || "?";
  node.querySelector(".badge-time").textContent = fmtTime(d.created_at);
  node.querySelector(".goal").textContent = d.goal || "(no goal)";
  node.querySelector(".client-id").textContent = d.client_id || "?";
  node.querySelector(".answer-count").textContent = d.answer_count ?? 0;
}

function renderCardBody(node, d) {
  const body = node.querySelector(".full-body");
  body.innerHTML = "";
  const fields = [
    ["goal", d.goal],
    ["context", d.context],
    ["tried", d.tried],
    ["error", d.error],
    ["constraints", d.constraints],
    ["question", d.question],
  ];
  for (const [k, v] of fields) {
    if (!v) continue;
    const dt = document.createElement("dt");
    dt.textContent = k;
    const dd = document.createElement("dd");
    dd.textContent = v;
    body.appendChild(dt);
    body.appendChild(dd);
  }
  const answersBox = node.querySelector(".answers");
  answersBox.innerHTML = "";
  for (const a of d.answers || []) {
    answersBox.appendChild(renderAnswer(a));
  }
}

function renderAnswer(a) {
  const div = document.createElement("div");
  div.className = "answer";
  div.dataset.id = a.id;
  div.innerHTML = `
    <p><strong>${escapeHtml(a.summary)}</strong>
      <small>by ${escapeHtml(a.solver_client_id)} (${escapeHtml(a.solver_model)}) at ${fmtTime(a.created_at)}</small>
    </p>
  `;
  if (a.solution) {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = a.solution;
    pre.appendChild(code);
    div.appendChild(pre);
    if (window.hljs) hljs.highlightElement(code);
  }
  if (a.reasoning) {
    const p = document.createElement("p");
    p.innerHTML = `<em>reasoning:</em> ${escapeHtml(a.reasoning)}`;
    div.appendChild(p);
  }
  if (a.caveats) {
    const p = document.createElement("p");
    p.innerHTML = `<em>caveats:</em> ${escapeHtml(a.caveats)}`;
    div.appendChild(p);
  }
  return div;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function buildCard(d) {
  const node = el.template.content.firstElementChild.cloneNode(true);
  renderCardChrome(node, d);
  node.querySelector(".btn-close").addEventListener("click", () => closeCard(d.id));
  node.querySelector(".btn-delete").addEventListener("click", () => deleteCard(d.id));
  node.querySelector("details").addEventListener("toggle", async (ev) => {
    if (!ev.target.open) return;
    const detail = await fetchJson(`/api/requests/${d.id}`);
    Object.assign(d, detail);
    renderCardBody(node, d);
  });
  return node;
}

function upsertCard(d) {
  let entry = state.cardsById.get(d.id);
  if (!entry) {
    const node = buildCard(d);
    entry = { node, data: d };
    state.cardsById.set(d.id, entry);
    el.cards.prepend(node);
    node.classList.add("flash");
    setTimeout(() => node.classList.remove("flash"), 1100);
  } else {
    entry.data = { ...entry.data, ...d };
    renderCardChrome(entry.node, entry.data);
  }
  applyFilter(entry);
  updateCounts();
}

function removeCard(id) {
  const entry = state.cardsById.get(id);
  if (!entry) return;
  entry.node.remove();
  state.cardsById.delete(id);
  updateCounts();
}

function bumpAnswerCount(rid, ans) {
  const entry = state.cardsById.get(rid);
  if (!entry) return;
  entry.data.answer_count = (entry.data.answer_count || 0) + 1;
  if (entry.data.answers) entry.data.answers.push(ans);
  renderCardChrome(entry.node, entry.data);
  if (entry.node.querySelector("details").open && entry.data.answers) {
    entry.node.querySelector(".answers").appendChild(renderAnswer(ans));
  }
  updateCounts();
}

function markClosed(rid, closedAt) {
  const entry = state.cardsById.get(rid);
  if (!entry) return;
  entry.data.status = "closed";
  entry.data.closed_at = closedAt;
  renderCardChrome(entry.node, entry.data);
  applyFilter(entry);
  updateCounts();
}

async function fetchJson(path, init) {
  const resp = await fetch(API_BASE + path, init);
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.status === 204 ? null : resp.json();
}

async function loadInitial() {
  const list = await fetchJson("/api/requests?status=all");
  list.sort((a, b) => b.created_at - a.created_at);
  for (const d of list) upsertCard(d);
}

async function closeCard(id) {
  if (!confirm(`Close request ${id.slice(0, 6)}?`)) return;
  await fetchJson(`/api/requests/${id}/close`, { method: "POST" });
}

async function deleteCard(id) {
  if (!confirm(`Permanently DELETE request ${id.slice(0, 6)}? This cannot be undone.`)) return;
  await fetchJson(`/api/requests/${id}`, { method: "DELETE" });
}

function connectSse() {
  const url = `${SSE_URL}?last_event_id=${state.lastEventId}`;
  const es = new EventSource(url);
  es.onopen = () => { el.liveBadge.dataset.state = "connected"; el.liveBadge.textContent = "● live"; };
  es.onerror = () => { el.liveBadge.dataset.state = "reconnecting"; el.liveBadge.textContent = "● reconnecting"; };

  es.addEventListener("request.created", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    upsertCard(d);
  });
  es.addEventListener("answer.created", (ev) => {
    const a = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    bumpAnswerCount(a.request_id, a);
  });
  es.addEventListener("request.closed", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    markClosed(d.id, d.closed_at);
  });
  es.addEventListener("request.deleted", (ev) => {
    const d = JSON.parse(ev.data);
    state.lastEventId = ev.lastEventId ? parseInt(ev.lastEventId) : state.lastEventId;
    removeCard(d.id);
  });
  es.addEventListener("replay-gap", (ev) => {
    console.warn("SSE replay-gap, refetching all", ev.data);
    state.lastEventId = 0;
    state.cardsById.clear();
    el.cards.innerHTML = "";
    loadInitial();
  });
}

el.filterStatus.addEventListener("change", (e) => {
  state.filter.status = e.target.value;
  applyFilterAll();
});
el.filterSearch.addEventListener("input", (e) => {
  state.filter.search = e.target.value;
  applyFilterAll();
});

(async () => {
  try {
    await loadInitial();
    connectSse();
  } catch (e) {
    console.error("Dashboard init failed", e);
    el.liveBadge.dataset.state = "disconnected";
    el.liveBadge.textContent = "● error";
  }
})();
```

- [ ] **Step 2: Manual smoke (no automated test in this task — Task 9 covers Playwright)**

```bash
cd /Users/liukun/j/ai-aid/server
mkdir -p /tmp/aid-web
AI_AID_DB_PATH=/tmp/aid-web/dev.db .venv/bin/uvicorn ai_aid.main:create_app --factory --host 127.0.0.1 --port 18003 > /tmp/aid-w.log 2>&1 &
sleep 2
# Open http://127.0.0.1:18003 in a browser, verify:
#   - Page loads with "ai-aid help network" header
#   - Stats show "open: 0" "closed: 0"
#   - "● live" badge appears (green)
# Then in a second terminal:
curl -s -X POST http://127.0.0.1:18003/api/requests \
  -H "Content-Type: application/json" \
  -d '{"client_id":"alice","model":"haiku-4.5","goal":"Test","context":"c","tried":"t","question":"q"}'
# In browser: card appears at top with yellow flash, "open: 1"
kill %1
rm -rf /tmp/aid-web /tmp/aid-w.log
```

If browser is unavailable, simulate via:
```bash
curl -s -N "http://127.0.0.1:18003/events?last_event_id=0&max_seconds=3" &
# in another shell, post a request, verify SSE frame appears
```

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): dashboard JS with SSE live updates + admin actions"
```

---

### Task 9: Playwright smoke test (optional — manual if Playwright unavailable)

**Files:**
- Create: `web/tests/test_dashboard.py`
- Modify: `server/pyproject.toml` (add playwright + pytest-playwright to test extras)

- [ ] **Step 1: If playwright is not installed in the venv, skip this task and document manual verification in `web/tests/MANUAL.md` instead.**

Manual verification (`web/tests/MANUAL.md`):
```markdown
# Manual web dashboard verification

Start server: `cd server && AI_AID_DB_PATH=/tmp/test.db .venv/bin/uvicorn ai_aid.main:create_app --factory`
Open http://127.0.0.1:8000

Verify:
- [ ] Header shows "ai-aid help network"
- [ ] Stats area shows open/closed counts and "● live" badge
- [ ] Posting a new request via curl makes a card appear with yellow flash
- [ ] Posting an answer increments the answer count badge
- [ ] Clicking close → confirmation → card status switches to closed (opacity dims)
- [ ] Clicking delete → confirmation → card disappears
- [ ] Filtering "open only" hides closed cards
- [ ] Search box filters by goal/context substring
- [ ] Reload page → state restored from REST + SSE resumes
```

- [ ] **Step 2: Commit (manual verification path)**

```bash
mkdir -p web/tests
git add web/tests/MANUAL.md
git commit -m "docs(web): add manual dashboard verification checklist"
```

---

### Task 10: Final integration smoke + tag

- [ ] **Step 1: Run full pytest suite**

```bash
cd /Users/liukun/j/ai-aid/server && .venv/bin/pytest -q
```
Expected: 79 passed.

- [ ] **Step 2: End-to-end smoke**

```bash
mkdir -p /tmp/aid-final
AI_AID_DB_PATH=/tmp/aid-final/dev.db .venv/bin/uvicorn ai_aid.main:create_app --factory --host 127.0.0.1 --port 18004 > /tmp/aid-final.log 2>&1 &
sleep 2
# 1) Confirm /events streams text/event-stream
curl -s -I http://127.0.0.1:18004/events?max_seconds=0 | grep -i content-type
# 2) Confirm / serves HTML
curl -s http://127.0.0.1:18004/ | head -1
# 3) Post request -> stream a 2s window and watch event arrive
curl -s -N "http://127.0.0.1:18004/events?last_event_id=0&max_seconds=2" > /tmp/aid-stream.txt &
SLEEP_PID=$!
sleep 0.3
curl -s -X POST http://127.0.0.1:18004/api/requests \
  -H "Content-Type: application/json" \
  -d '{"client_id":"alice","model":"m","goal":"smoke","context":"c","tried":"t","question":"q"}'
wait $SLEEP_PID
grep -c "request.created" /tmp/aid-stream.txt   # Expect: positive
kill %1 2>/dev/null
rm -rf /tmp/aid-final /tmp/aid-final.log /tmp/aid-stream.txt
```

- [ ] **Step 3: Tag**

```bash
cd /Users/liukun/j/ai-aid
git tag -a sse-web-v0.1.0 -m "Plan 2 complete: SSE + web dashboard"
```

- [ ] **Step 4: Plan 2 done.** Move to Plan 3 (Skills × 3 platforms).
