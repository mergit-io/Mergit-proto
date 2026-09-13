"""Deterministic demo data: one canned goal, three completed tasks, three minted proofs.

Exists because the free hosting tiers have no persistent disk. Every restart wipes the
SQLite file and the in-process chain, so without this a visitor arrives at an empty
dashboard and an empty ledger — the two screens the whole project is meant to show off.

Seeding beats committing a populated database. A checked-in db carries proofs whose chain
entries died with the process that recorded them, so every Verify button would answer
`verified: null`. Regenerating mints proofs against the chain that is running *now*, so
verification actually passes.

No LLM calls, no keys, no network. `scripts/replay_demo.py` is a thin wrapper around this.
"""
import logging
import uuid

import db
import economy
from state import GoalStatus, TaskStatus

logger = logging.getLogger(__name__)

# Task ids are generated per run — a fixed id set makes the second replay die on
# "UNIQUE constraint failed: tasks.id", which is exactly when a demo needs it most.
CANNED_TASK_SPECS = [
    ("researcher", "Research the Mergit agent economy design"),
    ("coder", "Implement the proof-of-work ledger"),
    ("integrator", "Wire the ledger into the live SSE stream"),
]

# Deterministic canned outputs per role, so the same replay always hashes the same.
CANNED_OUTPUTS = {
    "researcher": {"summary": "Located the design in the spec",
                   "key_points": ["passports", "reputation", "proofs"]},
    "coder": {"text": "Implemented the proof-of-work ledger", "title": "Fix"},
    "integrator": {"pr_url": "https://github.com/mergit-io/Mergit-proto/pull/1",
                   "comment": "PR opened"},
}

GOAL_TEXT = "Replay demo: ship the Mergit agent economy"


def build_tasks(run_id: str) -> list[dict]:
    tasks = []
    previous = None
    for index, (agent, description) in enumerate(CANNED_TASK_SPECS, start=1):
        task_id = f"replay_{run_id}_t{index}"
        tasks.append({
            "id": task_id, "agent": agent, "description": description,
            "depends_on": [previous] if previous else [],
        })
        previous = task_id
    return tasks


async def replay(delay_seconds: float = 0, emit=logger.info) -> int:
    """Seed a goal, settle its tasks and mint a proof for each. Returns proofs minted.

    `delay_seconds` paces the mints so the Proof Ledger and Leaderboard animate live when
    a human is watching; boot-time seeding passes 0.
    """
    import asyncio

    run_id = uuid.uuid4().hex[:8]
    goal = await db.create_goal(GOAL_TEXT)
    tasks = await db.create_tasks(build_tasks(run_id), goal.id, goal.trace_id)
    await db.update_goal_status(goal.id, GoalStatus.RUNNING)
    emit(f"Seeded goal {goal.id} with {len(tasks)} tasks")

    minted = 0
    for task in tasks:
        output = CANNED_OUTPUTS.get(
            task.agent_name, {"summary": f"{task.agent_name} completed (replay)"})
        await db.settle_task(task.id, TaskStatus.DONE, output=output)
        await db.promote_ready_tasks(goal.id)

        proof = await economy.record_proof(task, output)
        if proof:
            minted += 1
            emit(f"  minted proof {proof['tx_hash'][:18]}… for {task.agent_name} "
                 f"— block {proof['block_number']}")
        else:
            emit(f"  proof for {task.agent_name}: skipped (already minted)")

        if delay_seconds:
            await asyncio.sleep(delay_seconds)

    await db.update_goal_status(goal.id, GoalStatus.COMPLETED)
    return minted


async def seed_if_empty() -> bool:
    """Seed only when the ledger has no proofs. Returns True if it seeded.

    Never raises into startup: a demo convenience must not be able to stop the app booting.
    """
    try:
        if await db.list_proofs(limit=1):
            logger.info("Demo seed skipped — the ledger already has proofs")
            return False
        minted = await replay()
        logger.info("Demo seed complete — %d proofs minted", minted)
        return True
    except Exception as e:
        logger.warning("Demo seed failed (continuing without it): %s", e)
        return False
