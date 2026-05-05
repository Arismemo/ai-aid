def test_validation_error_uses_unified_shape(client):
    r = client.post("/api/requests", json={"client_id": "x"})  # missing many fields
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "bad_request"
    assert "message" in body
    assert "fields" in body  # list of offending field paths


def test_404_shape(client):
    r = client.get("/api/requests/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not_found"
    assert "message" in body


def test_403_self_solve_shape(client):
    r = client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    rid = r.json()["id"]
    r2 = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "alice", "solver_model": "m", "summary": "s",
    })
    body = r2.json()
    assert r2.status_code == 403
    assert body["error"] == "forbidden"
    assert body["request_id"] == rid
