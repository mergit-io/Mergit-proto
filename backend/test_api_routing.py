"""The SPA fallback must not answer for the API.

`SPAStaticFiles` serves index.html for any path the static mount cannot resolve, so that
client-side routes (/app, /app/economy, /login) survive a direct load or refresh. It is
mounted at "/", which means it also catches every unmatched `/api/...` path.

Observed on the live deployment: `/api/nope`, `/api/economy/nope` and `/api/goals/x/y/z`
all returned `200 text/html` with 479 bytes of SPA index. A client calling a mistyped or
removed endpoint gets HTML and a JSON decode error instead of a 404 it can handle.
"""
import json
import tempfile
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from main import SPAStaticFiles

INDEX = "<!doctype html><html><head><title>Mergit</title></head><body><div id=root></div></body></html>"


@pytest.fixture()
def client():
    """An app shaped exactly like main.py: API routers first, SPA mounted at '/' last."""
    dist = Path(tempfile.mkdtemp())
    (dist / "index.html").write_text(INDEX)
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('hi')")

    app = FastAPI()
    router = APIRouter(prefix="/api", tags=["probe"])

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(router)
    app.mount("/", SPAStaticFiles(directory=str(dist), html=True), name="static")
    return TestClient(app)


# ── what the SPA fallback is for ────────────────────────────────────────────────

def test_client_routes_still_fall_back_to_the_spa(client):
    for path in ("/app", "/app/economy", "/login", "/deep/nested/route"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert "text/html" in r.headers["content-type"], path
        assert "id=root" in r.text, path


def test_real_static_assets_are_still_served(client):
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_a_matched_api_route_is_untouched(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── what it must stop doing ─────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/api/nope",
    "/api/economy/nope",
    "/api/goals/x/y/z",
    "/api/config/does-not-exist",
    "/api",
])
def test_unmatched_api_paths_are_json_404s(client, path):
    r = client.get(path)

    assert r.status_code == 404, (
        f"{path} returned {r.status_code} — the SPA fallback answered for an API path; "
        "a client expecting JSON gets HTML"
    )
    assert "text/html" not in r.headers.get("content-type", ""), (
        f"{path} returned HTML: {r.text[:80]!r}"
    )
    body = json.loads(r.text)  # must be parseable as JSON, which was the whole problem
    assert "detail" in body


def test_the_api_404_does_not_leak_the_spa_body(client):
    r = client.get("/api/nope")
    assert "id=root" not in r.text
