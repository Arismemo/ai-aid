"""AI persona — small wrapper that does ask/list/solve/check/close."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class Persona:
    server_url: str
    client_id: str
    model: str

    def __post_init__(self) -> None:
        self._client = httpx.Client(base_url=self.server_url, timeout=10.0)

    def close(self) -> None:
        self._client.close()

    # Asker actions ------------------------------------------------------

    def ask(
        self,
        *,
        goal: str, context: str, tried: str, question: str,
        error: Optional[str] = None, constraints: Optional[str] = None,
    ) -> dict:
        body = {
            "client_id": self.client_id, "model": self.model,
            "goal": goal, "context": context, "tried": tried,
            "error": error, "constraints": constraints, "question": question,
        }
        r = self._client.post("/api/requests", json=body)
        r.raise_for_status()
        return r.json()

    def mine(self) -> list[dict]:
        r = self._client.get(
            "/api/requests",
            params={"status": "all", "client_id": self.client_id, "mine": 1},
        )
        r.raise_for_status()
        return r.json()

    def check(self, rid: str) -> dict:
        r = self._client.get(f"/api/requests/{rid}")
        r.raise_for_status()
        return r.json()

    def close_request(self, rid: str) -> dict:
        r = self._client.post(f"/api/requests/{rid}/close")
        r.raise_for_status()
        return r.json()

    # Solver actions -----------------------------------------------------

    def list_open(self) -> list[dict]:
        r = self._client.get(
            "/api/requests",
            params={"status": "open", "exclude_client": self.client_id},
        )
        r.raise_for_status()
        return r.json()

    def solve(
        self,
        rid: str,
        *,
        summary: str,
        solution: Optional[str] = None,
        reasoning: Optional[str] = None,
        caveats: Optional[str] = None,
    ) -> httpx.Response:
        body = {
            "solver_client_id": self.client_id, "solver_model": self.model,
            "summary": summary,
            "solution": solution, "reasoning": reasoning, "caveats": caveats,
        }
        return self._client.post(f"/api/requests/{rid}/answers", json=body)
