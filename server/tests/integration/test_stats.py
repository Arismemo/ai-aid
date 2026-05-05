def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def test_stats_missing_client_id_returns_400(client):
    r = client.get("/api/stats")
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "bad_request"


def test_stats_unknown_client_returns_zeros(client):
    r = client.get("/api/stats?client_id=ghost")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "client_id": "ghost",
        "asks_total": 0,
        "asks_open": 0,
        "asks_closed": 0,
        "answers_given": 0,
        "asks_received_answer": 0,
        "answer_accept_rate": None,
    }


def test_stats_after_activity_correct_numbers(client):
    # Alice posts 3 asks; closes 1 of them.
    rids = []
    for i in range(3):
        r = client.post("/api/requests", json=_payload(client_id="alice", goal=f"g{i}"))
        rids.append(r.json()["id"])
    client.post(f"/api/requests/{rids[0]}/close")
    # Bob answers two of Alice's asks (the one closed cannot be answered, so
    # answer the two remaining open ones).
    client.post(
        f"/api/requests/{rids[1]}/answers",
        json={"solver_client_id": "bob", "solver_model": "m", "summary": "s"},
    )
    client.post(
        f"/api/requests/{rids[2]}/answers",
        json={"solver_client_id": "bob", "solver_model": "m", "summary": "s"},
    )

    r = client.get("/api/stats?client_id=alice")
    body = r.json()
    assert body["client_id"] == "alice"
    assert body["asks_total"] == 3
    assert body["asks_open"] == 2
    assert body["asks_closed"] == 1
    assert body["answers_given"] == 0
    assert body["asks_received_answer"] == 2
    assert body["answer_accept_rate"] == 2 / 3

    # Bob: answered 2, asked 0
    r2 = client.get("/api/stats?client_id=bob")
    b2 = r2.json()
    assert b2["asks_total"] == 0
    assert b2["answers_given"] == 2
    assert b2["answer_accept_rate"] is None
