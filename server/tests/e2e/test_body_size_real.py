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
