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
