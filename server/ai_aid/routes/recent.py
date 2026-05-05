from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/api/recent")
async def recent_activity(
    request: Request,
    limit: int = Query(50, ge=1),
):
    store = request.app.state.store
    # Clamp at 200 per spec; pydantic-style hard ceiling applied in store too.
    if limit > 200:
        limit = 200
    return store.list_recent_activity(limit)
