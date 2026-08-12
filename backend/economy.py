"""Simulated Monad agent-economy: passports, reputation, proof-of-work.

Deterministic — no RNG. Scores derive from real task history. This module never
raises into the worker: record_proof swallows its own errors.
"""
import hashlib
import json
import logging
import math
import time

import agent_registry

import db
import events

logger = logging.getLogger(__name__)

ROLES = ["orchestrator", "researcher", "writer", "coder", "integrator", "notifier"]

_ORCH_CAPS = ["decompose_goal", "plan_task_dag", "route_agents"]

CAPABILITIES = {
    role: (_ORCH_CAPS if role == "orchestrator"
           else agent_registry.AGENT_REGISTRY.get(role, {}).get("allowed_tools", []))
    for role in ROLES
}

# Score weights and baselines
_W_SUCCESS = 0.5
_W_SPEED = 0.2
_W_VOLUME = 0.3
_BASELINE_SEC = 20.0           # a task at/under this is "fast"
_VOLUME_SATURATION = 50.0      # tasks needed to max the volume component
_MINT_BASE_BLOCK = 18_000_000
_PROOF_BASE_BLOCK = 18_100_000

ECONOMY_CHANNEL = "economy"


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def result_hash(output) -> str:
    return hashlib.sha256(canonical_json(output).encode()).hexdigest()


def tx_hash(task_id: str, rhash: str) -> str:
    return "0x" + hashlib.sha256((task_id + rhash).encode()).hexdigest()[:64]


def owner_address(role: str) -> str:
    return "0x" + hashlib.sha256(role.encode()).hexdigest()[:40]


def did_for(role: str) -> str:
    return f"did:mergit:agent:{role}"


def mint_block_for(role: str) -> int:
    return _MINT_BASE_BLOCK + ROLES.index(role)


def compute_scores(done: int, failed: int, avg_duration_sec: float) -> dict:
    total = done + failed
    success_rate = (done / total) if total else 0.75  # neutral prior
    if avg_duration_sec <= 0:
        speed = 0.6
    else:
        speed = max(0.0, min(1.0, _BASELINE_SEC / avg_duration_sec))
    volume = min(1.0, math.log10(done + 1) / math.log10(_VOLUME_SATURATION + 1)) if done else 0.0
    raw = _W_SUCCESS * success_rate + _W_SPEED * speed + _W_VOLUME * volume
    composite = int(round(1000 * raw))
    composite = max(0, min(1000, composite))
    return {"success_rate": round(success_rate, 4), "speed": round(speed, 4),
            "volume": round(volume, 4), "composite": composite}


def badge_for(composite: int) -> str:
    if composite >= 800:
        return "Gold"
    if composite >= 600:
        return "Silver"
    return "Bronze"


def apply_delta_cap(prev_composite: int, new_composite: int) -> int:
    if prev_composite <= 0:
        return new_composite
    lo = int(prev_composite * 0.8)
    hi = int(prev_composite * 1.2)
    return max(lo, min(hi, new_composite))


# ── Orchestration: seed, recompute, record, backfill ────────────────────────────

async def seed_passports() -> None:
    now = int(time.time())
    for idx, role in enumerate(ROLES, start=1):
        existing = await db.get_passport(role)
        if existing:
            continue
        await db.upsert_passport(
            role=role, did=did_for(role), token_id=idx, soulbound=True,
            capabilities=CAPABILITIES.get(role, []), owner_address=owner_address(role),
            minted_at=now, mint_block=mint_block_for(role),
        )
    # Ensure every role has a reputation row so all 6 appear on the leaderboard,
    # even those with no task history yet (neutral prior). Never overwrites existing.
    for role in ROLES:
        if not await db.get_reputation(role):
            await recompute_role(role)


async def recompute_role(role: str) -> dict:
    agg = (await db.list_completed_tasks_by_role()).get(
        role, {"done": 0, "failed": 0, "avg_duration_sec": 0.0})
    scores = compute_scores(agg["done"], agg["failed"], agg["avg_duration_sec"])
    prev = await db.get_reputation(role)
    composite = apply_delta_cap(prev["composite"] if prev else 0, scores["composite"])
    badge = badge_for(composite)
    await db.upsert_reputation(role, composite, scores["success_rate"], scores["speed"],
                               scores["volume"], badge, int(time.time()))
    return {"role": role, "composite": composite, "badge": badge, **scores}


async def _next_block() -> int:
    top = await db.max_proof_block()
    base = max(top, _PROOF_BASE_BLOCK - 1)
    return base + 1


async def record_proof(task, output) -> dict | None:
    """Mint a proof for a completed task and refresh its agent's reputation.
    Never raises — logs and returns None on any failure."""
    try:
        role = task.agent_name
        if role not in ROLES:
            return None
        if await db.get_proof(task.id):
            return None  # idempotent
        rhash = result_hash(output or {})
        tx = tx_hash(task.id, rhash)
        block = await _next_block()
        now = int(time.time())
        inserted = await db.insert_proof(task.id, task.goal_id, role, rhash, tx, block, now)
        if not inserted:
            return None
        proof = {"task_id": task.id, "goal_id": task.goal_id, "agent_role": role,
                 "result_hash": rhash, "tx_hash": tx, "block_number": block, "recorded_at": now}
        rep = await recompute_role(role)
        events.emit(ECONOMY_CHANNEL, "proof_recorded", dict(proof))
        events.emit(ECONOMY_CHANNEL, "reputation_update", dict(rep))

        # Queue the real on-chain submission. Deliberately after the local proof is durable:
        # the ledger updates instantly while the chain settles asynchronously (PRD §5.4).
        try:
            if await db.enqueue_proof(task.id, task.goal_id, role, rhash):
                events.emit(ECONOMY_CHANNEL, "proof_pending", {
                    "task_id": task.id, "goal_id": task.goal_id,
                    "agent_role": role, "result_hash": rhash,
                })
        except Exception as e:
            logger.warning("economy: failed to enqueue chain proof for %s: %s", task.id, e)

        return proof
    except Exception as e:  # never break the worker
        logger.warning("economy.record_proof failed for task %s: %s", getattr(task, "id", "?"), e)
        return None


async def backfill() -> None:
    """One-time: mint proofs for historical DONE tasks so pages are populated."""
    if await db.max_proof_block() > 0:
        return
    by_role = await db.list_completed_tasks_by_role()
    block = _PROOF_BASE_BLOCK
    for role, agg in by_role.items():
        if role not in ROLES:
            continue
        for row in sorted(agg["completed_task_rows"], key=lambda r: r["created_at"]):
            rhash = result_hash(row["output"])
            tx = tx_hash(row["id"], rhash)
            block += 1
            await db.insert_proof(row["id"], row["goal_id"], role, rhash, tx, block,
                                  row["updated_at"] or row["created_at"])
    for role in ROLES:
        await recompute_role(role)
