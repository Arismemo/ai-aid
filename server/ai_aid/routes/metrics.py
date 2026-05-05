import os

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


def _count(store, sql: str, params: tuple = ()) -> int:
    with store._conn() as c:
        return int(c.execute(sql, params).fetchone()[0])


@router.get("/metrics")
async def metrics(request: Request):
    settings = request.app.state.settings
    store = request.app.state.store

    open_n = _count(store, "SELECT COUNT(*) FROM requests WHERE status = 'open'")
    closed_n = _count(store, "SELECT COUNT(*) FROM requests WHERE status = 'closed'")
    answers_n = _count(store, "SELECT COUNT(*) FROM answers")
    events_n = store.count_events()

    try:
        db_bytes = os.path.getsize(settings.db_path)
    except OSError:
        db_bytes = 0

    body = (
        "# HELP ai_aid_requests_total Number of help requests by status.\n"
        "# TYPE ai_aid_requests_total gauge\n"
        f'ai_aid_requests_total{{status="open"}} {open_n}\n'
        f'ai_aid_requests_total{{status="closed"}} {closed_n}\n'
        "\n"
        "# HELP ai_aid_answers_total Number of answers posted.\n"
        "# TYPE ai_aid_answers_total counter\n"
        f"ai_aid_answers_total {answers_n}\n"
        "\n"
        "# HELP ai_aid_events_buffered Current events table size.\n"
        "# TYPE ai_aid_events_buffered gauge\n"
        f"ai_aid_events_buffered {events_n}\n"
        "\n"
        "# HELP ai_aid_db_bytes SQLite file size in bytes.\n"
        "# TYPE ai_aid_db_bytes gauge\n"
        f"ai_aid_db_bytes {db_bytes}\n"
    )
    return PlainTextResponse(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
