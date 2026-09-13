import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import db
import worker
from api import config, goals, health, keys, stream, tasks, webhooks
from config import settings
from tracing import init_tracing

# ── Logging setup ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)-24s %(message)s",
    datefmt="%H:%M:%S",
)
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
    logger.info("Starting omniBox (host=%s port=%s debug=%s)", settings.host, settings.port, settings.debug)
    await db.init_db()
    Path(settings.workspace_dir).mkdir(parents=True, exist_ok=True)
    logger.info("DB initialised at %s", settings.db_path)
    init_tracing(settings.omium_api_key, settings.omium_project)
    await worker.start()
    logger.info("omniBox ready ✓")
    yield
    logger.info("Shutting down omniBox…")
    await worker.stop()
    logger.info("omniBox stopped")


# ── App ───────────────────────────────────────────────────────────────────────────

app = FastAPI(title="omniBox", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

app.include_router(config.router)
app.include_router(keys.router)
app.include_router(goals.router)
app.include_router(tasks.router)
app.include_router(stream.router)
app.include_router(webhooks.router)
app.include_router(health.router)


# ── Frontend static files (production) ────────────────────────────────────────────

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
    logger.info("Serving frontend from %s", _frontend_dist)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_includes=["*.py"],
        reload_excludes=["*/__pycache__/*", "*.pyc", "*.db", "*.db-wal", "*.db-shm"],
        log_level="warning",
    )
