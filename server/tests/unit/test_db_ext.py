"""Unit tests for the new Store methods added in this iteration:
list_recent_activity, client_stats, prune_old_closed.
"""

import time

import pytest

from ai_aid import db
from migration_runner import apply_migrations


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "t.db"
    apply_migrations(str(path))
    return db.Store(str(path))


def _sample_request(client_id="alice"):
    return {
        "client_id": client_id, "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    }


# --- list_recent_activity --------------------------------------------------

def test_list_recent_activity_empty(store):
    assert store.list_recent_activity(50) == []


def test_list_recent_activity_returns_request_created(store):
    rid = store.create_request(_sample_request("alice"))
    store.append_event("request.created", {"id": rid, "client_id": "alice"})
    out = store.list_recent_activity(50)
    assert len(out) == 1
    assert out[0]["kind"] == "request.created"
    assert out[0]["request"]["id"] == rid


def test_list_recent_activity_returns_answer_created_with_request_meta(store):
    rid = store.create_request(_sample_request("alice"))
    aid = store.create_answer(rid, {
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
        "solution": None, "reasoning": None, "caveats": None,
    })
    store.append_event("answer.created", {
        "id": aid, "request_id": rid,
    })
    out = store.list_recent_activity(50)
    assert len(out) == 1
    entry = out[0]
    assert entry["kind"] == "answer.created"
    assert entry["answer"]["id"] == aid
    assert entry["request"]["id"] == rid
    assert entry["request"]["client_id"] == "alice"
    assert entry["request"]["goal"] == "g"


def test_list_recent_activity_clamps_limit_to_200(store):
    out = store.list_recent_activity(10_000)
    assert isinstance(out, list)


def test_list_recent_activity_skips_non_creation_events(store):
    rid = store.create_request(_sample_request("alice"))
    store.append_event("request.created", {"id": rid, "client_id": "alice"})
    store.append_event("request.closed", {"id": rid})
    store.append_event("request.deleted", {"id": rid})
    out = store.list_recent_activity(50)
    kinds = [e["kind"] for e in out]
    assert kinds == ["request.created"]


# --- client_stats ----------------------------------------------------------

def test_client_stats_empty(store):
    s = store.client_stats("ghost")
    assert s == {
        "client_id": "ghost",
        "asks_total": 0, "asks_open": 0, "asks_closed": 0,
        "answers_given": 0, "asks_received_answer": 0,
        "answer_accept_rate": None,
    }


def test_client_stats_full_picture(store):
    a = store.create_request(_sample_request("alice"))
    b = store.create_request(_sample_request("alice"))
    store.create_request(_sample_request("alice"))
    store.close_request(a)
    store.create_answer(b, {
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
        "solution": None, "reasoning": None, "caveats": None,
    })
    s = store.client_stats("alice")
    assert s["asks_total"] == 3
    assert s["asks_open"] == 2
    assert s["asks_closed"] == 1
    assert s["asks_received_answer"] == 1
    assert s["answer_accept_rate"] == 1 / 3


# --- prune_old_closed ------------------------------------------------------

def test_prune_old_closed_zero_days_noop(store):
    rid = store.create_request(_sample_request("alice"))
    store.close_request(rid)
    assert store.prune_old_closed(days=0) == 0
    assert store.get_request(rid) is not None


def test_prune_old_closed_recent_within_threshold(store):
    rid = store.create_request(_sample_request("alice"))
    store.close_request(rid)
    assert store.prune_old_closed(days=7) == 0
    assert store.get_request(rid) is not None


def test_prune_old_closed_removes_ancient(store):
    rid = store.create_request(_sample_request("alice"))
    store.close_request(rid)
    with store._conn() as c:
        old = int(time.time() * 1000) - 30 * 86_400_000
        c.execute("UPDATE requests SET closed_at = ? WHERE id = ?", (old, rid))
    deleted = store.prune_old_closed(days=7)
    assert deleted == 1
    assert store.get_request(rid) is None


def test_prune_old_closed_leaves_open_alone(store):
    rid = store.create_request(_sample_request("alice"))
    # Open request, no closed_at — must never be pruned.
    deleted = store.prune_old_closed(days=7)
    assert deleted == 0
    assert store.get_request(rid) is not None


def test_prune_cascades_answers(store):
    rid = store.create_request(_sample_request("alice"))
    store.create_answer(rid, {
        "solver_client_id": "bob", "solver_model": "m", "summary": "s",
        "solution": None, "reasoning": None, "caveats": None,
    })
    store.close_request(rid)
    with store._conn() as c:
        old = int(time.time() * 1000) - 30 * 86_400_000
        c.execute("UPDATE requests SET closed_at = ? WHERE id = ?", (old, rid))
    store.prune_old_closed(days=7)
    assert store.list_answers(rid) == []
