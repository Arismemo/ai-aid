from fastapi import APIRouter, Request

from ai_aid import events as event_payloads
from ai_aid.errors import not_found, conflict

router = APIRouter(prefix="/api/requests")


@router.post("/{rid}/close")
async def close_request(rid: str, request: Request):
    store = request.app.state.store
    row = store.get_request(rid)
    if row is None:
        raise not_found(f"request {rid} not found", request_id=rid)
    if not store.close_request(rid):
        raise conflict("request not open", status=row["status"], request_id=rid)
    closed = store.get_request(rid)
    settings = request.app.state.settings
    store.append_event(
        "request.closed",
        event_payloads.request_closed(rid, closed_at=closed["closed_at"]),
    )
    store.trim_events(keep=settings.event_buffer)
    return {"id": rid, "status": closed["status"], "closed_at": closed["closed_at"]}
