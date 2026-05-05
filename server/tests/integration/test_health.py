def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["db"] == "ok"
    assert body["events_buffered"] == 0


def test_oversized_body_rejected(client):
    huge = "x" * (101 * 1024)  # 101KB > 100KB cap
    r = client.post("/api/requests", json={"x": huge})
    assert r.status_code == 413
    body = r.json()
    assert body["error"] == "payload_too_large"


def test_app_boots(client):
    r = client.get("/this-does-not-exist")
    assert r.status_code == 404


def test_health_reports_buffered_count(client):
    client.post("/api/requests", json={
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    r = client.get("/health")
    body = r.json()
    assert body["events_buffered"] == 1
