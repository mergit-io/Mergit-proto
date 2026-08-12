"""Proof outbox tests — durability of chain submission (PRD §5.4).

The outbox is what lets chain submission be slow, flaky or entirely offline without ever
blocking a goal run or losing a proof.
"""
import asyncio
import importlib
import os
import tempfile

import pytest


@pytest.fixture()
def db(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "test.db"))
    import db as _db
    importlib.reload(_db)
    asyncio.run(_db.init_db())
    return _db


def run(coro):
    return asyncio.run(coro)


# ── Enqueue ─────────────────────────────────────────────────────────────────────

def test_enqueue_creates_pending_entry(db):
    async def go():
        assert await db.enqueue_proof("t1", "g1", "coder", "a" * 64) is True
        entry = await db.get_outbox_entry("t1")
        assert entry["status"] == "pending"
        assert entry["attempts"] == 0
        assert entry["result_hash"] == "a" * 64
        assert entry["tx_hash"] is None
    run(go())


def test_enqueue_is_idempotent_per_task(db):
    async def go():
        assert await db.enqueue_proof("t1", "g1", "coder", "a" * 64) is True
        assert await db.enqueue_proof("t1", "g1", "coder", "a" * 64) is False
        assert len(await db.list_outbox()) == 1
    run(go())


# ── Claiming ────────────────────────────────────────────────────────────────────

def test_claim_moves_to_submitting_and_is_exclusive(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        await db.enqueue_proof("t2", "g1", "writer", "b" * 64)

        claimed = await db.claim_pending_proofs(limit=10)
        assert {c["task_id"] for c in claimed} == {"t1", "t2"}
        assert all(c["status"] == "submitting" for c in claimed)

        # A second drain must find nothing — no double submission.
        assert await db.claim_pending_proofs(limit=10) == []
    run(go())


def test_claim_respects_limit(db):
    async def go():
        for i in range(5):
            await db.enqueue_proof(f"t{i}", "g1", "coder", "a" * 64)
        assert len(await db.claim_pending_proofs(limit=2)) == 2
        assert len(await db.claim_pending_proofs(limit=10)) == 3
    run(go())


def test_claim_skips_entries_in_backoff(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        await db.claim_pending_proofs(limit=10)
        await db.mark_proof_failed("t1", "rpc down")   # schedules a retry in the future

        assert await db.claim_pending_proofs(limit=10) == []
        # ...but it is claimable once its backoff has elapsed
        assert len(await db.claim_pending_proofs(limit=10, now=2**31)) == 1
    run(go())


# ── Outcomes ────────────────────────────────────────────────────────────────────

def test_confirm_records_transaction_details(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        await db.claim_pending_proofs(limit=10)
        await db.mark_proof_confirmed("t1", tx_hash="0x" + "f" * 64,
                                      block_number=42, chain_id=10143)

        entry = await db.get_outbox_entry("t1")
        assert entry["status"] == "confirmed"
        assert entry["tx_hash"] == "0x" + "f" * 64
        assert entry["block_number"] == 42
        assert entry["chain_id"] == 10143
        assert entry["last_error"] is None
    run(go())


def test_failure_increments_attempts_and_returns_to_pending(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        await db.claim_pending_proofs(limit=10)
        await db.mark_proof_failed("t1", "connection refused")

        entry = await db.get_outbox_entry("t1")
        assert entry["status"] == "pending"       # retryable
        assert entry["attempts"] == 1
        assert "connection refused" in entry["last_error"]
        assert entry["next_attempt_at"] > 0
    run(go())


def test_backoff_grows_with_attempts(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        delays = []
        for _ in range(4):
            await db.claim_pending_proofs(limit=10, now=2**31)
            await db.mark_proof_failed("t1", "boom", now=1000)
            delays.append((await db.get_outbox_entry("t1"))["next_attempt_at"] - 1000)
        assert delays == sorted(delays), f"backoff must not shrink: {delays}"
        assert delays[-1] > delays[0]
    run(go())


def test_dead_letters_after_max_attempts(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        for _ in range(db.MAX_PROOF_ATTEMPTS):
            await db.claim_pending_proofs(limit=10, now=2**31)
            await db.mark_proof_failed("t1", "permanent failure")

        entry = await db.get_outbox_entry("t1")
        assert entry["status"] == "dead_lettered"
        assert entry["attempts"] == db.MAX_PROOF_ATTEMPTS
        # A dead-lettered entry is never retried again.
        assert await db.claim_pending_proofs(limit=10, now=2**31) == []
    run(go())


# ── Restart resumability ────────────────────────────────────────────────────────

def test_interrupted_submissions_are_recoverable(db):
    """A crash mid-submit leaves rows stuck in 'submitting' — they must be reclaimable."""
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        await db.claim_pending_proofs(limit=10)
        assert (await db.get_outbox_entry("t1"))["status"] == "submitting"

        reclaimed = await db.reclaim_stuck_proofs(older_than_seconds=0)
        assert reclaimed == 1
        assert (await db.get_outbox_entry("t1"))["status"] == "pending"
        assert len(await db.claim_pending_proofs(limit=10)) == 1
    run(go())


def test_pending_entries_survive_reconnect(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
    run(go())

    async def after_restart():
        entry = await db.get_outbox_entry("t1")
        assert entry is not None and entry["status"] == "pending"
    run(after_restart())


# ── Stats ───────────────────────────────────────────────────────────────────────

def test_stats_counts_by_status(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        await db.enqueue_proof("t2", "g1", "writer", "b" * 64)
        await db.claim_pending_proofs(limit=1)
        await db.mark_proof_confirmed("t1", "0x" + "1" * 64, 1, 31337)

        stats = await db.outbox_stats()
        assert stats["confirmed"] == 1
        assert stats["pending"] == 1
    run(go())


def test_list_outbox_filters_by_status(db):
    async def go():
        await db.enqueue_proof("t1", "g1", "coder", "a" * 64)
        await db.enqueue_proof("t2", "g1", "writer", "b" * 64)
        await db.claim_pending_proofs(limit=1)
        await db.mark_proof_confirmed("t1", "0x" + "1" * 64, 1, 31337)

        assert [e["task_id"] for e in await db.list_outbox(status="confirmed")] == ["t1"]
        assert [e["task_id"] for e in await db.list_outbox(status="pending")] == ["t2"]
    run(go())
