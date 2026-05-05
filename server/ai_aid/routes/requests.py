from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ai_aid.errors import rate_limited
from ai_aid.models import AskRequest, CreateResponse

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
