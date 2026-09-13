import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("config.settings.db_path", os.path.join(tmp, "t.db"))
    import importlib
    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)
    from api import economy as _api
    importlib.reload(_api)
    asyncio.get_event_loop().run_until_complete(_db.init_db())
    asyncio.get_event_loop().run_until_complete(_ec.seed_passports())
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(_api.router)
    return TestClient(app)


def test_passports_endpoint(client):
    r = client.get("/api/economy/passports")
    assert r.status_code == 200
    assert len(r.json()) == 6


def test_leaderboard_endpoint(client):
    r = client.get("/api/economy/leaderboard")
    assert r.status_code == 200


def test_chain_endpoint(client):
    r = client.get("/api/economy/chain")
    assert r.json()["chainId"] == 10143
