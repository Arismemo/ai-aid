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
