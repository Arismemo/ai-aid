def _payload(**overrides):
    base = {
        "client_id": "alice", "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }
    base.update(overrides)
    return base


def test_post_request_emits_request_created(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("request.created", rid) in kinds


def test_post_answer_emits_answer_created(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    a = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
    })
    aid = a.json()["id"]
    store = client.app.state.store
    rows = store.list_events_after(0, limit=20)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("answer.created", aid) in kinds


def test_close_emits_request_closed(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    client.post(f"/api/requests/{rid}/close")
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("request.closed", rid) in kinds


def test_delete_emits_request_deleted(client):
    r = client.post("/api/requests", json=_payload())
    rid = r.json()["id"]
    client.delete(f"/api/requests/{rid}")
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    assert ("request.deleted", rid) in kinds


def test_failed_self_solve_emits_no_event(client):
    r = client.post("/api/requests", json=_payload(client_id="alice"))
    rid = r.json()["id"]
    client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": "alice", "solver_model": "m", "summary": "s",
    })
    store = client.app.state.store
    rows = store.list_events_after(0, limit=10)
    kinds = [(row["kind"], row["payload"].get("id")) for row in rows]
    answer_events = [k for k in kinds if k[0] == "answer.created"]
    assert answer_events == []
