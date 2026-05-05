from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from ai_aid.errors import not_found, rate_limited
from ai_aid.models import AnswerOut, AskRequest, CreateResponse, RequestDetail, RequestSummary

router = APIRouter(prefix="/api/requests")


@router.post("", status_code=201, response_model=CreateResponse)
async def create_request(payload: AskRequest, request: Request):
    settings = request.app.state.settings
    rl = request.app.state.rate_limiter
    if not rl.allow(payload.client_id):
        raise rate_limited(client_id=payload.client_id, limit=settings.rate_limit_per_min)
    store = request.app.state.store
    rid = store.create_request(payload.model_dump())
    row = store.get_request(rid)
    return {"id": row["id"], "status": row["status"], "created_at": row["created_at"]}


@router.get("", response_model=list[RequestSummary])
async def list_requests(
    request: Request,
    status: str = Query("open", pattern="^(open|closed|all)$"),
    exclude_client: Optional[str] = None,
    client_id: Optional[str] = None,
    mine: int = 0,
):
    store = request.app.state.store
    only = client_id if mine == 1 else None
    rows = store.list_requests(status=status, exclude_client=exclude_client, only_client=only)
    out = []
    for row in rows:
        answers = store.list_answers(row["id"])
        out.append({
            "id": row["id"], "client_id": row["client_id"], "model": row["model"],
            "goal": row["goal"], "status": row["status"],
            "created_at": row["created_at"], "closed_at": row["closed_at"],
            "answer_count": len(answers),
        })
    return out


@router.get("/{rid}", response_model=RequestDetail)
async def get_request(rid: str, request: Request):
    store = request.app.state.store
    row = store.get_request(rid)
    if row is None:
        raise not_found(f"request {rid} not found", request_id=rid)
    answers = [
        AnswerOut(**{
            "id": a["id"], "solver_client_id": a["solver_client_id"],
            "solver_model": a["solver_model"], "summary": a["summary"],
            "solution": a["solution"], "reasoning": a["reasoning"],
            "caveats": a["caveats"], "created_at": a["created_at"],
        }).model_dump()
        for a in store.list_answers(rid)
    ]
    return {**row, "answers": answers}


@router.delete("/{rid}", status_code=204)
async def delete_request(rid: str, request: Request):
    store = request.app.state.store
    if not store.delete_request(rid):
        raise not_found(f"request {rid} not found", request_id=rid)
    return Response(status_code=204)
