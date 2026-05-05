"""Structured (JSON) access logging.

`configure_logging()` installs a JSON formatter on the root + uvicorn loggers.
`install_access_log_middleware()` adds a per-request middleware that emits one
JSON-line per response with method, path, status, and duration_ms.
"""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request

ACCESS_LOGGER_NAME = "ai_aid.access"
_CONFIGURED_FLAG = "_ai_aid_log_configured"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # If the record's message is already a JSON object string, keep it as
        # the body (so middleware-emitted records survive untouched). Otherwise
        # wrap in a small envelope.
        msg = record.getMessage()
        try:
            inner = json.loads(msg)
            if isinstance(inner, dict):
                return msg
        except (ValueError, TypeError):
            pass
        envelope = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
        }
        return json.dumps(envelope, ensure_ascii=False)


def configure_logging() -> None:
    """Idempotently swap formatters on the access logger and uvicorn loggers."""
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_FLAG, False):
        return
    setattr(root, _CONFIGURED_FLAG, True)

    formatter = _JsonFormatter()

    # Our own access logger — emits one JSON line per request.
    access = logging.getLogger(ACCESS_LOGGER_NAME)
    access.setLevel(logging.INFO)
    if not access.handlers:
        h = logging.StreamHandler()
        h.setFormatter(formatter)
        access.addHandler(h)
        access.propagate = True  # let pytest caplog see it

    # Replace formatters on uvicorn loggers without removing handlers.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        for h in lg.handlers:
            h.setFormatter(formatter)


def install_access_log_middleware(app: FastAPI) -> None:
    log = logging.getLogger(ACCESS_LOGGER_NAME)

    @app.middleware("http")
    async def _access_log(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        client_host = request.client.host if request.client else None
        body = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "logger": ACCESS_LOGGER_NAME,
            "client": client_host,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }
        log.info(json.dumps(body, ensure_ascii=False))
        return response
