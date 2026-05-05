def _post(client, client_id="alice"):
    r = client.post("/api/requests", json={
        "client_id": client_id, "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": "e", "constraints": "k", "question": "q",
    })
    return r.json()["id"]


def test_detail_returns_full_request(client):
    rid = _post(client)
    r = client.get(f"/api/requests/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == rid
    assert body["context"] == "c"
    assert body["error"] == "e"
    assert body["answers"] == []


def test_detail_includes_answers_in_order(client):
    rid = _post(client, "alice")
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "first",
    })
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "carol", "solver_model": "m", "summary": "second",
    })
    r = client.get(f"/api/requests/{rid}")
    body = r.json()
    assert [a["summary"] for a in body["answers"]] == ["first", "second"]


def test_detail_404_for_missing(client):
    r = client.get("/api/requests/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
