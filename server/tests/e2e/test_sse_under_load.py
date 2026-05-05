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
