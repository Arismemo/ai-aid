from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AidError(Exception):
    def __init__(self, status_code: int, error: str, message: str, **extra: Any):
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message
        self.extra = extra


def not_found(message: str, **extra) -> AidError:
    return AidError(404, "not_found", message, **extra)


def forbidden(message: str, **extra) -> AidError:
    return AidError(403, "forbidden", message, **extra)


def conflict(message: str, **extra) -> AidError:
    return AidError(409, "conflict", message, **extra)


def payload_too_large(actual_kb: int, **extra) -> AidError:
    return AidError(413, "payload_too_large", f"body {actual_kb}KB exceeds limit", **extra)


def rate_limited(client_id: str, limit: int, **extra) -> AidError:
    return AidError(
        429, "rate_limited",
        f"client {client_id} exceeded {limit}/min",
        client_id=client_id, limit=limit, **extra,
    )


def bad_request(message: str, **extra) -> AidError:
    return AidError(400, "bad_request", message, **extra)


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AidError)
    async def _aid_handler(request: Request, exc: AidError):
        body = {"error": exc.error, "message": exc.message, **exc.extra}
        return JSONResponse(status_code=exc.status_code, content=body)
