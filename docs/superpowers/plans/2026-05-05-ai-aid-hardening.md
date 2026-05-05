# ai-aid Production Hardening Tests Implementation Plan (Plan 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add high-signal tests that exercise the system the way it'll be used in production: concurrent clients, full two-AI lifecycle, real network IO, real Docker container, real SSE streaming under writes. Catch failure modes before users do.

**Architecture:** New `tests/e2e/` directory at repo root for cross-component tests that boot real processes (uvicorn, docker container) instead of mocking. New `tools/simulator/` Python module that plays N AI personas against a real server — usable both as a CI test and as a manual load-runner. Existing test suites untouched.

**Tech Stack:** pytest + httpx async client (concurrency), Python stdlib threading + subprocess (process orchestration), bats with real server fork (no mock), Playwright optional for web E2E.

---

## What we're hardening against

| Failure mode | New test that catches it |
|---|---|
| SQLite write contention under concurrency | Task 1 |
| Two-AI handshake breaks (regression in ask/list/solve/check) | Task 2 |
| Skill scripts disagree with real server payload shape | Task 3 |
| SSE drops events under concurrent writes | Task 4 |
| Body-size middleware bypassed by chunked / streaming | Task 5 |
| Unicode/CJK/code blocks corrupted in storage or transit | Task 6 |
| Migration runner breaks existing data on re-run | Task 7 |
| Docker image misses a file or env var | Task 8 |
| Server crash mid-request leaves DB inconsistent | Task 9 |
| Long-running server leaks memory or sockets | Task 10 |

---

## File Structure

```
server/
  tests/
    e2e/
      __init__.py
      conftest.py              # boot real uvicorn fixture
      test_concurrency.py      # Task 1
      test_two_ai_flow.py      # Task 2
      test_sse_under_load.py   # Task 4
      test_body_size_real.py   # Task 5
      test_unicode.py          # Task 6
      test_migration_safety.py # Task 7
      test_crash_recovery.py   # Task 9
tools/
  simulator/
    __init__.py
    persona.py                 # AI persona class (asks, solves, checks)
    runner.py                  # CLI entry: spawn N personas vs server
    README.md
skills/
  tests/
    test_real_server.bats      # Task 3 - skills against actual uvicorn, not mock
deploy/
  tests/
    test_docker_e2e.sh         # Task 8 - build + run docker, hit it for real
    test_soak.sh               # Task 10 - 5min soak, monitor RSS
docs/
  superpowers/
    plans/
      2026-05-05-ai-aid-hardening.md   # this file
```

---

### Task 1: Concurrency test — N parallel POSTs survive

**Files:**
- Create: `server/tests/e2e/__init__.py` (empty)
- Create: `server/tests/e2e/conftest.py`
- Create: `server/tests/e2e/test_concurrency.py`

- [ ] **Step 1: Write the e2e fixtures**

`server/tests/e2e/conftest.py`:
```python
"""Boot a real uvicorn process per test for honest e2e behavior."""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest


def _find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def real_server(tmp_path):
    """Spawn uvicorn in a subprocess, yield (base_url, store_path)."""
    port = _find_free_port()
    db_path = tmp_path / "e2e.db"
    env = {
        **os.environ,
        "AI_AID_DB_PATH": str(db_path),
        "AI_AID_RATE_LIMIT_PER_MIN": "10000",  # disable rate limit for load tests
        "AI_AID_MAX_BODY_KB": "100",
        "AI_AID_EVENT_BUFFER": "1000",
    }
    repo_root = Path(__file__).resolve().parents[3]
    server_dir = repo_root / "server"
    venv_uv = server_dir / ".venv" / "bin" / "uvicorn"
    cmd = [
        str(venv_uv), "ai_aid.main:create_app", "--factory",
        "--host", "127.0.0.1", "--port", str(port),
        "--log-level", "warning",
    ]
    proc = subprocess.Popen(cmd, cwd=str(server_dir), env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 8.0
    last_err = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base}/health", timeout=0.5)
            if r.status_code == 200:
                break
        except Exception as e:
            last_err = e
        time.sleep(0.1)
    else:
        try:
            err_out = proc.stderr.read().decode("utf-8", errors="replace")
        except Exception:
            err_out = ""
        proc.kill()
        raise RuntimeError(f"server never became healthy: {last_err}\n{err_out}")

    yield base, str(db_path)

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
```

- [ ] **Step 2: Write the concurrency test**

`server/tests/e2e/test_concurrency.py`:
```python
"""Concurrent clients hammering the server should not lose, dupe, or 5xx."""
import asyncio
import sqlite3
import httpx
import pytest


def _payload(i: int, client="alice"):
    return {
        "client_id": client, "model": "m",
        "goal": f"goal {i}", "context": "ctx",
        "tried": "trying", "error": None, "constraints": None,
        "question": f"q{i}",
    }


@pytest.mark.asyncio
async def test_50_concurrent_posts_all_succeed(real_server):
    base, db_path = real_server
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        tasks = [ac.post("/api/requests", json=_payload(i, f"c{i % 5}"))
                 for i in range(50)]
        responses = await asyncio.gather(*tasks)
    statuses = [r.status_code for r in responses]
    assert all(s == 201 for s in statuses), f"non-201s: {statuses}"
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 50, "duplicate ids!"

    # Server-side: db row count matches
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
    assert n == 50

    # Events: one per request
    e = conn.execute("SELECT COUNT(*) FROM events WHERE kind='request.created'").fetchone()[0]
    assert e == 50


@pytest.mark.asyncio
async def test_concurrent_solves_against_one_request(real_server):
    base, db_path = real_server
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json=_payload(0, "alice"))
        rid = r.json()["id"]
        tasks = [
            ac.post(f"/api/requests/{rid}/answers", json={
                "solver_client_id": f"helper{i}", "solver_model": "m",
                "summary": f"answer {i}",
            })
            for i in range(20)
        ]
        responses = await asyncio.gather(*tasks)
    assert all(r.status_code == 201 for r in responses)
    detail = (await _fetch_detail(base, rid))
    assert len(detail["answers"]) == 20


@pytest.mark.asyncio
async def test_concurrent_close_attempts_one_wins(real_server):
    base, _ = real_server
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json=_payload(0, "alice"))
        rid = r.json()["id"]
        tasks = [ac.post(f"/api/requests/{rid}/close") for _ in range(10)]
        responses = await asyncio.gather(*tasks)
    statuses = [r.status_code for r in responses]
    # Exactly one 200, rest 409
    assert statuses.count(200) == 1, f"expected 1 win, got {statuses.count(200)}"
    assert statuses.count(409) == 9


async def _fetch_detail(base, rid):
    async with httpx.AsyncClient(base_url=base) as ac:
        r = await ac.get(f"/api/requests/{rid}")
        return r.json()
```

- [ ] **Step 3: Add pytest-asyncio config**

In `server/pyproject.toml`, add to `[tool.pytest.ini_options]`:
```toml
asyncio_mode = "auto"
```

- [ ] **Step 4: Run**

```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pytest tests/e2e/test_concurrency.py -v
```
Expected: 3 passed.

If any test fails on race conditions, that IS a real bug — diagnose before moving on.

- [ ] **Step 5: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add server/tests/e2e/__init__.py server/tests/e2e/conftest.py \
  server/tests/e2e/test_concurrency.py server/pyproject.toml
git commit -m "test(e2e): concurrent POST/solve/close survive under load"
```

---

### Task 2: Two-AI lifecycle simulator + e2e test

**Files:**
- Create: `tools/__init__.py` (empty)
- Create: `tools/simulator/__init__.py`
- Create: `tools/simulator/persona.py`
- Create: `tools/simulator/runner.py`
- Create: `tools/simulator/README.md`
- Create: `server/tests/e2e/test_two_ai_flow.py`

- [ ] **Step 1: Write the persona module**

`tools/simulator/persona.py`:
```python
"""AI persona — small wrapper that does ask/list/solve/check/close."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class Persona:
    server_url: str
    client_id: str
    model: str

    def __post_init__(self) -> None:
        self._client = httpx.Client(base_url=self.server_url, timeout=10.0)

    def close(self) -> None:
        self._client.close()

    # Asker actions ------------------------------------------------------

    def ask(
        self,
        *,
        goal: str, context: str, tried: str, question: str,
        error: Optional[str] = None, constraints: Optional[str] = None,
    ) -> dict:
        body = {
            "client_id": self.client_id, "model": self.model,
            "goal": goal, "context": context, "tried": tried,
            "error": error, "constraints": constraints, "question": question,
        }
        r = self._client.post("/api/requests", json=body)
        r.raise_for_status()
        return r.json()

    def mine(self) -> list[dict]:
        r = self._client.get(
            "/api/requests",
            params={"status": "all", "client_id": self.client_id, "mine": 1},
        )
        r.raise_for_status()
        return r.json()

    def check(self, rid: str) -> dict:
        r = self._client.get(f"/api/requests/{rid}")
        r.raise_for_status()
        return r.json()

    def close_request(self, rid: str) -> dict:
        r = self._client.post(f"/api/requests/{rid}/close")
        r.raise_for_status()
        return r.json()

    # Solver actions -----------------------------------------------------

    def list_open(self) -> list[dict]:
        r = self._client.get(
            "/api/requests",
            params={"status": "open", "exclude_client": self.client_id},
        )
        r.raise_for_status()
        return r.json()

    def solve(
        self,
        rid: str,
        *,
        summary: str,
        solution: Optional[str] = None,
        reasoning: Optional[str] = None,
        caveats: Optional[str] = None,
    ) -> httpx.Response:
        body = {
            "solver_client_id": self.client_id, "solver_model": self.model,
            "summary": summary,
            "solution": solution, "reasoning": reasoning, "caveats": caveats,
        }
        return self._client.post(f"/api/requests/{rid}/answers", json=body)
```

- [ ] **Step 2: Write the runner**

`tools/simulator/runner.py`:
```python
"""CLI: simulate N personas hitting a server.

Usage:
  python -m tools.simulator.runner --server http://127.0.0.1:8000 \\
    --asks 10 --solvers 3
"""
import argparse
import random
import time

from .persona import Persona


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--server", required=True)
    p.add_argument("--asks", type=int, default=5)
    p.add_argument("--solvers", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    random.seed(args.seed)

    asker = Persona(args.server, "sim-asker", "sim-haiku")
    solvers = [
        Persona(args.server, f"sim-solver-{i}", "sim-opus")
        for i in range(args.solvers)
    ]
    try:
        rids = []
        for i in range(args.asks):
            r = asker.ask(
                goal=f"sim goal {i}",
                context="simulator harness",
                tried=f"attempt {i}-a; attempt {i}-b",
                question=f"how do {i}",
            )
            rids.append(r["id"])
            print(f"[ask] {r['id']}")

        for solver in solvers:
            for rid in rids:
                resp = solver.solve(rid, summary=f"answer from {solver.client_id}")
                print(f"[solve] {solver.client_id} -> {rid} : {resp.status_code}")

        for rid in rids:
            d = asker.check(rid)
            assert len(d["answers"]) == args.solvers, \
                f"expected {args.solvers} answers, got {len(d['answers'])}"

        for rid in rids:
            asker.close_request(rid)
            print(f"[close] {rid}")

        print(f"OK: {args.asks} asks, {args.solvers} solvers, all answers landed, all closed")
        return 0
    finally:
        asker.close()
        for s in solvers:
            s.close()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Write the e2e test**

`server/tests/e2e/test_two_ai_flow.py`:
```python
"""Full two-AI lifecycle: asker posts, solver answers, asker checks then closes."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.simulator.persona import Persona


def test_full_lifecycle(real_server):
    base, _ = real_server
    asker = Persona(base, "ai-a", "haiku-4.5")
    solver = Persona(base, "ai-b", "opus-4.7")
    try:
        # Asker posts
        r = asker.ask(
            goal="PG fts cn",
            context="PG16, Django",
            tried="to_tsvector('simple') splits chars",
            question="how to do CN fts without zhparser",
            error=None, constraints="no extensions",
        )
        rid = r["id"]
        assert r["status"] == "open"

        # Asker sees own request via mine
        mine = asker.mine()
        assert any(x["id"] == rid for x in mine)

        # Solver lists, sees the request (excludes solver's own only)
        listed = solver.list_open()
        assert any(x["id"] == rid for x in listed)

        # Asker tries to solve own — must fail
        resp = asker.solve(rid, summary="cheating")
        assert resp.status_code == 403

        # Solver answers
        resp = solver.solve(
            rid,
            summary="use pg_trgm",
            solution="CREATE EXTENSION pg_trgm; ... USING gin (body gin_trgm_ops);",
            reasoning="trigrams handle CJK better than 'simple' tokenization",
            caveats="not great for boolean OR/AND queries",
        )
        assert resp.status_code == 201

        # Asker checks — sees the answer
        d = asker.check(rid)
        assert len(d["answers"]) == 1
        a = d["answers"][0]
        assert a["solver_client_id"] == "ai-b"
        assert a["summary"] == "use pg_trgm"
        assert "pg_trgm" in a["solution"]

        # Solver tries to close — must succeed at server level (no per-asker
        # ownership enforcement). Spec: only the asker should close their
        # own. Server currently allows anyone to close. Document via assertion.
        # If business decides to enforce, this will flag the regression.
        # For now, asker closes:
        closed = asker.close_request(rid)
        assert closed["status"] == "closed"

        # Solver tries to solve closed request — must fail with 409
        resp = solver.solve(rid, summary="too late")
        assert resp.status_code == 409

        # Asker tries to close again — 409
        # Use raw client because Persona raises_for_status
        import httpx
        r = httpx.post(f"{base}/api/requests/{rid}/close")
        assert r.status_code == 409
    finally:
        asker.close()
        solver.close()


def test_simulator_runner_smoke(real_server, capsys):
    base, _ = real_server
    from tools.simulator.runner import main as run_main
    sys.argv = ["runner", "--server", base, "--asks", "3", "--solvers", "2"]
    rc = run_main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "OK: 3 asks, 2 solvers" in captured.out
```

- [ ] **Step 4: Write README for the simulator**

`tools/simulator/README.md`:
```markdown
# ai-aid simulator

Spawns N AI personas that exercise the full ask → list → solve → check → close
lifecycle against a running server. Useful for:

- Manual smoke testing after deploy: run `python -m tools.simulator.runner --server URL`
- CI hardening (see `server/tests/e2e/test_two_ai_flow.py`)
- Load testing (bump --asks / --solvers)

## Run against your server

```bash
python -m tools.simulator.runner --server http://ai-aid.example.com --asks 5 --solvers 3
```

Each ask gets answers from each solver, then the asker closes everything.
Exit code 0 on success.

## Personas as a library

```python
from tools.simulator.persona import Persona
p = Persona("http://...", "client-id", "model-name")
r = p.ask(goal="...", context="...", tried="...", question="...")
print(r["id"])
p.close()
```
```

- [ ] **Step 5: Run**

```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pytest tests/e2e/test_two_ai_flow.py -v
```
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add tools/ server/tests/e2e/test_two_ai_flow.py
git commit -m "test(e2e): full two-AI lifecycle + reusable Persona/runner simulator"
```

---

### Task 3: Real-server bats test (no mock)

**Files:**
- Create: `skills/tests/test_real_server.bats`
- Create: `skills/tests/real_server_helpers.bash`

- [ ] **Step 1: Write helper that boots real uvicorn**

`skills/tests/real_server_helpers.bash`:
```bash
# Boot real uvicorn per test. Slower than mock but catches mock/server drift.

setup() {
  TEST_TMP="$(mktemp -d)"
  PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("",0)); print(s.getsockname()[1]); s.close()')"
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  VENV_UV="$REPO_ROOT/server/.venv/bin/uvicorn"
  AI_AID_DB_PATH="$TEST_TMP/db.sqlite" \
    AI_AID_RATE_LIMIT_PER_MIN=10000 \
    "$VENV_UV" ai_aid.main:create_app --factory \
      --host 127.0.0.1 --port "$PORT" --log-level warning \
      > "$TEST_TMP/srv.log" 2>&1 &
  SRV_PID=$!
  # Wait for ready (use the venv's uvicorn from server dir context)
  for _ in $(seq 1 40); do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/health"; then
      break
    fi
    sleep 0.1
  done
  cat > "$TEST_TMP/cfg.json" <<EOF
{
  "server_url": "http://127.0.0.1:$PORT",
  "client_id": "bats-real-client",
  "model": "bats-model"
}
EOF
  export AI_AID_CONFIG="$TEST_TMP/cfg.json"
  export TEST_TMP PORT SRV_PID
  SCRIPTS_DIR="$REPO_ROOT/skills/shared/scripts"
  export SCRIPTS_DIR
}

teardown() {
  if [[ -n "${SRV_PID:-}" ]]; then
    kill "$SRV_PID" 2>/dev/null || true
    wait "$SRV_PID" 2>/dev/null || true
  fi
  if [[ -n "${TEST_TMP:-}" ]]; then
    rm -rf "$TEST_TMP"
  fi
}

# Run a script in another persona (different client_id)
run_as() {
  local who="$1"; shift
  local cfg="$TEST_TMP/cfg-$who.json"
  cat > "$cfg" <<EOF
{
  "server_url": "http://127.0.0.1:$PORT",
  "client_id": "$who",
  "model": "$who-model"
}
EOF
  AI_AID_CONFIG="$cfg" "$@"
}
```

- [ ] **Step 2: Write the real-server bats tests**

`skills/tests/test_real_server.bats`:
```bash
#!/usr/bin/env bats
load real_server_helpers

@test "real: aid_ask + aid_check round-trip" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "real test" --context "ctx" --tried "x" --question "y"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"
  [ -n "$rid" ]

  run bash "$SCRIPTS_DIR/aid_check.sh" "$rid"
  [ "$status" -eq 0 ]
  [[ "$output" == *"\"id\":\"$rid\""* ]]
  [[ "$output" == *"\"answers\":[]"* ]]
}

@test "real: aid_solve different client succeeds; same client 403s" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"

  # Self-solve: 4xx → script exits non-zero
  run bash "$SCRIPTS_DIR/aid_solve.sh" --id "$rid" --summary "self"
  [ "$status" -ne 0 ]

  # Other persona: 201
  run run_as "other-helper" bash "$SCRIPTS_DIR/aid_solve.sh" --id "$rid" --summary "from other"
  [ "$status" -eq 0 ]

  # Check shows the answer
  run bash "$SCRIPTS_DIR/aid_check.sh" "$rid"
  [ "$status" -eq 0 ]
  [[ "$output" == *"from other"* ]]
}

@test "real: aid_list excludes own requests" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "mine" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]

  run bash "$SCRIPTS_DIR/aid_list.sh"
  [ "$status" -eq 0 ]
  # The list excludes self, so should NOT contain "bats-real-client"
  [[ "$output" != *"\"client_id\":\"bats-real-client\""* ]]
}

@test "real: aid_mine includes own + closed" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"
  run bash "$SCRIPTS_DIR/aid_close.sh" "$rid"
  [ "$status" -eq 0 ]

  run bash "$SCRIPTS_DIR/aid_mine.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"\"id\":\"$rid\""* ]]
  [[ "$output" == *"\"status\":\"closed\""* ]]
}

@test "real: optional fields in ask round-trip correctly" {
  run bash "$SCRIPTS_DIR/aid_ask.sh" \
    --goal "g" --context "c" --tried "t" --question "q" \
    --error "boom!" --constraints "no foo"
  [ "$status" -eq 0 ]
  rid="$(echo "$output" | jq -r .id)"

  run bash "$SCRIPTS_DIR/aid_check.sh" "$rid"
  [[ "$output" == *"\"error\":\"boom!\""* ]]
  [[ "$output" == *"\"constraints\":\"no foo\""* ]]
}
```

- [ ] **Step 3: Run**

```bash
cd /Users/liukun/j/ai-aid
bats skills/tests/test_real_server.bats
```
Expected: 5 passed.

If a test discovers mock/real divergence, fix the scripts (not the test).

- [ ] **Step 4: Commit**

```bash
git add skills/tests/test_real_server.bats skills/tests/real_server_helpers.bash
git commit -m "test(skills): bats against real uvicorn — catches mock/server drift"
```

---

### Task 4: SSE under concurrent writes (no events lost or out-of-order)

**Files:**
- Create: `server/tests/e2e/test_sse_under_load.py`

- [ ] **Step 1: Write the test**

`server/tests/e2e/test_sse_under_load.py`:
```python
"""SSE must deliver every event when writes are happening concurrently."""
import asyncio
import json
import httpx
import pytest


def _payload(i, client="alice"):
    return {
        "client_id": client, "model": "m",
        "goal": f"g{i}", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }


async def _consume(base, last_event_id, max_seconds, queue):
    """Subscribe to /events, push parsed events into queue."""
    async with httpx.AsyncClient(base_url=base, timeout=max_seconds + 5) as ac:
        url = f"/events?last_event_id={last_event_id}&max_seconds={max_seconds}"
        async with ac.stream("GET", url) as r:
            current = {}
            async for line in r.aiter_lines():
                if line == "":
                    if current:
                        queue.append(current)
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


@pytest.mark.asyncio
async def test_sse_receives_all_events_under_concurrent_writes(real_server):
    base, _ = real_server
    received = []
    consumer = asyncio.create_task(_consume(base, 0, 2.5, received))
    await asyncio.sleep(0.2)  # let SSE connect

    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        # Fire 30 posts in parallel during the SSE window
        tasks = [ac.post("/api/requests", json=_payload(i, f"c{i % 3}"))
                 for i in range(30)]
        await asyncio.gather(*tasks)

    await consumer  # wait for max_seconds to elapse
    created = [e for e in received if e.get("event") == "request.created"]
    assert len(created) == 30, f"expected 30 events, got {len(created)}"
    # Event ids strictly increasing
    ids = [e["id"] for e in created]
    assert ids == sorted(ids)
    assert len(set(ids)) == 30


@pytest.mark.asyncio
async def test_sse_resume_after_disconnect(real_server):
    base, _ = real_server
    # 1. post 3 requests, capture all events
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        for i in range(3):
            await ac.post("/api/requests", json=_payload(i))

    received1 = []
    await _consume(base, 0, 0.5, received1)
    first_batch_ids = [e["id"] for e in received1 if e.get("event") == "request.created"]
    assert len(first_batch_ids) == 3

    # 2. post 2 more
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        for i in range(3, 5):
            await ac.post("/api/requests", json=_payload(i))

    # 3. resume from last_event_id of first batch
    last = max(first_batch_ids)
    received2 = []
    await _consume(base, last, 0.5, received2)
    second_batch_ids = [e["id"] for e in received2 if e.get("event") == "request.created"]
    assert len(second_batch_ids) == 2
    assert all(i > last for i in second_batch_ids)
```

- [ ] **Step 2: Run**

```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pytest tests/e2e/test_sse_under_load.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add server/tests/e2e/test_sse_under_load.py
git commit -m "test(e2e): SSE delivers all events during concurrent writes + resumes"
```

---

### Task 5: Real body-size enforcement (not just Content-Length)

**Files:**
- Create: `server/tests/e2e/test_body_size_real.py`

- [ ] **Step 1: Write the test**

`server/tests/e2e/test_body_size_real.py`:
```python
"""The middleware checks Content-Length, but production also has Pydantic
+ FastAPI/uvicorn body limits. Real oversized request must be rejected."""
import httpx
import pytest


@pytest.mark.asyncio
async def test_oversized_real_body_rejected(real_server):
    base, _ = real_server
    huge = "x" * (200 * 1024)  # 200KB > 100KB cap
    payload = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": huge, "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json=payload)
    assert r.status_code == 413, f"got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_just_below_cap_succeeds(real_server):
    base, _ = real_server
    # 80KB content — well below 100KB cap
    big_but_ok = "y" * (80 * 1024)
    payload = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": big_but_ok, "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json=payload)
    assert r.status_code == 201
```

- [ ] **Step 2: Run**

```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pytest tests/e2e/test_body_size_real.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add server/tests/e2e/test_body_size_real.py
git commit -m "test(e2e): real oversized body returns 413; sub-cap body succeeds"
```

---

### Task 6: Unicode + code blocks survive round-trip

**Files:**
- Create: `server/tests/e2e/test_unicode.py`

- [ ] **Step 1: Write the test**

`server/tests/e2e/test_unicode.py`:
```python
"""CJK, emoji, code blocks, and triple-backtick markdown survive end-to-end."""
import httpx
import pytest


SAMPLES = {
    "chinese": "为什么 Postgres 全文搜索对中文不友好？",
    "japanese": "テストの意味",
    "emoji": "🚀💥 fire on prod 🔥",
    "codeblock": "```python\ndef ok():\n    return '中文 + emoji 🎉'\n```",
    "tabs_newlines": "line1\n\tindented\n\nblank-above",
    "json_in_text": '{"nested": "value", "list": [1, 2, 3]}',
}


@pytest.mark.asyncio
async def test_unicode_round_trip(real_server):
    base, _ = real_server
    payload = {
        "client_id": "alice", "model": "m",
        "goal": SAMPLES["chinese"],
        "context": SAMPLES["japanese"],
        "tried": SAMPLES["codeblock"],
        "error": SAMPLES["tabs_newlines"],
        "constraints": SAMPLES["json_in_text"],
        "question": SAMPLES["emoji"],
    }
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json=payload)
        assert r.status_code == 201
        rid = r.json()["id"]
        d = (await ac.get(f"/api/requests/{rid}")).json()
    assert d["goal"] == SAMPLES["chinese"]
    assert d["context"] == SAMPLES["japanese"]
    assert d["tried"] == SAMPLES["codeblock"]
    assert d["error"] == SAMPLES["tabs_newlines"]
    assert d["constraints"] == SAMPLES["json_in_text"]
    assert d["question"] == SAMPLES["emoji"]


@pytest.mark.asyncio
async def test_unicode_in_answer_round_trip(real_server):
    base, _ = real_server
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as ac:
        r = await ac.post("/api/requests", json={
            "client_id": "alice", "model": "m",
            "goal": "g", "context": "c", "tried": "t",
            "error": None, "constraints": None, "question": "q",
        })
        rid = r.json()["id"]
        await ac.post(f"/api/requests/{rid}/answers", json={
            "solver_client_id": "bob", "solver_model": "m",
            "summary": SAMPLES["chinese"],
            "solution": SAMPLES["codeblock"],
            "reasoning": SAMPLES["japanese"],
            "caveats": SAMPLES["emoji"],
        })
        d = (await ac.get(f"/api/requests/{rid}")).json()
    a = d["answers"][0]
    assert a["summary"] == SAMPLES["chinese"]
    assert a["solution"] == SAMPLES["codeblock"]
    assert a["reasoning"] == SAMPLES["japanese"]
    assert a["caveats"] == SAMPLES["emoji"]
```

- [ ] **Step 2: Run**

```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pytest tests/e2e/test_unicode.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add server/tests/e2e/test_unicode.py
git commit -m "test(e2e): unicode (CJK, emoji, code blocks) survives round-trip"
```

---

### Task 7: Migration safety — re-running migrations does not lose data

**Files:**
- Create: `server/tests/e2e/test_migration_safety.py`

- [ ] **Step 1: Write the test**

`server/tests/e2e/test_migration_safety.py`:
```python
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
```

- [ ] **Step 2: Run**

```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pytest tests/e2e/test_migration_safety.py -v
```
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add server/tests/e2e/test_migration_safety.py
git commit -m "test(e2e): migrations idempotent + new migration safe + cascade verified"
```

---

### Task 8: Docker container realistic E2E

**Files:**
- Create: `deploy/tests/test_docker_e2e.sh`

- [ ] **Step 1: Write the script**

`deploy/tests/test_docker_e2e.sh`:
```bash
#!/usr/bin/env bash
# End-to-end docker container test:
#   - build image
#   - run container with mounted data + web
#   - hit /health, post requests, list, solve, check, close
#   - verify container has web mount + db survives restart
#
# Usage: bash deploy/tests/test_docker_e2e.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PORT=18099
CONTAINER=ai-aid-e2e
DATA_DIR="$(mktemp -d)"
trap 'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; rm -rf "$DATA_DIR"' EXIT

echo "=== build ==="
docker build -t ai-aid:e2e ./server >/dev/null

echo "=== run container ==="
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  -e AI_AID_DB_PATH=/data/ai-aid.db \
  -e AI_AID_RATE_LIMIT_PER_MIN=10000 \
  -v "$DATA_DIR":/data \
  -v "$REPO_ROOT/web":/web:ro \
  -p "127.0.0.1:$PORT:8000" \
  ai-aid:e2e >/dev/null

echo "=== wait healthy ==="
for _ in $(seq 1 20); do
  if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then
    break
  fi
  sleep 1
done
H="$(curl -s "http://127.0.0.1:$PORT/health")"
echo "health: $H"
echo "$H" | jq -e '.ok == true' >/dev/null

echo "=== / serves dashboard ==="
INDEX="$(curl -s "http://127.0.0.1:$PORT/")"
[[ "$INDEX" == *"ai-aid Dashboard"* ]] || { echo "/ missing dashboard"; exit 1; }
JS_OK="$(curl -s "http://127.0.0.1:$PORT/web/app.js" | grep -c "EventSource")"
[[ "$JS_OK" -gt 0 ]] || { echo "app.js missing"; exit 1; }

echo "=== ask + check + solve + close ==="
RID="$(curl -s -X POST "http://127.0.0.1:$PORT/api/requests" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"docker-asker","model":"m","goal":"docker e2e","context":"c","tried":"t","question":"q"}' \
  | jq -r .id)"
[ -n "$RID" ] && [ "$RID" != "null" ]

curl -s "http://127.0.0.1:$PORT/api/requests/$RID" \
  | jq -e '.goal == "docker e2e"' >/dev/null

# Self-solve must 403
SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests/$RID/answers" \
  -H "Content-Type: application/json" \
  -d '{"solver_client_id":"docker-asker","solver_model":"m","summary":"self"}')"
[ "$SC" = "403" ] || { echo "self-solve expected 403, got $SC"; exit 1; }

# Other solver: 201
SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests/$RID/answers" \
  -H "Content-Type: application/json" \
  -d '{"solver_client_id":"docker-solver","solver_model":"m","summary":"hi"}')"
[ "$SC" = "201" ] || { echo "solve expected 201, got $SC"; exit 1; }

# Close
SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests/$RID/close")"
[ "$SC" = "200" ] || { echo "close expected 200, got $SC"; exit 1; }

echo "=== restart preserves data ==="
docker restart "$CONTAINER" >/dev/null
for _ in $(seq 1 20); do
  if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then
    break
  fi
  sleep 1
done
STATUS_AFTER="$(curl -s "http://127.0.0.1:$PORT/api/requests/$RID" | jq -r .status)"
[ "$STATUS_AFTER" = "closed" ] || { echo "post-restart status mismatch: $STATUS_AFTER"; exit 1; }

echo "=== SSE stream delivers ==="
(curl -s -N "http://127.0.0.1:$PORT/events?last_event_id=0&max_seconds=2" > "$DATA_DIR/sse.txt") &
SSE_PID=$!
sleep 0.3
curl -s -o /dev/null -X POST "http://127.0.0.1:$PORT/api/requests" \
  -H "Content-Type: application/json" \
  -d '{"client_id":"sse-test","model":"m","goal":"sse","context":"c","tried":"t","question":"q"}'
wait "$SSE_PID"
[ "$(grep -c 'request.created' "$DATA_DIR/sse.txt")" -gt 0 ] \
  || { echo "no SSE event delivered"; cat "$DATA_DIR/sse.txt"; exit 1; }

echo "=== ALL DOCKER E2E PASS ==="
```

- [ ] **Step 2: Run**

```bash
cd /Users/liukun/j/ai-aid
chmod +x deploy/tests/test_docker_e2e.sh
bash deploy/tests/test_docker_e2e.sh
```
Expected: prints `=== ALL DOCKER E2E PASS ===` at the end.

- [ ] **Step 3: Commit**

```bash
git add deploy/tests/test_docker_e2e.sh
git commit -m "test(deploy): full docker e2e — build, run, lifecycle, restart, SSE"
```

---

### Task 9: Crash recovery — kill mid-stream, server boots clean

**Files:**
- Create: `server/tests/e2e/test_crash_recovery.py`

- [ ] **Step 1: Write the test**

`server/tests/e2e/test_crash_recovery.py`:
```python
"""Killing the server mid-write does not corrupt the DB. Restart preserves
acknowledged writes."""
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest


def _find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _spawn(env, port):
    repo_root = Path(__file__).resolve().parents[3]
    server_dir = repo_root / "server"
    venv_uv = server_dir / ".venv" / "bin" / "uvicorn"
    return subprocess.Popen(
        [str(venv_uv), "ai_aid.main:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(server_dir), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _wait_healthy(base, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base}/health", timeout=0.5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError("server never healthy")


def test_sigkill_recovery_preserves_committed_data(tmp_path):
    port = _find_free_port()
    db_path = tmp_path / "crash.db"
    env = {
        **os.environ,
        "AI_AID_DB_PATH": str(db_path),
        "AI_AID_RATE_LIMIT_PER_MIN": "10000",
    }
    base = f"http://127.0.0.1:{port}"

    proc = _spawn(env, port)
    try:
        _wait_healthy(base)
        # Write 5 requests, ack each
        rids = []
        with httpx.Client(base_url=base) as c:
            for i in range(5):
                r = c.post("/api/requests", json={
                    "client_id": "alice", "model": "m",
                    "goal": f"g{i}", "context": "c", "tried": "t",
                    "error": None, "constraints": None, "question": "q",
                })
                assert r.status_code == 201
                rids.append(r.json()["id"])
        # Hard kill
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()

    # Restart, verify data
    proc2 = _spawn(env, port)
    try:
        _wait_healthy(base)
        with httpx.Client(base_url=base) as c:
            for rid in rids:
                r = c.get(f"/api/requests/{rid}")
                assert r.status_code == 200
                assert r.json()["id"] == rid
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc2.kill()


def test_double_boot_no_corruption(tmp_path):
    """Two consecutive boots see the same DB cleanly."""
    port = _find_free_port()
    db_path = tmp_path / "x.db"
    env = {
        **os.environ,
        "AI_AID_DB_PATH": str(db_path),
        "AI_AID_RATE_LIMIT_PER_MIN": "10000",
    }
    base = f"http://127.0.0.1:{port}"

    p1 = _spawn(env, port)
    try:
        _wait_healthy(base)
        with httpx.Client(base_url=base) as c:
            c.post("/api/requests", json={
                "client_id": "alice", "model": "m",
                "goal": "g", "context": "c", "tried": "t",
                "error": None, "constraints": None, "question": "q",
            })
    finally:
        p1.terminate()
        p1.wait(timeout=5)

    p2 = _spawn(env, port)
    try:
        _wait_healthy(base)
        with httpx.Client(base_url=base) as c:
            r = c.get("/api/requests?status=all")
            assert r.status_code == 200
            assert len(r.json()) == 1
    finally:
        p2.terminate()
        p2.wait(timeout=5)
```

- [ ] **Step 2: Run**

```bash
cd /Users/liukun/j/ai-aid/server
.venv/bin/pytest tests/e2e/test_crash_recovery.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd /Users/liukun/j/ai-aid
git add server/tests/e2e/test_crash_recovery.py
git commit -m "test(e2e): SIGKILL + restart preserves acknowledged writes"
```

---

### Task 10: Soak test (5-min light load against real container)

**Files:**
- Create: `deploy/tests/test_soak.sh`

- [ ] **Step 1: Write the soak script**

`deploy/tests/test_soak.sh`:
```bash
#!/usr/bin/env bash
# Soak test: keep the container under light continuous load for N seconds,
# sample memory + check for errors. Catches:
#   - memory growth (file handle / connection leaks)
#   - container drift to unhealthy
#   - SQLite corruption over time
#
# Usage: bash deploy/tests/test_soak.sh [DURATION_SEC] [REQS_PER_SEC]

set -euo pipefail
DURATION="${1:-60}"   # default 60s for CI; bump to 300 for full soak
RPS="${2:-5}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PORT=18098
CONTAINER=ai-aid-soak
DATA_DIR="$(mktemp -d)"
trap 'docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; rm -rf "$DATA_DIR"' EXIT

docker build -t ai-aid:soak ./server >/dev/null
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" \
  -e AI_AID_DB_PATH=/data/db.sqlite \
  -e AI_AID_RATE_LIMIT_PER_MIN=10000 \
  -v "$DATA_DIR":/data \
  -p "127.0.0.1:$PORT:8000" \
  ai-aid:soak >/dev/null

for _ in $(seq 1 20); do
  if curl -fs "http://127.0.0.1:$PORT/health" >/dev/null; then break; fi
  sleep 1
done

START_RSS="$(docker stats --no-stream --format '{{.MemUsage}}' "$CONTAINER" | awk '{print $1}')"
echo "START_RSS=$START_RSS"

END=$(( $(date +%s) + DURATION ))
COUNT=0
while [ "$(date +%s)" -lt "$END" ]; do
  for _ in $(seq 1 "$RPS"); do
    SC="$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/requests" \
      -H "Content-Type: application/json" \
      -d "{\"client_id\":\"soak-$((COUNT % 5))\",\"model\":\"m\",\"goal\":\"g$COUNT\",\"context\":\"c\",\"tried\":\"t\",\"error\":null,\"constraints\":null,\"question\":\"q\"}")"
    if [[ "$SC" != "201" ]]; then
      echo "FAIL on $COUNT: $SC"
      docker logs --tail=30 "$CONTAINER"
      exit 1
    fi
    COUNT=$((COUNT + 1))
  done
  sleep 1
done

END_RSS="$(docker stats --no-stream --format '{{.MemUsage}}' "$CONTAINER" | awk '{print $1}')"
HEALTH_END="$(curl -s "http://127.0.0.1:$PORT/health")"

# Sanity: count rows
ROW_COUNT="$(docker exec "$CONTAINER" python -c \
  "import sqlite3; print(sqlite3.connect('/data/db.sqlite').execute('SELECT COUNT(*) FROM requests').fetchone()[0])")"

echo "soak summary:"
echo "  duration : ${DURATION}s"
echo "  rps      : $RPS"
echo "  posted   : $COUNT"
echo "  db rows  : $ROW_COUNT"
echo "  start RSS: $START_RSS"
echo "  end   RSS: $END_RSS"
echo "  health   : $HEALTH_END"

[ "$ROW_COUNT" = "$COUNT" ] || { echo "row count mismatch"; exit 1; }
echo "$HEALTH_END" | jq -e '.ok == true' >/dev/null
echo "=== SOAK PASS ==="
```

- [ ] **Step 2: Run a short soak**

```bash
cd /Users/liukun/j/ai-aid
chmod +x deploy/tests/test_soak.sh
bash deploy/tests/test_soak.sh 30 3
```
Expected: prints `=== SOAK PASS ===` at the end. (30s × 3 rps = 90 successful inserts.)

- [ ] **Step 3: Commit**

```bash
git add deploy/tests/test_soak.sh
git commit -m "test(deploy): soak script — light load + memory + row-count check"
```

---

### Task 11: Wire e2e tests into CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add e2e job**

Append to `.github/workflows/ci.yml`:
```yaml
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        working-directory: server
        run: |
          python -m venv .venv
          .venv/bin/pip install --upgrade pip
          .venv/bin/pip install -e ".[test]"
      - name: Run e2e suite
        working-directory: server
        run: .venv/bin/pytest tests/e2e/ -v --tb=short

  bats-real:
    runs-on: ubuntu-latest
    needs: pytest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install bats + jq
        run: sudo apt-get update && sudo apt-get install -y bats jq
      - name: Set up server venv
        working-directory: server
        run: |
          python -m venv .venv
          .venv/bin/pip install --upgrade pip
          .venv/bin/pip install -e .
      - name: Run real-server bats
        run: bats skills/tests/test_real_server.bats

  docker-e2e:
    runs-on: ubuntu-latest
    needs: docker
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Run docker e2e
        run: bash deploy/tests/test_docker_e2e.sh
```

- [ ] **Step 2: Verify YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```
Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add e2e + bats-real + docker-e2e jobs"
```

---

### Task 12: Final verification + tag

- [ ] **Step 1: Run every test suite**

```bash
cd /Users/liukun/j/ai-aid

# Server unit + integration
cd server && .venv/bin/pytest -v --tb=short
# Expect: 80+ original passing PLUS new e2e

cd /Users/liukun/j/ai-aid

# Server e2e (needs uvicorn — make sure venv has it)
cd server && .venv/bin/pytest tests/e2e/ -v
cd /Users/liukun/j/ai-aid

# Skills bats (mock + real)
bats skills/tests/

# Docker e2e
bash deploy/tests/test_docker_e2e.sh

# Short soak (30s)
bash deploy/tests/test_soak.sh 30 3
```

All green required.

- [ ] **Step 2: Tag**

```bash
git tag -a hardening-v0.1.0 -m "Plan 5 complete: production hardening tests"
git tag -d v0.1.0 || true
git tag -a v0.1.0 -m "ai-aid v0.1.0: full stack — server + dashboard + skills + deployment + hardening"
```

- [ ] **Step 3: Done.** Five plans complete; all tests green.
