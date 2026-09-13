import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
import worker
from api import goals, health, stream, tasks, webhooks
from config import settings
from tracing import init_tracing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    Path(settings.workspace_dir).mkdir(parents=True, exist_ok=True)
    init_tracing(settings.omium_api_key, settings.omium_project)
    await worker.start()
    logger.info("omniBox started")
    yield
    await worker.stop()
    logger.info("omniBox stopped")


app = FastAPI(title="omniBox", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(goals.router)
app.include_router(tasks.router)
app.include_router(stream.router)
app.include_router(webhooks.router)
app.include_router(health.router)

# Serve frontend in production
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
