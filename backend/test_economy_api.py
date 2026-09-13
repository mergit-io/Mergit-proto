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


def test_chain_endpoint_reports_the_live_chain(client):
    """The endpoint must describe the chain we are on, not a chain we wish we were on.

    It previously read deployments/10143.json off disk and asserted 10143 back, which
    passed happily while the app ran on chainId 31337 with entirely different addresses.
    """
    from chain.client import ChainClient, reset_client, set_client
    from chain.deployer import deploy_all
    from chain.provider import LocalEvmProvider

    provider = LocalEvmProvider()
    live = ChainClient(provider, deploy_all(provider))
    set_client(live)
    try:
        body = client.get("/api/economy/chain").json()
        assert body["chainId"] == live.chain_id
        assert body["contracts"] == live.addresses
    finally:
        reset_client()


def test_chain_endpoint_with_the_chain_off_claims_nothing(client, monkeypatch):
    from chain.client import reset_client, set_client

    monkeypatch.setattr("config.settings.chain_enabled", False)
    set_client(None)
    try:
        body = client.get("/api/economy/chain").json()
        assert body["chainId"] is None
        assert body["contracts"] == {}
    finally:
        reset_client()
