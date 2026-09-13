"""Independently verify that a task's stored output matches its on-chain proof.

    .venv/bin/python scripts/verify_proof.py <task_id>
    .venv/bin/python scripts/verify_proof.py <task_id> --api http://localhost:8000
    .venv/bin/python scripts/verify_proof.py <task_id> --direct

Recomputes sha256(canonical_json(output)) from the database, reads ProofOfWork.getProof
from the chain, and compares. Prints every intermediate so the result can be checked by hand.

Note on CHAIN_TARGET=local: that EVM runs *inside* the backend process, so a separate CLI
process cannot see it — there is no shared node to connect to. The CLI therefore verifies
through the running server's API by default on local, and talks to the chain directly on a
real network (where the chain is external and any process can read it).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import economy  # noqa: E402
from chain import networks  # noqa: E402
from config import settings  # noqa: E402

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _print_common(task_id, agent, status, canonical, computed):
    print(f"\n── Proof verification: {task_id} ──")
    print(f"agent            : {agent}")
    print(f"task status      : {status}")
    shown = canonical if len(canonical) <= 120 else canonical[:120] + "…"
    print(f"{DIM}canonical output : {shown}{RESET}")
    print(f"computed sha256  : {computed}")


def _verdict(computed: str, onchain: str | None) -> int:
    if not onchain:
        print(f"\n{YELLOW}No on-chain proof recorded for this task yet.{RESET}\n")
        return 3
    print(f"on-chain sha256  : {onchain}")
    if onchain == computed:
        print(f"\n{GREEN}✓ VERIFIED — the stored output is exactly what was proven on chain.{RESET}\n")
        return 0
    print(f"\n{RED}✗ MISMATCH — the stored output does not match the on-chain proof.{RESET}")
    print(f"{RED}  The output was altered after the proof was recorded.{RESET}\n")
    return 1


def verify_via_api(task_id: str, base_url: str) -> int:
    """Ask the running backend, which owns the chain when it is in-process."""
    import httpx

    url = f"{base_url.rstrip('/')}/api/economy/verify/{task_id}"
    try:
        response = httpx.get(url, timeout=15)
    except Exception as e:
        print(f"\n{RED}Could not reach the backend at {base_url}: {e}{RESET}")
        print("Start it with `.venv/bin/python main.py`, or pass --api <url>.\n")
        return 4

    if response.status_code == 404:
        print(f"{RED}Unknown task {task_id!r}{RESET}")
        return 2
    if response.status_code != 200:
        print(f"{RED}Backend returned {response.status_code}: {response.text[:200]}{RESET}")
        return 4

    body = response.json()
    _print_common(task_id, body["agent_role"], body["task_status"],
                  body["canonical_output"], body["computed_hash"])
    if body.get("submission_status"):
        print(f"submission       : {body['submission_status']}")
    if body.get("tx_hash"):
        print(f"tx hash          : {body['tx_hash']}")
    if body.get("block_number"):
        print(f"block number     : {body['block_number']}")
    if body.get("explorer_url"):
        print(f"explorer         : {body['explorer_url']}")
    if body.get("reason") == "chain_unavailable":
        print(f"\n{YELLOW}The backend reports no chain available.{RESET}\n")
        return 3
    print(f"{DIM}verified via     : {base_url}{RESET}")
    return _verdict(body["computed_hash"], body.get("onchain_hash"))


async def verify_direct(task_id: str) -> int:
    """Read the chain ourselves — correct whenever the chain is external."""
    from chain.client import get_client

    await db.init_db()
    task = await db.get_task(task_id)
    if not task:
        print(f"{RED}Unknown task {task_id!r}{RESET}")
        return 2

    output = task.output or {}
    canonical = economy.canonical_json(output)
    computed = economy.result_hash(output)
    _print_common(task_id, task.agent_name, task.status, canonical, computed)

    client = get_client()
    if client is None or not client.is_ready:
        status = client.status.value if client else "disabled"
        print(f"\n{YELLOW}Chain unavailable ({status}) — cannot verify.{RESET}\n")
        return 3

    entry = await db.get_outbox_entry(task_id)
    if entry:
        print(f"submission       : {entry['status']} (attempts {entry['attempts']})")
        if entry["tx_hash"]:
            print(f"tx hash          : {entry['tx_hash']}")
            if url := client.tx_url(entry["tx_hash"]):
                print(f"explorer         : {url}")

    onchain = client.get_proof(task_id)
    if onchain:
        print(f"block number     : {onchain['block_number']}")
        print(f"chain id         : {onchain['chain_id']}")
    return _verdict(computed, onchain["result_hash"] if onchain else None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a task's on-chain proof")
    parser.add_argument("task_id")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="backend base URL used when the chain is in-process")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--direct", action="store_true",
                      help="always read the chain directly, never via the API")
    mode.add_argument("--via-api", action="store_true",
                      help="always verify through the backend API")
    args = parser.parse_args()

    network = networks.get_network(settings.chain_target)
    use_api = args.via_api or (network.is_local and not args.direct)

    if use_api:
        if network.is_local and not args.via_api:
            print(f"{DIM}CHAIN_TARGET=local runs the EVM inside the backend process; "
                  f"verifying through {args.api}{RESET}")
        return verify_via_api(args.task_id, args.api)
    return asyncio.run(verify_direct(args.task_id))


if __name__ == "__main__":
    raise SystemExit(main())
