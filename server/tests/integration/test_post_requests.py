def _payload(**overrides):
    base = {
        "client_id": "alice",
        "model": "haiku-4.5",
        "goal": "g",
        "context": "c",
        "tried": "t",
        "error": None,
        "constraints": None,
        "question": "q",
    }
    base.update(overrides)
    return base


def test_create_returns_201_with_id(client):
    r = client.post("/api/requests", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["status"] == "open"
    assert body["created_at"] > 0


def test_missing_required_field_returns_400(client):
    payload = _payload()
    del payload["goal"]
    r = client.post("/api/requests", json=payload)
    assert r.status_code == 400 or r.status_code == 422


def test_blank_required_field_returns_validation_error(client):
    r = client.post("/api/requests", json=_payload(question="   "))
    assert r.status_code == 400 or r.status_code == 422


def test_optional_fields_can_be_omitted(client):
    payload = _payload()
    del payload["error"]
    del payload["constraints"]
    r = client.post("/api/requests", json=payload)
    assert r.status_code == 201


def test_rate_limit_blocks_after_n(client, monkeypatch):
    # The fixture sets limit=30, so 31st should fail
    last_status = None
    for i in range(31):
        r = client.post("/api/requests", json=_payload())
        last_status = r.status_code
    assert last_status == 429
    body = r.json()
    assert body["error"] == "rate_limited"
