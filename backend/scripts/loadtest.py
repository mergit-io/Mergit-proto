"""Simulate N concurrent dashboard users against a running Mergit.

Each user holds an SSE stream open (that is what the Economy and GoalDetail pages do)
while polling the same endpoints SWR polls, at SWR's 5s interval. Reports p50/p95/max
latency per endpoint and any failures — the numbers that decide whether a free tier can
carry the load, rather than a guess about it.
"""
import argparse
import asyncio
import statistics
import time

import httpx

POLLED = [
    "/api/goals",
    "/api/economy/leaderboard",
    "/api/economy/passports",
    "/api/economy/proofs?limit=50",
    "/api/economy/chain/status",
    "/api/heal/stats",
]

latencies: dict[str, list[float]] = {p: [] for p in POLLED}
errors: list[str] = []
sse_events = 0


async def sse_user(base: str, stop: float) -> None:
    """Hold an economy SSE stream open, like an open Economy tab."""
    global sse_events
    try:
        async with httpx.AsyncClient(timeout=None) as c:
            async with c.stream("GET", f"{base}/api/economy/stream") as r:
                if r.status_code != 200:
                    errors.append(f"sse status {r.status_code}")
                    return
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        sse_events += 1
                    if time.monotonic() > stop:
                        return
    except Exception as e:
        errors.append(f"sse {type(e).__name__}: {e}")


async def poll_user(base: str, stop: float) -> None:
    async with httpx.AsyncClient(timeout=20) as c:
        while time.monotonic() < stop:
            for path in POLLED:
                t0 = time.perf_counter()
                try:
                    r = await c.get(base + path)
                    dt = time.perf_counter() - t0
                    if r.status_code != 200:
                        errors.append(f"{path} -> {r.status_code}")
                    else:
                        latencies[path].append(dt)
                except Exception as e:
                    errors.append(f"{path} {type(e).__name__}: {e}")
            await asyncio.sleep(5)  # SWR refreshInterval


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=30)
    args = ap.parse_args()

    stop = time.monotonic() + args.seconds
    print(f"{args.users} concurrent users for {args.seconds:.0f}s against {args.base}")
    tasks = []
    for _ in range(args.users):
        tasks.append(asyncio.create_task(sse_user(args.base, stop)))
        tasks.append(asyncio.create_task(poll_user(args.base, stop)))
    await asyncio.gather(*tasks)

    total = sum(len(v) for v in latencies.values())
    print(f"\n{total} requests, {len(errors)} errors, {sse_events} SSE events\n")
    print(f"{'endpoint':34} {'n':>5} {'p50':>8} {'p95':>8} {'max':>8}")
    for path, vals in latencies.items():
        print(f"{path:34} {len(vals):5} {pct(vals, .5)*1000:7.1f}ms "
              f"{pct(vals, .95)*1000:7.1f}ms {max(vals or [0])*1000:7.1f}ms")
    if errors:
        print("\nfirst errors:")
        for e in errors[:10]:
            print("  ", e)


if __name__ == "__main__":
    asyncio.run(main())
