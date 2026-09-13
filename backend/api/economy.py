import asyncio
import json

from fastapi import APIRouter, Request, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

import db
from auth.gate import require_user
import economy
import events
from chain.client import get_client
from config import settings

router = APIRouter(prefix="/api/economy", tags=["economy"])



@router.get("/verify/{task_id}")
async def verify_proof(task_id: str):
    """Prove that a stored agent output matches what was recorded on chain.

    Returns every intermediate value so the check can be reproduced by hand:
    canonical JSON → sha256 → compare against `ProofOfWork.getProof`.
    """
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Unknown task")

    output = task.output or {}
    canonical = economy.canonical_json(output)
    computed = economy.result_hash(output)

    result = {
        "task_id": task_id,
        "goal_id": task.goal_id,
        "agent_role": task.agent_name,
        "task_status": task.status,
        "canonical_output": canonical,
        "computed_hash": computed,
        "hash_algorithm": "sha256",
        "task_key_algorithm": "keccak256",
        "onchain_hash": None,
        "tx_hash": None,
        "block_number": None,
        "chain_id": None,
        "explorer_url": None,
        "verified": None,
        "reason": None,
    }

    outbox = await db.get_outbox_entry(task_id)
    if outbox:
        result["submission_status"] = outbox["status"]
        result["tx_hash"] = outbox["tx_hash"]
        result["block_number"] = outbox["block_number"]
        result["chain_id"] = outbox["chain_id"]

    client = get_client()
    if client is None or not client.is_ready:
        result["reason"] = "chain_unavailable"
        return result

    onchain = client.get_proof(task_id)
    if not onchain:
        result["reason"] = "not_recorded"
        return result

    result["onchain_hash"] = onchain["result_hash"]
    result["block_number"] = onchain["block_number"]
    result["chain_id"] = onchain["chain_id"]
    result["verified"] = onchain["result_hash"] == computed
    if not result["verified"]:
        result["reason"] = "hash_mismatch"
    if result["tx_hash"]:
        result["explorer_url"] = client.tx_url(result["tx_hash"])
    return result


@router.get("/chain/status")
async def chain_status():
    """Live chain target, deployment state and submission queue depth."""
    client = get_client()
    info = client.info() if client else {"status": "disabled"}
    try:
        info["outbox"] = await db.outbox_stats()
    except Exception:
        info["outbox"] = {}
    return info


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
async def proofs(
    # Bounded: this reaches `LIMIT ?` directly, and SQLite treats a negative limit as
    # unbounded — ?limit=-1 dumped the entire proof ledger.
    request: Request,
    limit: int = Query(50, ge=1, le=settings.max_page_size),
    before: int | None = Query(None, ge=0),
):
    # Own proofs plus the public demo rows — see db._VISIBLE_GOALS for why a strict
    # per-caller filter would empty the showcase's centrepiece for every real user.
    user = require_user(request)
    return await db.list_proofs(limit=limit, before_block=before, user_id=user["id"])


@router.get("/agents/{role}")
async def agent_detail(role: str, request: Request):
    passport = await db.get_passport(role)
    if not passport:
        raise HTTPException(status_code=404, detail="Unknown agent")
    rep = await db.get_reputation(role)
    user = require_user(request)
    role_proofs = await db.list_proofs_for_role(role, limit=25, user_id=user["id"])
    return {"passport": passport, "reputation": rep, "proofs": role_proofs}


@router.get("/chain")
async def chain():
    """The chain the app is actually connected to.

    This used to read deployments/10143.json unconditionally, so it announced Monad
    Testnet and four addresses that had never been deployed anywhere — whatever chain was
    really running underneath. It now reports the live client, which is also the only
    source that can be wrong in a way anyone would notice.
    """
    client = get_client()
    if client is None:
        return {"chainId": None, "network": "disabled", "explorer": "", "contracts": {}}
    return {
        "chainId": client.chain_id,
        "network": client.network.name,
        "explorer": client.network.explorer_base or "",
        "contracts": client.addresses,
        "status": client.status.value,
    }


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
