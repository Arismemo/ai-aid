def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def test_metrics_endpoint_returns_200_text_plain(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    ct = r.headers["content-type"]
    assert ct.startswith("text/plain")
    assert "version=0.0.4" in ct


def test_metrics_contains_all_four_metric_names(client):
    r = client.get("/metrics")
    body = r.text
    assert "ai_aid_requests_total" in body
    assert "ai_aid_answers_total" in body
    assert "ai_aid_events_buffered" in body
    assert "ai_aid_db_bytes" in body


def test_metrics_reflects_state(client):
    rr = client.post("/api/requests", json=_payload(client_id="alice"))
    rid = rr.json()["id"]
    client.post(
        f"/api/requests/{rid}/answers",
        json={"solver_client_id": "bob", "solver_model": "m", "summary": "s"},
    )
    r = client.get("/metrics")
    body = r.text
    assert 'ai_aid_requests_total{status="open"} 1' in body
    assert 'ai_aid_answers_total 1' in body
