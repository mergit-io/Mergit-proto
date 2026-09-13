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

import db  # noqa: E402
import economy  # noqa: E402
from state import GoalStatus, TaskStatus  # noqa: E402

CANNED_TASKS = [
    {"id": "replay_t1", "agent": "researcher",
     "description": "Research the Mergit agent economy design"},
    {"id": "replay_t2", "agent": "coder",
     "description": "Implement the proof-of-work ledger", "depends_on": ["replay_t1"]},
    {"id": "replay_t3", "agent": "integrator",
     "description": "Wire the ledger into the live SSE stream", "depends_on": ["replay_t2"]},
]

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

    goal = await db.create_goal("Replay demo: ship the Mergit agent economy")
    tasks = await db.create_tasks(CANNED_TASKS, goal.id, goal.trace_id)
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
