"""Deterministic offline demo for the Mergit showcase.

Seeds a canned goal + 3 completed tasks (researcher -> coder -> integrator)
and mints a proof for each via the economy engine, with a short delay so
the Proof Ledger and Leaderboard on /app/economy animate live. No LLM calls.

Run from backend/:  .venv/bin/python scripts/replay_demo.py

Depends on `economy.record_proof` (Workstream A / issue #1), which has not
landed in this repo yet. Goal/task seeding below uses only the existing
db.py API and is runnable today; the proof-minting loop will start working
the moment that module exists. Assumed interface (adjust the call below if
the real signature differs):

    async def record_proof(agent_name: str, task_id: str, goal_id: str,
                            reputation_delta: int) -> dict
    # -> {"proof_id", "agent_name", "task_id", "goal_id", "tx_hash",
    #     "block_number", "reputation_delta", "timestamp"}
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
from state import GoalStatus, TaskStatus

CANNED_TASKS = [
    {"id": "replay_t1", "agent": "researcher", "description": "Research the Mergit agent economy design"},
    {"id": "replay_t2", "agent": "coder", "description": "Implement the proof-of-work ledger", "depends_on": ["replay_t1"]},
    {"id": "replay_t3", "agent": "integrator", "description": "Wire the ledger into the live SSE stream", "depends_on": ["replay_t2"]},
]

REPUTATION_DELTA = 40
DELAY_SECONDS = 2


async def main() -> None:
    await db.init_db()

    goal = await db.create_goal("Replay demo: ship the Mergit agent economy")
    tasks = await db.create_tasks(CANNED_TASKS, goal.id, goal.trace_id)
    await db.update_goal_status(goal.id, GoalStatus.RUNNING)
    print(f"Seeded goal {goal.id} with {len(tasks)} tasks")

    try:
        from economy import record_proof
    except ImportError as e:
        raise SystemExit(
            "Goal/task seeding above succeeded. `economy.record_proof` isn't "
            "available yet (Workstream A / issue #1 hasn't landed) -- proof "
            "minting will work once that module exists."
        ) from e

    for task in tasks:
        await db.settle_task(task.id, TaskStatus.DONE, output={"summary": f"{task.agent_name} completed (replay)"})
        await db.promote_ready_tasks(goal.id)

        proof = await record_proof(
            agent_name=task.agent_name,
            task_id=task.id,
            goal_id=goal.id,
            reputation_delta=REPUTATION_DELTA,
        )
        print(
            f"Minted proof {proof['tx_hash']} for {task.agent_name} "
            f"— block {proof['block_number']}, +{REPUTATION_DELTA} REP"
        )

        await asyncio.sleep(DELAY_SECONDS)

    await db.update_goal_status(goal.id, GoalStatus.COMPLETED)
    print("Replay complete — 3 proofs minted.")


if __name__ == "__main__":
    asyncio.run(main())
