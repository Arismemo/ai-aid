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


def test_sse_no_replay_gap_when_cursor_in_range(client):
    store = client.app.state.store
    ids = [store.append_event("request.created", {"i": i}) for i in range(3)]
    with client.stream(
        "GET", f"/events?last_event_id={ids[1]}&max_seconds=0"
    ) as r:
        events = _read_sse_events(r)
    event_kinds = [e.get("event") for e in events if e.get("event")]
    assert "replay-gap" not in event_kinds
