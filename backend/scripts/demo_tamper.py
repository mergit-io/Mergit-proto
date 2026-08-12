"""Live demo: prove that a completed task's output cannot be altered after the fact.

    .venv/bin/python scripts/demo_tamper.py

Picks the most recent proven task, verifies it, rewrites its stored output directly in
SQLite behind the system's back, verifies again to show the mismatch, then restores it.

This is the concrete answer to PRD Problem 1 ("no verifiability"): the check is a hash
recomputed from the database and compared against contract state, so anyone can redo it.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

import db  # noqa: E402
import economy  # noqa: E402

API = "http://localhost:8000"

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"

FORGED = {"summary": "I definitely fixed everything", "key_points": ["trust me"], "sources": []}


def rule(title: str) -> None:
    print(f"\n{BOLD}── {title} {'─' * max(0, 58 - len(title))}{RESET}")


def verify(task_id: str) -> dict:
    """Verify through the running backend.

    CHAIN_TARGET=local runs the EVM inside the backend process, so this script - a
    separate process - cannot read that chain directly. The API can, and going through it
    is also a more honest demo: it is the same endpoint any observer would use.
    """
    return httpx.get(f"{API}/api/economy/verify/{task_id}", timeout=20).json()


async def set_output(task_id: str, output: dict) -> None:
    async with db.get_conn() as conn:
        await conn.execute("UPDATE tasks SET output=? WHERE id=?",
                           (json.dumps(output), task_id))
        await conn.commit()


async def main() -> int:
    await db.init_db()
    try:
        httpx.get(f"{API}/api/health", timeout=10)
    except Exception:
        print(f"{RED}Backend not reachable at {API} — start it with `python main.py`.{RESET}")
        return 2

    proofs = await db.list_proofs(limit=25)
    target = None
    for proof in proofs:
        task = await db.get_task(proof["task_id"])
        if task and task.output and verify(task.id).get("verified") is True:
            target = task
            break

    if target is None:
        print(f"{RED}No proven task found. Run scripts/replay_demo.py first.{RESET}")
        return 2

    original = target.output
    entry = await db.get_outbox_entry(target.id)

    rule("1. A task that an agent completed")
    print(f"task   : {target.id}")
    print(f"agent  : {target.agent_name}")
    print(f"output : {json.dumps(original)[:100]}")
    if entry and entry["tx_hash"]:
        print(f"tx     : {entry['tx_hash']}")
        print(f"block  : {entry['block_number']}  on chainId {entry['chain_id']}")

    rule("2. Verify it — recompute the hash, compare against the contract")
    r = verify(target.id)
    print(f"computed sha256 : {r['computed_hash']}")
    print(f"on-chain sha256 : {r['onchain_hash']}")
    print(f"\n{GREEN}✓ VERIFIED — the stored output is exactly what was proven.{RESET}"
          if r["verified"] else f"\n{RED}unexpected mismatch before tampering{RESET}")

    rule("3. Now tamper — rewrite the output directly in the database")
    print(f"{DIM}UPDATE tasks SET output='{json.dumps(FORGED)[:60]}…' WHERE id='{target.id}'{RESET}")
    await set_output(target.id, FORGED)
    print("done — the application was bypassed entirely.")

    rule("4. Verify again")
    r = verify(target.id)
    print(f"computed sha256 : {r['computed_hash']}")
    print(f"on-chain sha256 : {r['onchain_hash']}")
    if not r["verified"]:
        print(f"\n{RED}✗ MISMATCH — the output was altered after the proof was recorded.{RESET}")
        print(f"{RED}  The forgery is detected. The chain still holds the original hash.{RESET}")
    else:
        print(f"\n{RED}TAMPERING WENT UNDETECTED — this is a bug.{RESET}")
        return 1

    rule("5. Restore")
    await set_output(target.id, original)
    ok = verify(target.id).get("verified") is True
    print(f"{GREEN}✓ restored and verifying again.{RESET}" if ok else f"{RED}restore failed{RESET}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
