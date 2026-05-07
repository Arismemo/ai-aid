"""Integration tests for the quality-signal feature: accept + upvote.

Covers /api/requests/{rid}/accept, /api/answers/{aid}/vote, and the
exposure of `accepted_answer_id`, per-answer `votes` + `accepted` flags
on existing read endpoints.
"""

import sqlite3
from pathlib import Path


def _post_request(client, client_id="alice"):
    r = client.post("/api/requests", json={
        "client_id": client_id, "model": "m",
        "goal": "g", "context": "c", "tried": "t",
        "error": None, "constraints": None, "question": "q",
    })
    assert r.status_code == 201
    return r.json()["id"]


def _post_answer(client, rid, solver_client_id="bob"):
    r = client.post(f"/api/requests/{rid}/answers", json={
        "solver_client_id": solver_client_id,
        "solver_model": "m",
        "summary": "s",
    })
    assert r.status_code == 201
    return r.json()["id"]


# ----- accept -----

def test_accept_by_asker_returns_200(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    r = client.post(f"/api/requests/{rid}/accept",
                    json={"answer_id": aid, "client_id": "alice"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == rid
    assert body["accepted_answer_id"] == aid


def test_accept_by_other_returns_403(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    r = client.post(f"/api/requests/{rid}/accept",
                    json={"answer_id": aid, "client_id": "carol"})
    assert r.status_code == 403


def test_accept_unknown_answer_returns_404(client):
    rid = _post_request(client, "alice")
    r = client.post(f"/api/requests/{rid}/accept",
                    json={"answer_id": "00000000-0000-0000-0000-000000000000",
                          "client_id": "alice"})
    assert r.status_code == 404


def test_accept_unknown_request_returns_404(client):
    rid_fake = "00000000-0000-0000-0000-000000000000"
    r = client.post(f"/api/requests/{rid_fake}/accept",
                    json={"answer_id": "anything", "client_id": "alice"})
    assert r.status_code == 404


def test_accept_answer_from_other_request_returns_404(client):
    r1 = _post_request(client, "alice")
    r2 = _post_request(client, "alice")
    aid_for_r2 = _post_answer(client, r2, "bob")
    r = client.post(f"/api/requests/{r1}/accept",
                    json={"answer_id": aid_for_r2, "client_id": "alice"})
    assert r.status_code == 404


def test_accept_idempotent_same_answer(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    r1 = client.post(f"/api/requests/{rid}/accept",
                     json={"answer_id": aid, "client_id": "alice"})
    r2 = client.post(f"/api/requests/{rid}/accept",
                     json={"answer_id": aid, "client_id": "alice"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["accepted_answer_id"] == aid


def test_accept_overwrites_previous_choice(client):
    rid = _post_request(client, "alice")
    aid1 = _post_answer(client, rid, "bob")
    aid2 = _post_answer(client, rid, "carol")
    client.post(f"/api/requests/{rid}/accept",
                json={"answer_id": aid1, "client_id": "alice"})
    r = client.post(f"/api/requests/{rid}/accept",
                    json={"answer_id": aid2, "client_id": "alice"})
    assert r.status_code == 200
    assert r.json()["accepted_answer_id"] == aid2

    detail = client.get(f"/api/requests/{rid}").json()
    assert detail["accepted_answer_id"] == aid2
    by_id = {a["id"]: a for a in detail["answers"]}
    assert by_id[aid2]["accepted"] is True
    assert by_id[aid1]["accepted"] is False


# ----- vote toggle -----

def test_vote_toggles_insert_then_delete(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    r1 = client.post(f"/api/answers/{aid}/vote", json={"voter": "carol"})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["answer_id"] == aid
    assert body1["votes"] == 1
    assert body1["voted"] is True

    r2 = client.post(f"/api/answers/{aid}/vote", json={"voter": "carol"})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["votes"] == 0
    assert body2["voted"] is False


def test_vote_unknown_answer_returns_404(client):
    r = client.post("/api/answers/00000000-0000-0000-0000-000000000000/vote",
                    json={"voter": "carol"})
    assert r.status_code == 404


def test_vote_count_visible_in_request_detail(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    client.post(f"/api/answers/{aid}/vote", json={"voter": "carol"})
    client.post(f"/api/answers/{aid}/vote", json={"voter": "dave"})
    detail = client.get(f"/api/requests/{rid}").json()
    a = next(a for a in detail["answers"] if a["id"] == aid)
    assert a["votes"] == 2
    assert a["accepted"] is False


def test_self_vote_allowed(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    # bob voting on his own answer — allowed for solo-user
    r = client.post(f"/api/answers/{aid}/vote", json={"voter": "bob"})
    assert r.status_code == 200
    assert r.json()["votes"] == 1


def test_two_voters_independent(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    client.post(f"/api/answers/{aid}/vote", json={"voter": "carol"})
    client.post(f"/api/answers/{aid}/vote", json={"voter": "dave"})
    # carol toggles off — only dave remains
    client.post(f"/api/answers/{aid}/vote", json={"voter": "carol"})
    r = client.get(f"/api/requests/{rid}").json()
    a = next(a for a in r["answers"] if a["id"] == aid)
    assert a["votes"] == 1


# ----- summary list integration -----

def test_request_list_summary_includes_accepted_answer_id(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    client.post(f"/api/requests/{rid}/accept",
                json={"answer_id": aid, "client_id": "alice"})
    r = client.get("/api/requests?status=all")
    assert r.status_code == 200
    item = next(x for x in r.json() if x["id"] == rid)
    assert item["accepted_answer_id"] == aid


def test_request_list_summary_top_votes(client):
    rid = _post_request(client, "alice")
    a1 = _post_answer(client, rid, "bob")
    a2 = _post_answer(client, rid, "carol")
    client.post(f"/api/answers/{a1}/vote", json={"voter": "x"})
    client.post(f"/api/answers/{a2}/vote", json={"voter": "x"})
    client.post(f"/api/answers/{a2}/vote", json={"voter": "y"})
    r = client.get("/api/requests?status=all")
    item = next(x for x in r.json() if x["id"] == rid)
    assert item["top_votes"] == 2


def test_summary_has_default_zero_top_votes_and_null_accepted(client):
    rid = _post_request(client, "alice")
    _post_answer(client, rid, "bob")
    r = client.get("/api/requests?status=all")
    item = next(x for x in r.json() if x["id"] == rid)
    assert item["accepted_answer_id"] is None
    assert item["top_votes"] == 0


# ----- events -----

def test_request_accepted_event_emitted(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    client.post(f"/api/requests/{rid}/accept",
                json={"answer_id": aid, "client_id": "alice"})
    store = client.app.state.store
    rows = store.list_events_after(0, limit=20)
    accepted = [r for r in rows if r["kind"] == "request.accepted"]
    assert len(accepted) == 1
    payload = accepted[0]["payload"]
    assert payload["request_id"] == rid
    assert payload["accepted_answer_id"] == aid
    assert "accepted_at" in payload
    assert payload["accepted_at"] > 0


def test_answer_vote_event_emitted_on_each_toggle(client):
    rid = _post_request(client, "alice")
    aid = _post_answer(client, rid, "bob")
    client.post(f"/api/answers/{aid}/vote", json={"voter": "carol"})
    client.post(f"/api/answers/{aid}/vote", json={"voter": "carol"})
    store = client.app.state.store
    rows = store.list_events_after(0, limit=20)
    votes = [r for r in rows if r["kind"] == "answer.vote"]
    assert len(votes) == 2
    p0, p1 = votes[0]["payload"], votes[1]["payload"]
    assert p0["answer_id"] == aid
    assert p0["request_id"] == rid
    assert p0["votes"] == 1
    assert p1["votes"] == 0


# ----- migration on top of existing data -----

def test_migration_002_applies_on_top_of_001_with_seed(tmp_path):
    """Run only 001, seed data, then run 002 — ensure data preserved
    and new schema present."""
    import sys
    SERVER = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(SERVER))
    from migration_runner import MIGRATIONS_DIR

    db_path = str(tmp_path / "step.db")

    # Apply only 001 manually
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((MIGRATIONS_DIR / "001_init.sql").read_text())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations "
        "(version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
    )
    conn.execute(
        "INSERT INTO _migrations (version, applied_at) VALUES ('001_init', 1)"
    )
    # Seed: a request + an answer.
    conn.execute(
        "INSERT INTO requests "
        "(id, client_id, model, goal, context, tried, error, constraints, "
        "question, status, created_at) "
        "VALUES ('r1', 'alice', 'm', 'g', 'c', 't', NULL, NULL, 'q', 'open', 100)"
    )
    conn.execute(
        "INSERT INTO answers "
        "(id, request_id, solver_client_id, solver_model, summary, "
        "solution, reasoning, caveats, created_at) "
        "VALUES ('a1', 'r1', 'bob', 'm', 's', NULL, NULL, NULL, 200)"
    )
    conn.commit()
    conn.close()

    # Now run the full migration runner — should pick up 002 only.
    from migration_runner import apply_migrations
    apply_migrations(db_path)

    conn = sqlite3.connect(db_path)
    versions = sorted(r[0] for r in conn.execute(
        "SELECT version FROM _migrations"
    ))
    assert versions == [
        "001_init",
        "002_quality_signals",
        "003_attachments",
    ]
    # Existing data preserved
    assert conn.execute("SELECT goal FROM requests WHERE id='r1'").fetchone()[0] == "g"
    assert conn.execute("SELECT summary FROM answers WHERE id='a1'").fetchone()[0] == "s"
    # New column exists, defaults NULL
    row = conn.execute(
        "SELECT accepted_answer_id FROM requests WHERE id='r1'"
    ).fetchone()
    assert row[0] is None
    # New table exists and is empty
    assert conn.execute("SELECT COUNT(*) FROM answer_votes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 0
