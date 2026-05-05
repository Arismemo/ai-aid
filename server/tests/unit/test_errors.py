from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_aid.errors import (
    AidError, conflict, forbidden, not_found, payload_too_large,
    rate_limited, register_handlers,
)


def _make_app():
    app = FastAPI()
    register_handlers(app)

    @app.get("/raise/{kind}")
    def raise_handler(kind: str):
        if kind == "404":
            raise not_found("missing thing")
        if kind == "403":
            raise forbidden("cannot solve own request", request_id="r1")
        if kind == "409":
            raise conflict("request not open", status="closed")
        if kind == "413":
            raise payload_too_large(150)
        if kind == "429":
            raise rate_limited(client_id="alice", limit=30)
        return {"ok": True}

    return app


def test_not_found_returns_404_with_shape():
    client = TestClient(_make_app())
    r = client.get("/raise/404")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "not_found"
    assert "missing thing" in body["message"]


def test_forbidden_includes_extra_fields():
    client = TestClient(_make_app())
    r = client.get("/raise/403")
    assert r.status_code == 403
    body = r.json()
    assert body["error"] == "forbidden"
    assert body["request_id"] == "r1"


def test_conflict_includes_status():
    client = TestClient(_make_app())
    r = client.get("/raise/409")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "conflict"
    assert body["status"] == "closed"


def test_payload_too_large():
    client = TestClient(_make_app())
    r = client.get("/raise/413")
    assert r.status_code == 413
    body = r.json()
    assert body["error"] == "payload_too_large"


def test_rate_limited_includes_limit_and_client():
    client = TestClient(_make_app())
    r = client.get("/raise/429")
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "rate_limited"
    assert body["client_id"] == "alice"
    assert body["limit"] == 30
