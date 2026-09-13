"""End-to-end: a completed task becomes a real on-chain transaction.

This is the integration that the whole milestone exists for — economy.record_proof →
outbox → chain_worker → ProofOfWork.sol → verifiable receipt.
"""
import asyncio
import importlib
import os
import tempfile
import types

import pytest


@pytest.fixture()
def env(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "test.db"))

    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)

    from chain.client import ChainClient, set_client
    from chain.deployer import deploy_all
    from chain.provider import LocalEvmProvider

    provider = LocalEvmProvider()
    client = ChainClient(provider, deploy_all(provider))
    set_client(client)

    import chain_worker as _cw
    importlib.reload(_cw)

    asyncio.run(_db.init_db())
    asyncio.run(_ec.seed_passports())
    return types.SimpleNamespace(db=_db, economy=_ec, chain_worker=_cw, client=client)


def _task(task_id="g1_t1", goal_id="g1", role="coder"):
    return types.SimpleNamespace(id=task_id, goal_id=goal_id, agent_name=role)


def test_completed_task_lands_on_chain(env):
    async def go():
        output = {"summary": "Fixed the null check in auth.py", "files": ["auth.py"]}

        proof = await env.economy.record_proof(_task(), output)
        assert proof is not None

        entry = await env.db.get_outbox_entry("g1_t1")
        assert entry["status"] == "pending", "record_proof must queue a chain submission"

        confirmed = await env.chain_worker.submit_batch()
        assert confirmed == 1

        entry = await env.db.get_outbox_entry("g1_t1")
        assert entry["status"] == "confirmed"
        assert entry["tx_hash"].startswith("0x") and len(entry["tx_hash"]) == 66
        assert entry["block_number"] > 0

        # The hash on chain is the hash of the real agent output.
        onchain = env.client.get_proof("g1_t1")
        assert onchain["result_hash"] == env.economy.result_hash(output)
        assert env.client.verify("g1_t1", env.economy.result_hash(output)) is True

    asyncio.run(go())


def test_tampering_with_stored_output_breaks_verification(env):
    """The whole point of the proof: you cannot change the output after the fact."""
    async def go():
        output = {"summary": "original"}
        await env.economy.record_proof(_task(), output)
        await env.chain_worker.submit_batch()

        tampered_hash = env.economy.result_hash({"summary": "rewritten after the fact"})
        assert env.client.verify("g1_t1", tampered_hash) is False

    asyncio.run(go())


def test_chain_failure_does_not_break_the_goal(env, monkeypatch):
    """A dead chain must degrade to a retryable queue entry, never an exception."""
    async def go():
        monkeypatch.setattr(
            env.client, "record_proof",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("RPC unreachable")))

        proof = await env.economy.record_proof(_task(), {"summary": "ok"})
        assert proof is not None, "the local economy proof must still be minted"

        confirmed = await env.chain_worker.submit_batch()
        assert confirmed == 0

        entry = await env.db.get_outbox_entry("g1_t1")
        assert entry["status"] == "pending"      # queued for retry, not lost
        assert entry["attempts"] == 1

    asyncio.run(go())


def test_resubmission_after_restart_is_idempotent(env):
    """Reclaim/restart can re-submit an already-recorded task; the chain rejects the
    duplicate and the worker treats that as success rather than a failure."""
    async def go():
        await env.economy.record_proof(_task(), {"summary": "ok"})
        await env.chain_worker.submit_batch()
        first_tx = (await env.db.get_outbox_entry("g1_t1"))["tx_hash"]

        # Force a re-submission of the same task.
        await env.db.mark_proof_failed("g1_t1", "simulated crash", now=0)
        assert await env.chain_worker.submit_batch() == 1

        entry = await env.db.get_outbox_entry("g1_t1")
        assert entry["status"] == "confirmed"
        assert entry["tx_hash"] == first_tx, "history must not be rewritten"

    asyncio.run(go())


def test_multiple_agents_each_get_a_passport_and_proof(env):
    async def go():
        for i, role in enumerate(["researcher", "coder", "integrator"], start=1):
            await env.economy.record_proof(_task(f"g1_t{i}", "g1", role), {"step": i})

        assert await env.chain_worker.submit_batch(limit=10) == 3

        token_ids = {role: env.client.ensure_passport(role)
                     for role in ["researcher", "coder", "integrator"]}
        assert len(set(token_ids.values())) == 3, "each role needs its own passport"

        for i in range(1, 4):
            assert env.client.get_proof(f"g1_t{i}") is not None

    asyncio.run(go())
