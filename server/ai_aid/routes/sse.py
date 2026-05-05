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

    if initial_last_id > 0:
        min_id = store.min_event_id()
        if min_id > 0 and initial_last_id < min_id - 1:
            yield _sse_frame(
                event="replay-gap",
                data={"requested": initial_last_id, "available_from": min_id},
            )

    last_id = initial_last_id
    started = time.monotonic()
    while True:
        if await request.is_disconnected():
            return
        rows = store.list_events_after(last_id, limit=100)
        for row in rows:
            yield _sse_frame(event=row["kind"], data=row["payload"], event_id=row["id"])
            last_id = row["id"]
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
