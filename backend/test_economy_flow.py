import asyncio
import os
import tempfile
import types

import pytest


@pytest.fixture()
def env(monkeypatch):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "test.db")
    import config
    monkeypatch.setattr(config.settings, "db_path", path)
    import importlib
    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)
    asyncio.get_event_loop().run_until_complete(_db.init_db())
    return _db, _ec


def test_seed_passports_creates_all_roles(env):
    db, ec = env
    async def go():
        await ec.seed_passports()
        ps = await db.list_passports()
        roles = {p["role"] for p in ps}
        assert roles == set(ec.ROLES)
    asyncio.get_event_loop().run_until_complete(go())


def test_record_proof_idempotent_and_updates_rep(env):
    db, ec = env
    async def go():
        await ec.seed_passports()
        task = types.SimpleNamespace(id="tX", goal_id="gX", agent_name="coder")
        p1 = await ec.record_proof(task, {"result": "ok"})
        p2 = await ec.record_proof(task, {"result": "ok"})
        assert p1 is not None
        assert p2 is None  # idempotent — already minted
        rep = await db.get_reputation("coder")
        assert rep is not None
        assert 0 <= rep["composite"] <= 1000
        proofs = await db.list_proofs_for_role("coder")
        assert len(proofs) == 1
    asyncio.get_event_loop().run_until_complete(go())
