"""Deterministic offline demo for the Mergit showcase.

Seeds a canned goal + 3 completed tasks (researcher -> coder -> integrator)
and mints a proof for each via the economy engine, with a short delay so
the Proof Ledger and Leaderboard on /app/economy animate live. No LLM calls.

Run from backend/:  .venv/bin/python scripts/replay_demo.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid  # noqa: E402

import db  # noqa: E402
import economy  # noqa: E402
from state import GoalStatus, TaskStatus  # noqa: E402

# Task ids are generated per run — a fixed id set makes the second replay die on
# "UNIQUE constraint failed: tasks.id", which is exactly when a demo needs it most.
CANNED_TASK_SPECS = [
    ("researcher", "Research the Mergit agent economy design"),
    ("coder", "Implement the proof-of-work ledger"),
    ("integrator", "Wire the ledger into the live SSE stream"),
]


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

DELAY_SECONDS = 2

# Deterministic canned outputs per role, so the same replay always hashes the same.
CANNED_OUTPUTS = {
    "researcher": {"summary": "Located the design in the spec",
                   "key_points": ["passports", "reputation", "proofs"]},
    "coder": {"text": "Implemented the proof-of-work ledger", "title": "Fix"},
    "integrator": {"pr_url": "https://github.com/mergit-io/Mergit-proto/pull/1",
                   "comment": "PR opened"},
}


async def main() -> None:
    await db.init_db()
    await economy.seed_passports()

    run_id = uuid.uuid4().hex[:8]
    goal = await db.create_goal("Replay demo: ship the Mergit agent economy")
    tasks = await db.create_tasks(build_tasks(run_id), goal.id, goal.trace_id)
    await db.update_goal_status(goal.id, GoalStatus.RUNNING)
    print(f"Seeded goal {goal.id} with {len(tasks)} tasks — open /app/economy to watch the ledger.")

    for task in tasks:
        output = CANNED_OUTPUTS.get(
            task.agent_name, {"summary": f"{task.agent_name} completed (replay)"})
        await db.settle_task(task.id, TaskStatus.DONE, output=output)
        await db.promote_ready_tasks(goal.id)

        proof = await economy.record_proof(task, output)
        if proof:
            print(f"  minted proof {proof['tx_hash'][:18]}… for {task.agent_name} "
                  f"— block {proof['block_number']}")
        else:
            print(f"  proof for {task.agent_name}: skipped (already minted)")

        await asyncio.sleep(DELAY_SECONDS)

    await db.update_goal_status(goal.id, GoalStatus.COMPLETED)
    print("Replay complete — 3 proofs minted.")


if __name__ == "__main__":
    asyncio.run(main())
