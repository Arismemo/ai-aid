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
