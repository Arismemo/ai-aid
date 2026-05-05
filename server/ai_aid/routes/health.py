import sqlite3
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    db_ok = "ok"
    try:
        with sqlite3.connect(settings.db_path) as c:
            c.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = "error"
    return {"ok": db_ok == "ok", "db": db_ok, "events_buffered": 0}
