from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ai_aid.config import Settings
from ai_aid.db import Store
from ai_aid.errors import register_handlers, payload_too_large
from ai_aid.rate_limit import SlidingWindow
from ai_aid.routes import health
from migration_runner import apply_migrations


def create_app() -> FastAPI:
    settings = Settings.from_env()
    apply_migrations(settings.db_path)

    app = FastAPI(title="ai-aid", version="0.1.0")
    app.state.settings = settings
    app.state.store = Store(settings.db_path)
    app.state.rate_limiter = SlidingWindow(
        limit=settings.rate_limit_per_min, window_ms=60_000
    )

    # Configure structured (JSON) logging once per app instance.
    from ai_aid.logging_setup import configure_logging, install_access_log_middleware
    configure_logging()

    # Run a startup prune (cheap SQLite delete; fire-and-forget on error).
    if settings.retention_days > 0:
        try:
            app.state.store.prune_old_closed(days=settings.retention_days)
        except Exception:  # noqa: BLE001
            pass

    register_handlers(app)

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()]
        return JSONResponse(
            status_code=400,
            content={
                "error": "bad_request",
                "message": "validation failed",
                "fields": fields,
            },
        )

    # Body-size guard: relies on Content-Length being honest. Production
    # deployments must enforce the real cap at the reverse proxy
    # (e.g. nginx client_max_body_size) since clients can spoof headers
    # or use chunked transfer to bypass this check.
    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        max_bytes = settings.max_body_kb * 1024
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > max_bytes:
            err = payload_too_large(int(cl) // 1024)
            return JSONResponse(
                status_code=err.status_code,
                content={"error": err.error, "message": err.message, **err.extra},
            )
        return await call_next(request)

    # Access log middleware (registered last so it wraps everything else).
    install_access_log_middleware(app)

    app.include_router(health.router)
    from ai_aid.routes import requests as requests_routes
    app.include_router(requests_routes.router)
    from ai_aid.routes import answers as answers_routes
    app.include_router(answers_routes.router)
    from ai_aid.routes import lifecycle as lifecycle_routes
    app.include_router(lifecycle_routes.router)
    from ai_aid.routes import sse as sse_routes
    app.include_router(sse_routes.router)
    from ai_aid.routes import recent as recent_routes
    app.include_router(recent_routes.router)
    from ai_aid.routes import stats as stats_routes
    app.include_router(stats_routes.router)
    from ai_aid.routes import metrics as metrics_routes
    app.include_router(metrics_routes.router)

    from fastapi.staticfiles import StaticFiles
    from pathlib import Path
    from fastapi.responses import FileResponse

    web_dir = Path(__file__).parent.parent.parent / "web"
    if web_dir.exists():
        app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")

        @app.get("/")
        async def index():
            return FileResponse(str(web_dir / "index.html"))

    return app
