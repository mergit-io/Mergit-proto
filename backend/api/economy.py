import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

import db
import economy
import events

router = APIRouter(prefix="/api/economy", tags=["economy"])

_CHAIN_FILE = Path(__file__).resolve().parent.parent / "deployments" / "10143.json"


@router.get("/passports")
async def passports():
    return await db.list_passports()


@router.get("/leaderboard")
async def leaderboard():
    reps = await db.list_reputation()
    passports_by_role = {p["role"]: p for p in await db.list_passports()}
    out = []
    for rank, rep in enumerate(reps, start=1):
        p = passports_by_role.get(rep["role"], {})
        out.append({**rep, "rank": rank, "token_id": p.get("token_id"),
                    "did": p.get("did")})
    return out


@router.get("/proofs")
async def proofs(limit: int = 50, before: int | None = None):
    return await db.list_proofs(limit=limit, before_block=before)


@router.get("/agents/{role}")
async def agent_detail(role: str):
    passport = await db.get_passport(role)
    if not passport:
        raise HTTPException(status_code=404, detail="Unknown agent")
    rep = await db.get_reputation(role)
    role_proofs = await db.list_proofs_for_role(role, limit=25)
    return {"passport": passport, "reputation": rep, "proofs": role_proofs}


@router.get("/chain")
async def chain():
    return json.loads(_CHAIN_FILE.read_text())


@router.get("/stream")
async def stream():
    q = events.subscribe(economy.ECONOMY_CHANNEL)

    async def generator():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=30)
                    yield {"event": item["event"], "data": json.dumps(item["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            events.unsubscribe(economy.ECONOMY_CHANNEL, q)

    return EventSourceResponse(generator())
