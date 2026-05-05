def _post_request(client, client_id="alice"):
    r = client.post("/api/requests", json={
        "client_id": client_id, "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    return r.json()["id"]


def _ans(**overrides):
    base = {"solver_client_id": "bob", "solver_model": "m", "summary": "s"}
    base.update(overrides)
    return base


def test_create_answer_returns_201(client):
    rid = _post_request(client, "alice")
    r = client.post(f"/api/requests/{rid}/answers", json=_ans())
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["created_at"] > 0


def test_self_solve_returns_403(client):
    rid = _post_request(client, "alice")
    r = client.post(
        f"/api/requests/{rid}/answers",
        json=_ans(solver_client_id="alice"),
    )
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "forbidden"
    assert body["request_id"] == rid


def test_answer_on_unknown_request_returns_404(client):
    r = client.post(
        "/api/requests/00000000-0000-0000-0000-000000000000/answers",
        json=_ans(),
    )
    assert r.status_code == 404


def test_missing_summary_returns_validation_error(client):
    rid = _post_request(client, "alice")
    r = client.post(
        f"/api/requests/{rid}/answers",
        json={"solver_client_id": "bob", "solver_model": "m"},
    )
    assert r.status_code in (400, 422)


def test_blank_summary_rejected(client):
    rid = _post_request(client, "alice")
    r = client.post(
        f"/api/requests/{rid}/answers",
        json=_ans(summary="   "),
    )
    assert r.status_code in (400, 422)
