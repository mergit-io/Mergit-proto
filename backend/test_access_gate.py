"""The gate that makes a public URL safe.

Without this, a reachable deployment hands anyone `PUT /api/config/keys` (overwrite the
provider keys), `GET /api/config/keys` (read masked keys) and `POST /api/goals` — and the
coder agent's `code_exec` tool runs arbitrary Python in a subprocess. That is remote code
execution by design, not by bug, so the gate is the difference between "unlisted" and "safe".
"""
import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from access_gate import add_access_gate


def build(password: str) -> TestClient:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/config/keys")
    async def keys():
        return {"groq": {"set": True}}

    @app.put("/api/config/keys")
    async def put_keys():
        return {"ok": True}

    @app.get("/")
    async def index():
        return {"page": "app"}

    add_access_gate(app, password)
    return TestClient(app)


def basic(user: str, password: str) -> dict[str, str]:
    raw = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {raw}"}


def test_no_password_configured_leaves_everything_open():
    """Local dev and the existing test suite must not need credentials."""
    c = build("")
    assert c.get("/api/config/keys").status_code == 200
    assert c.put("/api/config/keys").status_code == 200
    assert c.get("/").status_code == 200


@pytest.mark.parametrize("method,path", [
    ("get", "/api/config/keys"),
    ("put", "/api/config/keys"),
    ("get", "/"),
])
def test_gated_requests_without_credentials_are_rejected(method, path):
    c = build("s3cret")
    r = getattr(c, method)(path)
    assert r.status_code == 401
    # Without this header the browser never shows a login prompt — it just renders a 401.
    assert r.headers["www-authenticate"].startswith("Basic")


def test_correct_password_passes():
    c = build("s3cret")
    assert c.get("/api/config/keys", headers=basic("mergit", "s3cret")).status_code == 200
    assert c.put("/api/config/keys", headers=basic("anyone", "s3cret")).status_code == 200


@pytest.mark.parametrize("bad", ["", "wrong", "s3cre", "s3cret ", "S3CRET"])
def test_wrong_password_is_rejected(bad):
    c = build("s3cret")
    assert c.get("/api/config/keys", headers=basic("mergit", bad)).status_code == 401


def test_malformed_authorization_headers_do_not_crash():
    c = build("s3cret")
    for header in [{"Authorization": "Basic"}, {"Authorization": "Basic !!!not-base64"},
                   {"Authorization": "Bearer s3cret"}, {"Authorization": "Basic " + base64.b64encode(b"nocolon").decode()}]:
        assert c.get("/api/config/keys", headers=header).status_code == 401


def test_health_stays_open_so_container_healthchecks_still_pass():
    """The Docker HEALTHCHECK has no credentials; gating it turns the container unhealthy."""
    c = build("s3cret")
    assert c.get("/api/health").status_code == 200
