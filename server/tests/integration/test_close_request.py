def _post(client):
    r = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    return r.json()["id"]


def test_close_open_returns_200(client):
    rid = _post(client)
    r = client.post(f"/api/requests/{rid}/close")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_close_already_closed_returns_409(client):
    rid = _post(client)
    client.post(f"/api/requests/{rid}/close")
    r = client.post(f"/api/requests/{rid}/close")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "conflict"
    assert body["status"] == "closed"


def test_close_unknown_returns_404(client):
    r = client.post("/api/requests/00000000-0000-0000-0000-000000000000/close")
    assert r.status_code == 404


def test_solve_after_close_returns_409(client):
    rid = _post(client)
    client.post(f"/api/requests/{rid}/close")
    r = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    assert r.status_code == 409
