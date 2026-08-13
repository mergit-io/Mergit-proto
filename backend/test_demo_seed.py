"""Boot-time seeding for hosts with no persistent disk."""
import asyncio
import importlib
import os
import tempfile

import pytest


@pytest.fixture()
def fresh(monkeypatch):
    """A brand-new database, the way a restarted ephemeral container sees one."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("config.settings.db_path", os.path.join(tmp, "t.db"))
    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)
    import demo_seed as _seed
    importlib.reload(_seed)
    asyncio.get_event_loop().run_until_complete(_db.init_db())
    asyncio.get_event_loop().run_until_complete(_ec.seed_passports())
    return _db, _seed


def test_seeds_an_empty_ledger(fresh):
    db, demo_seed = fresh
    assert asyncio.get_event_loop().run_until_complete(demo_seed.seed_if_empty()) is True
    proofs = asyncio.get_event_loop().run_until_complete(db.list_proofs(limit=10))
    assert len(proofs) == 3
    assert {p["agent_role"] for p in proofs} == {"researcher", "coder", "integrator"}


def test_does_not_seed_twice(fresh):
    """Restart with a persistent disk must not pile up a fresh demo goal every boot."""
    db, demo_seed = fresh
    loop = asyncio.get_event_loop()
    assert loop.run_until_complete(demo_seed.seed_if_empty()) is True
    assert loop.run_until_complete(demo_seed.seed_if_empty()) is False
    assert len(loop.run_until_complete(db.list_proofs(limit=10))) == 3


def test_replaying_twice_does_not_collide_on_task_ids(fresh):
    """Task ids are per-run; a fixed set would fail the UNIQUE constraint on replay two."""
    db, demo_seed = fresh
    loop = asyncio.get_event_loop()
    loop.run_until_complete(demo_seed.replay())
    loop.run_until_complete(demo_seed.replay())
    assert len(loop.run_until_complete(db.list_proofs(limit=10))) == 6


def test_seed_failure_never_stops_the_app_booting(fresh, monkeypatch):
    _, demo_seed = fresh
    monkeypatch.setattr(demo_seed, "replay",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("chain exploded")))
    assert asyncio.get_event_loop().run_until_complete(demo_seed.seed_if_empty()) is False
