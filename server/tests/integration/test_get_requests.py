def _post(client, **overrides):
    base = {
        "client_id": "alice", "model": "haiku-4.5",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    r = client.post("/api/requests", json=base)
    assert r.status_code == 201
    return r.json()["id"]


def test_default_returns_open_only(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="bob")
    client.post(f"/api/requests/{a}/close")
    r = client.get("/api/requests")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert b in ids
    assert a not in ids


def test_status_all_returns_both(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="bob")
    client.post(f"/api/requests/{a}/close")
    r = client.get("/api/requests?status=all")
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert {a, b} <= ids


def test_exclude_client_filters_out(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="bob")
    r = client.get("/api/requests?exclude_client=alice")
    ids = {x["id"] for x in r.json()}
    assert b in ids
    assert a not in ids


def test_mine_returns_own_requests_in_all_statuses(client):
    a = _post(client, client_id="alice")
    b = _post(client, client_id="alice")
    _post(client, client_id="bob")
    client.post(f"/api/requests/{a}/close")
    r = client.get("/api/requests?status=all&client_id=alice&mine=1")
    ids = {x["id"] for x in r.json()}
    assert ids == {a, b}


def test_summary_includes_answer_count(client):
    a = _post(client, client_id="alice")
    client.post(f"/api/requests/{a}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    client.post(f"/api/requests/{a}/answers", json={
        "solver_client_id": "carol", "solver_model": "m", "summary": "s",
    })
    r = client.get("/api/requests?status=all")
    item = next(x for x in r.json() if x["id"] == a)
    assert item["answer_count"] == 2
