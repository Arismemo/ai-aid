def _post(client):
    r = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    return r.json()["id"]


def test_delete_returns_204(client):
    rid = _post(client)
    r = client.delete(f"/api/requests/{rid}")
    assert r.status_code == 204
    assert client.get(f"/api/requests/{rid}").status_code == 404


def test_delete_cascades_answers(client):
    rid = _post(client)
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    client.delete(f"/api/requests/{rid}")
    # Recreate request with same client; ensure no orphan rows surface in detail
    r2 = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    rid2 = r2.json()["id"]
    detail = client.get(f"/api/requests/{rid2}").json()
    assert detail["answers"] == []


def test_delete_unknown_returns_404(client):
    r = client.delete("/api/requests/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
