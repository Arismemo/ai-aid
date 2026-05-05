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


def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def test_subscribe_to_filters_other_clients_request_created(client):
    client.post("/api/requests", json=_payload(client_id="alice"))
    client.post("/api/requests", json=_payload(client_id="bob"))
    with client.stream(
        "GET", "/events?last_event_id=0&max_seconds=0&subscribe_to=alice"
    ) as r:
        events = _read_sse_events(r)
    kinds = [e.get("event") for e in events if e.get("event") == "request.created"]
    assert len(kinds) == 1


def test_subscribe_to_lets_through_answers_to_owned_requests(client):
    rr = client.post("/api/requests", json=_payload(client_id="alice"))
    rid = rr.json()["id"]
    client.post(
        f"/api/requests/{rid}/answers",
        json={"solver_client_id": "bob", "solver_model": "m", "summary": "s"},
    )
    with client.stream(
        "GET", "/events?last_event_id=0&max_seconds=0&subscribe_to=alice"
    ) as r:
        events = _read_sse_events(r)
    kinds = [e.get("event") for e in events if e.get("event")]
    assert "answer.created" in kinds


def test_subscribe_to_filters_unrelated_answers(client):
    rr_a = client.post("/api/requests", json=_payload(client_id="alice"))
    rr_c = client.post("/api/requests", json=_payload(client_id="carol"))
    rid_a = rr_a.json()["id"]
    rid_c = rr_c.json()["id"]
    # Bob answers both.
    client.post(
        f"/api/requests/{rid_a}/answers",
        json={"solver_client_id": "bob", "solver_model": "m", "summary": "for-alice"},
    )
    client.post(
        f"/api/requests/{rid_c}/answers",
        json={"solver_client_id": "bob", "solver_model": "m", "summary": "for-carol"},
    )
    with client.stream(
        "GET", "/events?last_event_id=0&max_seconds=0&subscribe_to=alice"
    ) as r:
        events = _read_sse_events(r)
    answer_events = [e for e in events if e.get("event") == "answer.created"]
    # Only alice's answer should pass through
    assert len(answer_events) == 1
    import json as _j
    data = _j.loads(answer_events[0]["data"])
    assert data["request_id"] == rid_a


def test_subscribe_to_filters_request_closed_for_other_client(client):
    rr = client.post("/api/requests", json=_payload(client_id="bob"))
    rid = rr.json()["id"]
    client.post(f"/api/requests/{rid}/close")
    with client.stream(
        "GET", "/events?last_event_id=0&max_seconds=0&subscribe_to=alice"
    ) as r:
        events = _read_sse_events(r)
    kinds = [e.get("event") for e in events if e.get("event")]
    assert "request.closed" not in kinds
    assert "request.created" not in kinds


def test_subscribe_to_passes_request_closed_for_owned(client):
    rr = client.post("/api/requests", json=_payload(client_id="alice"))
    rid = rr.json()["id"]
    client.post(f"/api/requests/{rid}/close")
    with client.stream(
        "GET", "/events?last_event_id=0&max_seconds=0&subscribe_to=alice"
    ) as r:
        events = _read_sse_events(r)
    kinds = [e.get("event") for e in events if e.get("event")]
    assert "request.closed" in kinds
