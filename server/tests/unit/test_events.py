import pytest

from ai_aid import db, events
from migration_runner import apply_migrations


@pytest.fixture
def store(tmp_path):
    p = tmp_path / "t.db"
    apply_migrations(str(p))
    return db.Store(str(p))


def test_request_created_payload_shape():
    p = events.request_created({
        "id": "r1", "client_id": "alice", "model": "m",
        "goal": "g", "status": "open", "created_at": 1, "closed_at": None,
    }, answer_count=0)
    assert p["id"] == "r1"
    assert p["client_id"] == "alice"
    assert p["status"] == "open"
    assert p["answer_count"] == 0


def test_answer_created_payload_shape():
    p = events.answer_created("r1", {
        "id": "a1", "solver_client_id": "bob", "solver_model": "m",
        "summary": "s", "solution": None, "reasoning": None, "caveats": None,
        "created_at": 2,
    })
    assert p["request_id"] == "r1"
    assert p["id"] == "a1"
    assert p["solver_client_id"] == "bob"


def test_request_closed_payload_shape():
    p = events.request_closed("r1", closed_at=42)
    assert p == {"id": "r1", "status": "closed", "closed_at": 42}


def test_request_deleted_payload_shape():
    p = events.request_deleted("r1")
    assert p == {"id": "r1"}


def test_append_and_list_events_after(store):
    a = store.append_event("request.created", {"id": "r1"})
    b = store.append_event("answer.created", {"id": "a1"})
    rows = store.list_events_after(0, limit=10)
    assert [r["id"] for r in rows] == [a, b]
    assert rows[0]["kind"] == "request.created"
    rows_after_a = store.list_events_after(a, limit=10)
    assert [r["id"] for r in rows_after_a] == [b]


def test_trim_events_keeps_newest(store):
    ids = [store.append_event("request.created", {"i": i}) for i in range(5)]
    store.trim_events(keep=3)
    rows = store.list_events_after(0, limit=10)
    assert sorted(r["id"] for r in rows) == sorted(ids[-3:])


def test_count_events(store):
    store.append_event("request.created", {})
    store.append_event("answer.created", {})
    assert store.count_events() == 2


def test_max_event_id(store):
    assert store.max_event_id() == 0
    store.append_event("request.created", {})
    last = store.append_event("answer.created", {})
    assert store.max_event_id() == last
