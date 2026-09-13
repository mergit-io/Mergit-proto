"""The ledger may only show chain values the chain actually issued.

`proofs.tx_hash` and `proofs.block_number` are simulated at insert time: the hash is
`sha256(task_id + result_hash)` and the block is a local counter seeded at 18,100,000.
Neither has ever existed on any chain. Real settlement lands in `proof_outbox`, and
`mark_proof_confirmed` writes only there — so a ledger that reads `proofs` and links
`{explorer}/tx/{tx_hash}` produces a link to a transaction that does not exist, for every
row, including rows that did settle.

These tests pin the boundary: the list endpoints expose the local counter as `sequence`,
and expose `tx_hash` / `block_number` / `chain_id` only from the outbox, only once
confirmed.
"""
import asyncio
import importlib
import os
import tempfile

import pytest


@pytest.fixture()
def stack(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "test.db"))

    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)
    asyncio.run(_db.init_db())

    class Stack:
        db, economy = _db, _ec

    return Stack()


def run(coro):
    return asyncio.run(coro)


async def _seed_proof(db, task_id="t1", role="coder", sequence=18_100_001,
                      goal_id=None, user_id=None):
    """Insert a proof the way `economy.record_proof` does — simulated hash and block."""
    import economy
    if goal_id is None:
        goal = await db.create_goal("ledger", user_id=user_id or db.LEGACY_USER_ID)
        goal_id = goal.id
    rhash = "a" * 64
    await db.insert_proof(task_id, goal_id, role, rhash,
                          economy.tx_hash(task_id, rhash), sequence, 1_700_000_000)
    return goal_id, rhash


def _only(rows, task_id):
    return next(r for r in rows if r["task_id"] == task_id)


# ── Never submitted ─────────────────────────────────────────────────────────────

def test_proof_with_no_outbox_entry_claims_no_chain_values(stack):
    """`economy.backfill()` mints proofs without enqueuing them. Those never settle."""
    db = stack.db

    async def go():
        await _seed_proof(db)
        row = _only(await db.list_proofs(limit=10), "t1")

        assert row["tx_hash"] is None
        assert row["block_number"] is None
        assert row["chain_id"] is None
        assert row["submission_status"] is None
        # The local counter is still there, under a name that cannot be read as a block.
        assert row["sequence"] == 18_100_001

    run(go())


def test_the_simulated_hash_never_reaches_the_response(stack):
    """The regression guard. Any field carrying `tx_hash(task, rhash)` is the bug."""
    db, economy = stack.db, stack.economy

    async def go():
        _, rhash = await _seed_proof(db)
        simulated = economy.tx_hash("t1", rhash)
        row = _only(await db.list_proofs(limit=10), "t1")

        assert simulated not in [v for v in row.values() if isinstance(v, str)]

    run(go())


# ── Queued but not settled ──────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["pending", "submitting", "dead_lettered"])
def test_unconfirmed_proof_shows_its_state_and_no_hash(stack, status):
    db = stack.db

    async def go():
        goal_id, rhash = await _seed_proof(db)
        await db.enqueue_proof("t1", goal_id, "coder", rhash)
        if status == "submitting":
            await db.claim_pending_proofs(limit=1)
        elif status == "dead_lettered":
            for _ in range(db.MAX_PROOF_ATTEMPTS):
                await db.mark_proof_failed("t1", "nope")

        row = _only(await db.list_proofs(limit=10), "t1")
        assert row["submission_status"] == status
        assert row["tx_hash"] is None
        assert row["block_number"] is None

    run(go())


# ── Settled ─────────────────────────────────────────────────────────────────────

def test_confirmed_proof_shows_the_real_hash_and_block(stack):
    db = stack.db

    async def go():
        goal_id, rhash = await _seed_proof(db)
        await db.enqueue_proof("t1", goal_id, "coder", rhash)
        await db.mark_proof_confirmed("t1", tx_hash="0xreal", block_number=7, chain_id=31337)

        row = _only(await db.list_proofs(limit=10), "t1")
        assert row["submission_status"] == "confirmed"
        assert row["tx_hash"] == "0xreal"
        assert row["block_number"] == 7          # the chain's block, not 18,100,001
        assert row["chain_id"] == 31337
        assert row["sequence"] == 18_100_001

    run(go())


def test_already_recorded_proof_confirms_without_inventing_a_hash(stack):
    """`chain_worker` confirms with an empty tx hash when the chain already had the result.

    The proof is genuinely settled, but no transaction of ours delivered it — so there is
    nothing to link to, and an empty string must not become a link to `{explorer}/tx/`.
    """
    db = stack.db

    async def go():
        goal_id, rhash = await _seed_proof(db)
        await db.enqueue_proof("t1", goal_id, "coder", rhash)
        await db.mark_proof_confirmed("t1", tx_hash="", block_number=9, chain_id=31337)

        row = _only(await db.list_proofs(limit=10), "t1")
        assert row["submission_status"] == "confirmed"
        assert row["tx_hash"] is None
        assert row["block_number"] == 9

    run(go())


# ── The join must not disturb what already worked ───────────────────────────────

def test_ordering_and_pagination_still_run_on_the_local_sequence(stack):
    """`before` pages on the local counter. Real blocks are sparse and arrive out of order,
    so paginating on them would skip or repeat rows."""
    db = stack.db

    async def go():
        goal = await db.create_goal("ledger", user_id=db.LEGACY_USER_ID)
        for i in (1, 2, 3):
            await _seed_proof(db, task_id=f"t{i}", sequence=18_100_000 + i, goal_id=goal.id)
        # Settle the oldest into a low real block — it must not jump to the top.
        await db.enqueue_proof("t1", goal.id, "coder", "a" * 64)
        await db.mark_proof_confirmed("t1", tx_hash="0xreal", block_number=2, chain_id=31337)

        rows = await db.list_proofs(limit=10)
        assert [r["task_id"] for r in rows] == ["t3", "t2", "t1"]

        page = await db.list_proofs(limit=10, before_block=18_100_003)
        assert [r["task_id"] for r in page] == ["t2", "t1"]

    run(go())


def test_role_listing_gets_the_same_treatment(stack):
    """`/economy/agents/{role}` renders through the same ProofLedger component."""
    db = stack.db

    async def go():
        goal_id, rhash = await _seed_proof(db, task_id="t1", role="coder")
        await db.enqueue_proof("t1", goal_id, "coder", rhash)

        row = _only(await db.list_proofs_for_role("coder", limit=10), "t1")
        assert row["submission_status"] == "pending"
        assert row["tx_hash"] is None
        assert row["sequence"] == 18_100_001

    run(go())


def test_tenancy_filter_survives_the_join(stack):
    """The join adds a table to the FROM clause; the visibility predicate must still bite."""
    db = stack.db

    async def go():
        me = await db.upsert_user("sub-me", "me@x.test", True)
        other = await db.upsert_user("sub-other", "other@x.test", True)
        mine = await db.create_goal("mine", user_id=me["id"])
        theirs = await db.create_goal("theirs", user_id=other["id"])
        await _seed_proof(db, task_id="t_mine", sequence=18_100_001, goal_id=mine.id)
        await _seed_proof(db, task_id="t_theirs", sequence=18_100_002, goal_id=theirs.id)

        visible = {r["task_id"] for r in await db.list_proofs(limit=10, user_id=me["id"])}
        assert visible == {"t_mine"}

    run(go())
