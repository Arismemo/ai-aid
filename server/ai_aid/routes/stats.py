from typing import Optional

from fastapi import APIRouter, Request

from ai_aid.errors import bad_request

router = APIRouter()


@router.get("/api/stats")
async def client_stats(request: Request, client_id: Optional[str] = None):
    if not client_id or not client_id.strip():
        raise bad_request("client_id query param required")
    store = request.app.state.store
    return store.client_stats(client_id)
