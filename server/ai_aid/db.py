import json as _json
import sqlite3
import time
import uuid
from typing import Any, Optional


def _now_ms() -> int:
    return int(time.time() * 1000)


class Store:
    def __init__(self, path: str):
        self.path = path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_request(self, payload: dict) -> str:
        rid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO requests "
                "(id, client_id, model, goal, context, tried, error, constraints, question, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
                (
                    rid, payload["client_id"], payload["model"],
                    payload["goal"], payload["context"], payload["tried"],
                    payload.get("error"), payload.get("constraints"),
                    payload["question"], _now_ms(),
                ),
            )
        return rid

    def get_request(self, rid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM requests WHERE id = ?", (rid,)).fetchone()
            return dict(row) if row else None

    def list_requests(
        self,
        *,
        status: str,
        exclude_client: Optional[str],
        only_client: Optional[str],
    ) -> list[dict]:
        sql = "SELECT * FROM requests WHERE 1=1"
        params: list[Any] = []
        if status != "all":
            sql += " AND status = ?"
            params.append(status)
        if exclude_client:
            sql += " AND client_id != ?"
            params.append(exclude_client)
        if only_client:
            sql += " AND client_id = ?"
            params.append(only_client)
        sql += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close_request(self, rid: str) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE requests SET status='closed', closed_at=? WHERE id=? AND status='open'",
                (_now_ms(), rid),
            )
            return cur.rowcount == 1

    def delete_request(self, rid: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM requests WHERE id = ?", (rid,))
            return cur.rowcount == 1

    def create_answer(self, rid: str, payload: dict) -> str:
        aid = str(uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO answers "
                "(id, request_id, solver_client_id, solver_model, summary, solution, reasoning, caveats, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    aid, rid, payload["solver_client_id"], payload["solver_model"],
                    payload["summary"], payload.get("solution"),
                    payload.get("reasoning"), payload.get("caveats"), _now_ms(),
                ),
            )
        return aid

    def list_answers(self, rid: str) -> list[dict]:
        with self._conn() as c:
            req_row = c.execute(
                "SELECT accepted_answer_id FROM requests WHERE id = ?",
                (rid,),
            ).fetchone()
            accepted = req_row["accepted_answer_id"] if req_row else None
            rows = c.execute(
                "SELECT a.*, "
                "(SELECT COUNT(*) FROM answer_votes v WHERE v.answer_id = a.id) "
                "AS votes "
                "FROM answers a "
                "WHERE a.request_id = ? ORDER BY a.created_at ASC",
                (rid,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["accepted"] = bool(accepted) and d["id"] == accepted
            out.append(d)
        return out

    def accept_answer(
        self, rid: str, aid: str, asker_client_id: str
    ) -> bool:
        """Mark `aid` as the accepted answer for `rid`.

        Returns True on success. Returns False on ownership mismatch
        (asker_client_id != requests.client_id) OR if the answer doesn't
        belong to this request. Raises LookupError if the request or
        the answer doesn't exist (caller maps to 404).
        """
        with self._conn() as c:
            req = c.execute(
                "SELECT client_id FROM requests WHERE id = ?", (rid,),
            ).fetchone()
            if req is None:
                raise LookupError(f"request {rid} not found")
            ans = c.execute(
                "SELECT request_id FROM answers WHERE id = ?", (aid,),
            ).fetchone()
            if ans is None:
                raise LookupError(f"answer {aid} not found")
            if ans["request_id"] != rid:
                # Treat as not-found for this request — the answer exists
                # but doesn't belong here.
                raise LookupError(f"answer {aid} not on request {rid}")
            if req["client_id"] != asker_client_id:
                return False
            c.execute(
                "UPDATE requests SET accepted_answer_id = ? WHERE id = ?",
                (aid, rid),
            )
        return True

    def toggle_vote(self, answer_id: str, voter: str) -> tuple[int, bool]:
        """Toggle a voter's vote on an answer.

        Returns (new_total_votes, voted_now). Raises LookupError if the
        answer doesn't exist (caller maps to 404).
        """
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM answers WHERE id = ?", (answer_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"answer {answer_id} not found")
            existing = c.execute(
                "SELECT 1 FROM answer_votes WHERE answer_id = ? AND voter = ?",
                (answer_id, voter),
            ).fetchone()
            if existing:
                c.execute(
                    "DELETE FROM answer_votes WHERE answer_id = ? AND voter = ?",
                    (answer_id, voter),
                )
                voted_now = False
            else:
                c.execute(
                    "INSERT INTO answer_votes (answer_id, voter, created_at) "
                    "VALUES (?, ?, ?)",
                    (answer_id, voter, _now_ms()),
                )
                voted_now = True
            total = int(c.execute(
                "SELECT COUNT(*) FROM answer_votes WHERE answer_id = ?",
                (answer_id,),
            ).fetchone()[0])
        return total, voted_now

    def count_votes(self, answer_id: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) FROM answer_votes WHERE answer_id = ?",
                (answer_id,),
            ).fetchone()
        return int(row[0])

    def get_answer(self, aid: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM answers WHERE id = ?", (aid,),
            ).fetchone()
            return dict(row) if row else None

    def top_votes_for_request(self, rid: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(MAX(c), 0) FROM ("
                "  SELECT COUNT(*) AS c FROM answer_votes v "
                "  JOIN answers a ON a.id = v.answer_id "
                "  WHERE a.request_id = ? GROUP BY v.answer_id"
                ")",
                (rid,),
            ).fetchone()
        return int(row[0])

    def count_recent_requests(self, client_id: str, window_ms: int) -> int:
        cutoff = _now_ms() - window_ms
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) FROM requests WHERE client_id = ? AND created_at >= ?",
                (client_id, cutoff),
            ).fetchone()
            return int(row[0])

    def append_event(self, kind: str, payload: dict) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO events (kind, payload, created_at) VALUES (?, ?, ?)",
                (kind, _json.dumps(payload), _now_ms()),
            )
            return int(cur.lastrowid)

    def list_events_after(self, last_id: int, *, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM events WHERE id > ? ORDER BY id ASC LIMIT ?",
                (last_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = _json.loads(d["payload"])
            out.append(d)
        return out

    def count_events(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def trim_events(self, *, keep: int) -> None:
        with self._conn() as c:
            c.execute(
                "DELETE FROM events WHERE id NOT IN ("
                "SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                (keep,),
            )

    def max_event_id(self) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
            return int(row[0])

    def min_event_id(self) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COALESCE(MIN(id), 0) FROM events").fetchone()
            return int(row[0])

    def list_recent_activity(self, limit: int) -> list[dict]:
        """Return a global activity feed combining request.created and
        answer.created events with their underlying objects.

        Ordered by event id DESC (newest first), capped at `limit`.
        Closed/deleted events are excluded — this is "ask/answer" activity.
        """
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        out: list[dict] = []
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, kind, payload, created_at FROM events "
                "WHERE kind IN ('request.created', 'answer.created') "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            for row in rows:
                payload = _json.loads(row["payload"])
                if row["kind"] == "request.created":
                    rid = payload.get("id")
                    req_row = c.execute(
                        "SELECT * FROM requests WHERE id = ?", (rid,)
                    ).fetchone()
                    if req_row is None:
                        # underlying request was deleted; skip
                        continue
                    out.append({
                        "kind": "request.created",
                        "at": row["created_at"],
                        "request": dict(req_row),
                    })
                elif row["kind"] == "answer.created":
                    aid = payload.get("id")
                    rid = payload.get("request_id")
                    ans_row = c.execute(
                        "SELECT * FROM answers WHERE id = ?", (aid,)
                    ).fetchone()
                    if ans_row is None:
                        continue
                    req_row = c.execute(
                        "SELECT id, goal, client_id FROM requests WHERE id = ?",
                        (rid,),
                    ).fetchone()
                    if req_row is None:
                        continue
                    out.append({
                        "kind": "answer.created",
                        "at": row["created_at"],
                        "answer": dict(ans_row),
                        "request": dict(req_row),
                    })
        return out

    def client_stats(self, client_id: str) -> dict:
        """Per-client statistics — asks total/open/closed, answers given,
        asks-received-answer count, and answer_accept_rate."""
        with self._conn() as c:
            asks_total = int(c.execute(
                "SELECT COUNT(*) FROM requests WHERE client_id = ?",
                (client_id,),
            ).fetchone()[0])
            asks_open = int(c.execute(
                "SELECT COUNT(*) FROM requests WHERE client_id = ? AND status = 'open'",
                (client_id,),
            ).fetchone()[0])
            asks_closed = int(c.execute(
                "SELECT COUNT(*) FROM requests WHERE client_id = ? AND status = 'closed'",
                (client_id,),
            ).fetchone()[0])
            answers_given = int(c.execute(
                "SELECT COUNT(*) FROM answers WHERE solver_client_id = ?",
                (client_id,),
            ).fetchone()[0])
            asks_received_answer = int(c.execute(
                "SELECT COUNT(DISTINCT r.id) FROM requests r "
                "JOIN answers a ON a.request_id = r.id "
                "WHERE r.client_id = ?",
                (client_id,),
            ).fetchone()[0])
        if asks_total == 0:
            accept_rate = None
        else:
            accept_rate = asks_received_answer / asks_total
        return {
            "client_id": client_id,
            "asks_total": asks_total,
            "asks_open": asks_open,
            "asks_closed": asks_closed,
            "answers_given": answers_given,
            "asks_received_answer": asks_received_answer,
            "answer_accept_rate": accept_rate,
        }

    def prune_old_closed(self, days: int) -> int:
        """Delete closed requests whose closed_at is older than `days` days.

        Returns number of rows deleted. days <= 0 is a no-op (returns 0).
        Cascade deletes answers via FK ON DELETE CASCADE.
        """
        if days <= 0:
            return 0
        cutoff = _now_ms() - days * 86_400_000
        with self._conn() as c:
            cur = c.execute(
                "DELETE FROM requests WHERE status = 'closed' AND closed_at IS NOT NULL "
                "AND closed_at < ?",
                (cutoff,),
            )
            return int(cur.rowcount)
