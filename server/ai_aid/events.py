from typing import Optional


def request_created(row: dict, *, answer_count: int = 0) -> dict:
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "model": row["model"],
        "goal": row["goal"],
        "status": row["status"],
        "created_at": row["created_at"],
        "closed_at": row["closed_at"],
        "answer_count": answer_count,
    }


def answer_created(request_id: str, ans: dict) -> dict:
    return {
        "request_id": request_id,
        "id": ans["id"],
        "solver_client_id": ans["solver_client_id"],
        "solver_model": ans["solver_model"],
        "summary": ans["summary"],
        "solution": ans["solution"],
        "reasoning": ans["reasoning"],
        "caveats": ans["caveats"],
        "created_at": ans["created_at"],
    }


def request_closed(rid: str, *, closed_at: int) -> dict:
    return {"id": rid, "status": "closed", "closed_at": closed_at}


def request_deleted(rid: str) -> dict:
    return {"id": rid}


def request_accepted(rid: str, *, accepted_answer_id: str, accepted_at: int) -> dict:
    return {
        "request_id": rid,
        "accepted_answer_id": accepted_answer_id,
        "accepted_at": accepted_at,
    }


def answer_vote(answer_id: str, *, request_id: str, votes: int) -> dict:
    return {
        "answer_id": answer_id,
        "request_id": request_id,
        "votes": votes,
    }
