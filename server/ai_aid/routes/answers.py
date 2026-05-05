from fastapi import APIRouter, Request

from ai_aid.errors import forbidden, not_found, conflict
from ai_aid.models import AnswerRequest

router = APIRouter(prefix="/api/requests")


@router.post("/{rid}/answers", status_code=201)
async def create_answer(rid: str, payload: AnswerRequest, request: Request):
    store = request.app.state.store
    req_row = store.get_request(rid)
    if req_row is None:
        raise not_found(f"request {rid} not found", request_id=rid)
    if req_row["status"] != "open":
        raise conflict("request not open", status=req_row["status"], request_id=rid)
    if req_row["client_id"] == payload.solver_client_id:
        raise forbidden("cannot solve own request", request_id=rid)
    aid = store.create_answer(rid, payload.model_dump())
    answers = store.list_answers(rid)
    new_one = next(a for a in answers if a["id"] == aid)
    return {"id": aid, "created_at": new_one["created_at"]}
