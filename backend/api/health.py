import time

from fastapi import APIRouter

import db
import worker
from chain.client import get_client
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

    chain_status, chain_id = "disabled", None
    try:
        client = get_client()
        if client is not None:
            chain_status, chain_id = client.status.value, client.chain_id
    except Exception:
        chain_status = "error"

    return HealthResponse(
        status="ok",
        db=db_status,
        worker="running" if worker.is_running() else "stopped",
        ts=int(time.time()),
        chain=chain_status,
        chain_id=chain_id,
    )
