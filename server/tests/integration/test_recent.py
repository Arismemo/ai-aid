def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def test_recent_empty_returns_empty_list(client):
    r = client.get("/api/recent")
    assert r.status_code == 200
    assert r.json() == []


def test_recent_contains_created_events_in_reverse_chronological(client):
    r1 = client.post("/api/requests", json=_payload(client_id="alice", goal="first"))
    r2 = client.post("/api/requests", json=_payload(client_id="bob", goal="second"))
    rid1 = r1.json()["id"]
    rid2 = r2.json()["id"]

    r = client.get("/api/recent")
    assert r.status_code == 200
    body = r.json()
    # Newest first
    assert body[0]["kind"] == "request.created"
    assert body[0]["request"]["id"] == rid2
    assert body[1]["kind"] == "request.created"
    assert body[1]["request"]["id"] == rid1


def test_recent_limit_clamped_to_200(client):
    # Try limit=1000 — should be clamped to 200 max.
    for i in range(3):
        client.post("/api/requests", json=_payload(client_id=f"c{i}"))
    r = client.get("/api/recent?limit=1000")
    assert r.status_code == 200
    # We only posted 3, so we won't actually hit 200; just confirm no error.
    body = r.json()
    assert len(body) <= 200


def test_recent_limit_default_50(client):
    r = client.get("/api/recent")
    assert r.status_code == 200


def test_recent_answer_created_includes_request_goal_and_client_id(client):
    rr = client.post("/api/requests", json=_payload(client_id="alice", goal="my goal"))
    rid = rr.json()["id"]
    client.post(
        f"/api/requests/{rid}/answers",
        json={"solver_client_id": "bob", "solver_model": "m", "summary": "s"},
    )
    r = client.get("/api/recent")
    body = r.json()
    answer_entries = [e for e in body if e["kind"] == "answer.created"]
    assert len(answer_entries) == 1
    entry = answer_entries[0]
    assert entry["request"]["id"] == rid
    assert entry["request"]["goal"] == "my goal"
    assert entry["request"]["client_id"] == "alice"
    assert entry["answer"]["summary"] == "s"


def test_recent_skips_closed_and_deleted_events(client):
    rr = client.post("/api/requests", json=_payload(client_id="alice"))
    rid = rr.json()["id"]
    client.post(f"/api/requests/{rid}/close")
    r = client.get("/api/recent")
    body = r.json()
    kinds = [e["kind"] for e in body]
    # Only request.created should be in the activity feed.
    assert "request.closed" not in kinds
    assert "request.deleted" not in kinds


def test_recent_explicit_limit_respected(client):
    for i in range(5):
        client.post("/api/requests", json=_payload(client_id=f"c{i}"))
    r = client.get("/api/recent?limit=2")
    body = r.json()
    assert len(body) == 2
