import json
import re


def _read_sse_events(response):
    """Parse SSE wire format, return list of dicts with id/event/data keys."""
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
