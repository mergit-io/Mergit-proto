import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import db
import worker
from api import actions, auth, config, context as ctx_api, github_webhook, goals, health, keys, stream, tasks, webhooks
from api import economy as economy_api
from config import cors_origin_list, settings
from tracing import init_tracing

# ── Logging setup ────────────────────────────────────────────────────────────────
_log_fmt = "%(asctime)s %(levelname)-8s %(name)-24s %(message)s"
_log_date = "%H:%M:%S"
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format=_log_fmt,
    datefmt=_log_date,
)
# Also write to a rotating file so you can debug without watching the terminal
import os
from logging.handlers import RotatingFileHandler as _RFH
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_fh = _RFH(os.path.join(_log_dir, "mergit.log"), maxBytes=5_000_000, backupCount=3)
_fh.setFormatter(logging.Formatter(_log_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
_fh.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_fh)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mergit (host=%s port=%s debug=%s)", settings.host, settings.port, settings.debug)
    await db.init_db()
    import economy
    await economy.seed_passports()
    await economy.backfill()
    Path(settings.workspace_dir).mkdir(parents=True, exist_ok=True)
    logger.info("DB initialised at %s", settings.db_path)
    init_tracing(settings.omium_api_key, settings.omium_project)
    await worker.start()
    logger.info("Mergit ready ✓")
    yield
    logger.info("Shutting down Mergit…")
    await worker.stop()
    logger.info("Mergit stopped")


# ── App ───────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Mergit",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request logging middleware ────────────────────────────────────────────────────

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()

    # Skip SSE endpoints from verbose logging (they stay open)
    is_sse = "stream" in request.url.path

    if not is_sse:
        logger.debug("[%s] → %s %s", req_id, request.method, request.url.path)

    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if not is_sse:
            level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
            logger.log(level, "[%s] ← %d %s %s (%.0fms)",
                       req_id, response.status_code, request.method,
                       request.url.path, elapsed_ms)

        response.headers["X-Request-Id"] = req_id
        return response

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error("[%s] ✗ %s %s — unhandled exception after %.0fms: %s",
                     req_id, request.method, request.url.path, elapsed_ms, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": req_id},
            headers={"X-Request-Id": req_id},
        )


# ── Routers ───────────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(config.router)
app.include_router(keys.router)
app.include_router(ctx_api.router)
app.include_router(goals.router)
app.include_router(tasks.router)
app.include_router(stream.router)
app.include_router(github_webhook.router)  # specific route before generic /{token}
app.include_router(webhooks.router)
app.include_router(actions.router)
app.include_router(economy_api.router)
app.include_router(health.router)


# ── Frontend static files (production) ────────────────────────────────────────────


class SPAStaticFiles(StaticFiles):
    """Static files with SPA fallback: serve index.html for any unmatched path so
    client-side routes (/app, /app/economy, /login, …) work on direct load/refresh."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", SPAStaticFiles(directory=str(_frontend_dist), html=True), name="static")
    logger.info("Serving frontend from %s", _frontend_dist)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_includes=["*.py"] if settings.debug else [],
        reload_excludes=["*/__pycache__/*", "*.pyc", "*.db", "*.db-wal", "*.db-shm"] if settings.debug else [],
        log_level="warning",
    )
