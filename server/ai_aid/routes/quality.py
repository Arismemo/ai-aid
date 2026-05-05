"""Quality-signal endpoints: accept (one per request, asker-only) +
upvote (toggle, any client). Lives separately from /answers and /requests
so the existing route files stay focused on CRUD."""
import time

from fastapi import APIRouter, Request

from ai_aid import events as event_payloads
from ai_aid.errors import forbidden, not_found
from ai_aid.models import AcceptRequest, VoteRequest

router = APIRouter()


def _now_ms() -> int:
    return int(time.time() * 1000)


@router.post("/api/requests/{rid}/accept")
async def accept_answer(rid: str, payload: AcceptRequest, request: Request):
    store = request.app.state.store
    settings = request.app.state.settings
    try:
        ok = store.accept_answer(rid, payload.answer_id, payload.client_id)
    except LookupError as e:
        raise not_found(str(e), request_id=rid)
    if not ok:
        raise forbidden(
            "only the asker can accept an answer", request_id=rid,
        )
    accepted_at = _now_ms()
    store.append_event(
        "request.accepted",
        event_payloads.request_accepted(
            rid,
            accepted_answer_id=payload.answer_id,
            accepted_at=accepted_at,
        ),
    )
    store.trim_events(keep=settings.event_buffer)
    return {"id": rid, "accepted_answer_id": payload.answer_id}


@router.post("/api/answers/{aid}/vote")
async def vote_answer(aid: str, payload: VoteRequest, request: Request):
    store = request.app.state.store
    settings = request.app.state.settings
    try:
        votes, voted = store.toggle_vote(aid, payload.voter)
    except LookupError as e:
        raise not_found(str(e))
    ans = store.get_answer(aid)
    rid = ans["request_id"] if ans else None
    store.append_event(
        "answer.vote",
        event_payloads.answer_vote(aid, request_id=rid, votes=votes),
    )
    store.trim_events(keep=settings.event_buffer)
    return {"answer_id": aid, "votes": votes, "voted": voted}
