"""Verification endpoint tests — the credibility feature.

Answers PRD Problem 1 ("no verifiability") concretely: recompute the hash from the stored
output, read the chain, compare, and expose every intermediate value so a human can redo it.
"""
import asyncio
import importlib
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def ctx(monkeypatch):
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
    from api import economy as _api
    importlib.reload(_api)

    asyncio.run(_db.init_db())
    asyncio.run(_ec.seed_passports())

    app = FastAPI()
    app.include_router(_api.router)

    class Ctx:
        db, economy, chain_worker = _db, _ec, _cw
        http = TestClient(app)

    return Ctx()


def _seed_completed_task(ctx, output, task_id="t1", role="coder"):
    """Create a goal + DONE task with a real stored output."""
    async def go():
        goal = await ctx.db.create_goal("verify me")
        await ctx.db.create_tasks(
            [{"id": task_id, "agent": role, "description": "d", "inputs": {}, "depends_on": []}],
            goal.id, "trace")
        await ctx.db.settle_task(task_id, ctx.db.TaskStatus.DONE, output=output) \
            if hasattr(ctx.db, "settle_task") else None
        async with ctx.db.get_conn() as conn:
            import json as _json
            await conn.execute("UPDATE tasks SET status='DONE', output=? WHERE id=?",
                               (_json.dumps(output), task_id))
            await conn.commit()
        return goal.id
    return asyncio.run(go())


# ── Happy path ──────────────────────────────────────────────────────────────────

def test_verified_proof_reports_matching_hashes(ctx):
    output = {"summary": "Patched the token refresh guard", "files": ["auth.py"]}
    goal_id = _seed_completed_task(ctx, output)

    asyncio.run(ctx.economy.record_proof(
        type("T", (), {"id": "t1", "goal_id": goal_id, "agent_name": "coder"})(), output))
    asyncio.run(ctx.chain_worker.submit_batch())

    r = ctx.http.get("/api/economy/verify/t1")
    assert r.status_code == 200
    body = r.json()

    assert body["verified"] is True
    assert body["computed_hash"] == body["onchain_hash"] == ctx.economy.result_hash(output)
    assert body["tx_hash"].startswith("0x")
    assert body["block_number"] > 0
    assert body["chain_id"] > 0


def test_verification_exposes_intermediates_for_manual_audit(ctx):
    """A verifier must be able to redo the computation by hand — so show the inputs."""
    output = {"b": 2, "a": 1}
    goal_id = _seed_completed_task(ctx, output)
    asyncio.run(ctx.economy.record_proof(
        type("T", (), {"id": "t1", "goal_id": goal_id, "agent_name": "coder"})(), output))
    asyncio.run(ctx.chain_worker.submit_batch())

    body = ctx.http.get("/api/economy/verify/t1").json()
    assert body["canonical_output"] == ctx.economy.canonical_json(output)
    assert body["hash_algorithm"] == "sha256"
    assert body["task_key_algorithm"] == "keccak256"


# ── Tamper detection ────────────────────────────────────────────────────────────

def test_tampered_output_fails_verification(ctx):
    original = {"summary": "original result"}
    goal_id = _seed_completed_task(ctx, original)
    asyncio.run(ctx.economy.record_proof(
        type("T", (), {"id": "t1", "goal_id": goal_id, "agent_name": "coder"})(), original))
    asyncio.run(ctx.chain_worker.submit_batch())

    async def tamper():
        import json as _json
        async with ctx.db.get_conn() as conn:
            await conn.execute("UPDATE tasks SET output=? WHERE id=?",
                               (_json.dumps({"summary": "forged result"}), "t1"))
            await conn.commit()
    asyncio.run(tamper())

    body = ctx.http.get("/api/economy/verify/t1").json()
    assert body["verified"] is False
    assert body["computed_hash"] != body["onchain_hash"]


# ── Degradation ─────────────────────────────────────────────────────────────────

def test_unknown_task_is_404(ctx):
    assert ctx.http.get("/api/economy/verify/nope").status_code == 404


def test_task_without_onchain_proof_is_unverified_not_an_error(ctx):
    _seed_completed_task(ctx, {"summary": "never submitted"})
    r = ctx.http.get("/api/economy/verify/t1")

    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is None            # unknown, not false
    assert body["reason"] == "not_recorded"
    assert body["computed_hash"]               # still shown, so the user sees what would be proven
