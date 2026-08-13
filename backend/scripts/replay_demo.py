"""Deterministic offline demo for the Mergit showcase.

Seeds a canned goal + 3 completed tasks (researcher -> coder -> integrator) and mints a
proof for each via the economy engine, with a short delay so the Proof Ledger and
Leaderboard on /app/economy animate live. No LLM calls.

The logic lives in `demo_seed.py` so that boot-time seeding (`SEED_DEMO=true`) and this
script cannot drift apart. This wrapper only adds the pacing and the printing.

Run from backend/:  .venv/bin/python scripts/replay_demo.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import demo_seed  # noqa: E402
import economy  # noqa: E402

DELAY_SECONDS = 2


async def main() -> None:
    await db.init_db()
    await economy.seed_passports()
    print("Seeding replay — open /app/economy to watch the ledger.")
    minted = await demo_seed.replay(delay_seconds=DELAY_SECONDS, emit=print)
    print(f"Replay complete — {minted} proofs minted.")


if __name__ == "__main__":
    asyncio.run(main())
