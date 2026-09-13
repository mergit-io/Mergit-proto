import time

from fastapi import APIRouter

import db
import worker
from models import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> HealthResponse:
    db_status = "ok"
    try:
        async with db.get_conn() as conn:
            await conn.execute("SELECT 1")
    except Exception:
        db_status = "error"

    return HealthResponse(
        status="ok",
        db=db_status,
        worker="running" if worker.is_running() else "stopped",
        ts=int(time.time()),
    )
