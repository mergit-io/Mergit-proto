"""Background worker that drains the proof outbox onto the chain.

Runs independently of task execution: a chain that is slow, down or undeployed only means
proofs settle later, never that a goal fails. Restart-safe — the queue lives in SQLite.
"""
import asyncio
import logging

import db
import economy
import events
from chain.client import get_client
from config import settings

logger = logging.getLogger(__name__)

_running = False
_BATCH_SIZE = 5
_STUCK_AFTER_SECONDS = 300


def is_running() -> bool:
    return _running


async def start() -> None:
    global _running
    if not settings.chain_enabled:
        logger.info("chain_worker: disabled by config (chain_enabled=false)")
        return
    _running = True
    asyncio.create_task(chain_submit_loop(), name="chain_submit")
    logger.info("chain_worker: started (target=%s)", settings.chain_target)


async def stop() -> None:
    global _running
    _running = False


async def chain_submit_loop() -> None:
    """Claim due outbox entries and submit them, forever."""
    # Anything left mid-flight by a previous process is reclaimed on boot.
    try:
        reclaimed = await db.reclaim_stuck_proofs(older_than_seconds=0)
        if reclaimed:
            logger.info("chain_worker: reclaimed %d interrupted submissions", reclaimed)
    except Exception as e:
        logger.warning("chain_worker: startup reclaim failed: %s", e)

    # The in-process EVM is wiped on restart while the outbox survives, so anything it
    # previously confirmed would silently stop verifying. Re-submit it to the new chain.
    try:
        client = get_client()
        if client is not None and client.network.is_local:
            requeued = await db.requeue_proofs_for_chain(client.chain_id)
            if requeued:
                logger.info(
                    "chain_worker: re-submitting %d proof(s) — the local chain is ephemeral "
                    "and was reset by this restart", requeued)
    except Exception as e:
        logger.warning("chain_worker: ephemeral-chain requeue failed: %s", e)

    while _running:
        try:
            await submit_batch()
        except Exception as e:
            logger.error("chain_worker: batch failed: %s", e)
        await asyncio.sleep(settings.chain_submit_interval_seconds)


async def submit_batch(limit: int = _BATCH_SIZE) -> int:
    """Submit one batch. Returns the number of entries confirmed."""
    client = get_client()
    if client is None or not client.is_ready:
        return 0

    entries = await db.claim_pending_proofs(limit=limit)
    if not entries:
        # Opportunistically recover anything stranded by an earlier crash.
        await db.reclaim_stuck_proofs(older_than_seconds=_STUCK_AFTER_SECONDS)
        return 0

    confirmed = 0
    for entry in entries:
        confirmed += await _submit_one(client, entry)
    return confirmed


async def _submit_one(client, entry: dict) -> int:
    task_id = entry["task_id"]
    try:
        # web3 is synchronous — keep the event loop free while the tx lands.
        receipt = await asyncio.to_thread(
            client.record_proof, task_id, entry["agent_role"], entry["result_hash"]
        )
    except Exception as e:
        receipt = None
        logger.warning("chain_worker: %s raised during submit: %s", task_id, e)

    if not receipt:
        status = await db.mark_proof_failed(task_id, "chain submission failed")
        events.emit(economy.ECONOMY_CHANNEL, "proof_failed", {
            "task_id": task_id, "goal_id": entry["goal_id"],
            "agent_role": entry["agent_role"], "status": status,
        })
        return 0

    # An already-recorded proof carries no tx hash — the chain stores the result, not the
    # transaction that delivered it. Keep whatever we recorded the first time round rather
    # than overwriting settled history with a null.
    tx_hash = receipt.get("tx_hash") or entry.get("tx_hash") or ""
    block_number = receipt.get("block_number") or entry.get("block_number") or 0

    await db.mark_proof_confirmed(
        task_id,
        tx_hash=tx_hash,
        block_number=block_number,
        chain_id=receipt["chain_id"],
    )
    payload = {
        "task_id": task_id,
        "goal_id": entry["goal_id"],
        "agent_role": entry["agent_role"],
        "result_hash": entry["result_hash"],
        "tx_hash": tx_hash,
        "block_number": block_number,
        "chain_id": receipt["chain_id"],
        "explorer_url": client.tx_url(tx_hash),
        "already_recorded": receipt.get("already_recorded", False),
    }
    events.emit(economy.ECONOMY_CHANNEL, "proof_confirmed", payload)
    logger.info(
        "chain_worker: proof for %s confirmed in block %s (tx %s)",
        task_id, block_number, (tx_hash or "already-recorded")[:14],
    )
    return 1
