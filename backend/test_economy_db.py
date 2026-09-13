import asyncio
import os
import tempfile

import pytest


@pytest.fixture()
def fresh_db(monkeypatch):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "test.db")
    import config
    monkeypatch.setattr(config.settings, "db_path", path)
    import importlib
    import db as _db
    importlib.reload(_db)
    asyncio.get_event_loop().run_until_complete(_db.init_db())
    return _db


def test_passport_roundtrip(fresh_db):
    db = fresh_db
    async def go():
        await db.upsert_passport("coder", "did:mergit:agent:coder", 3, 1,
                                 ["code_exec", "file_ops"], "0xabc", 1000, 42)
        p = await db.get_passport("coder")
        assert p["role"] == "coder"
        assert p["token_id"] == 3
        assert p["capabilities"] == ["code_exec", "file_ops"]
    asyncio.get_event_loop().run_until_complete(go())


def test_proof_idempotent(fresh_db):
    db = fresh_db
    async def go():
        first = await db.insert_proof("t1", "g1", "coder", "hh", "0xtx", 100, 111)
        second = await db.insert_proof("t1", "g1", "coder", "hh", "0xtx", 100, 111)
        assert first is True
        assert second is False
        assert await db.max_proof_block() == 100
    asyncio.get_event_loop().run_until_complete(go())
