import pytest

from ai_aid import db
from migration_runner import apply_migrations


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "t.db"
    apply_migrations(str(path))
    return db.Store(str(path))


def _sample_request(client_id="alice", model="haiku-4.5"):
    return {
        "client_id": client_id,
        "model": model,
        "goal": "g",
        "context": "c",
        "tried": "t",
        "error": None,
        "constraints": None,
        "question": "q",
    }


def test_create_request_returns_id_and_persists(store):
    rid = store.create_request(_sample_request())
    assert isinstance(rid, str) and len(rid) == 36
    row = store.get_request(rid)
    assert row["id"] == rid
    assert row["status"] == "open"
    assert row["created_at"] > 0
    assert row["closed_at"] is None


def test_get_request_returns_none_when_missing(store):
    assert store.get_request("nope") is None


def test_list_requests_filters_status_and_excludes_client(store):
    a = store.create_request(_sample_request("alice"))
    b = store.create_request(_sample_request("bob"))
    store.close_request(a)
    open_only = store.list_requests(status="open", exclude_client=None, only_client=None)
    assert {r["id"] for r in open_only} == {b}
    not_alice = store.list_requests(status="all", exclude_client="alice", only_client=None)
    assert {r["id"] for r in not_alice} == {b}
    only_alice = store.list_requests(status="all", exclude_client=None, only_client="alice")
    assert {r["id"] for r in only_alice} == {a}


def test_close_request_idempotency_signal(store):
    rid = store.create_request(_sample_request())
    assert store.close_request(rid) is True
    assert store.close_request(rid) is False  # already closed


def test_create_answer_and_list(store):
    rid = store.create_request(_sample_request("alice"))
    aid = store.create_answer(rid, {
        "solver_client_id": "bob",
        "solver_model": "opus-4.7",
        "summary": "s",
        "solution": None,
        "reasoning": None,
        "caveats": None,
    })
    answers = store.list_answers(rid)
    assert len(answers) == 1
    assert answers[0]["id"] == aid
    assert answers[0]["solver_client_id"] == "bob"


def test_delete_request_cascades_answers(store):
    rid = store.create_request(_sample_request("alice"))
    store.create_answer(rid, {
        "solver_client_id": "bob", "solver_model": "m",
        "summary": "s", "solution": None, "reasoning": None, "caveats": None,
    })
    assert store.delete_request(rid) is True
    assert store.get_request(rid) is None
    assert store.list_answers(rid) == []


def test_count_recent_requests_for_client(store):
    for _ in range(5):
        store.create_request(_sample_request("alice"))
    assert store.count_recent_requests("alice", window_ms=60_000) == 5
    assert store.count_recent_requests("bob", window_ms=60_000) == 0
