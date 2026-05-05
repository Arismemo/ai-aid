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
            rows = c.execute(
                "SELECT * FROM answers WHERE request_id = ? ORDER BY created_at ASC",
                (rid,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_recent_requests(self, client_id: str, window_ms: int) -> int:
        cutoff = _now_ms() - window_ms
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) FROM requests WHERE client_id = ? AND created_at >= ?",
                (client_id, cutoff),
            ).fetchone()
            return int(row[0])
