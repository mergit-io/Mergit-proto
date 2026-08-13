"""A shared-secret gate for public deployments.

Mergit's API is unauthenticated by design: `POST /api/goals` takes a free-form goal, the
coder agent's `code_exec` tool runs the result in a subprocess, and `PUT /api/config/keys`
rewrites the provider keys. On a laptop that is exactly what you want. On a URL anyone can
reach it is remote code execution plus credential theft, and `VITE_DEMO_MODE=true` removes
the login that would otherwise stand in the way.

So: set `ACCESS_PASSWORD` and every request needs it. Leave it empty and nothing changes,
which keeps local development and the test suite credential-free.

HTTP Basic is deliberate. The browser prompts natively, so the whole surface — SPA, REST and
SSE alike — is covered without touching the frontend, and `EventSource` (which cannot send
custom headers) still works because the browser attaches the credentials itself.
"""
import base64
import binascii
import secrets

from starlette.responses import JSONResponse

# The container HEALTHCHECK sends no credentials. Gating this marks the container unhealthy,
# which on most hosts means it gets killed and restarted forever.
OPEN_PATHS = frozenset({"/api/health"})

_CHALLENGE = {"WWW-Authenticate": 'Basic realm="Mergit", charset="UTF-8"'}


def password_from(header: str | None) -> str | None:
    """Pull the password out of an HTTP Basic header, or None if it isn't one.

    The username is ignored — there is one shared secret, not a user database.
    """
    if not header:
        return None
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    return decoded.split(":", 1)[1]


def is_authorized(header: str | None, expected: str) -> bool:
    supplied = password_from(header)
    if supplied is None:
        return False
    # compare_digest, not ==, so a wrong password cannot be recovered by timing how long
    # the rejection takes.
    return secrets.compare_digest(supplied, expected)


def add_access_gate(app, password: str) -> None:
    """Require `password` on every request. A falsy password installs nothing at all."""
    if not password:
        return

    @app.middleware("http")
    async def access_gate(request, call_next):
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        if not is_authorized(request.headers.get("authorization"), password):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers=_CHALLENGE,
            )
        return await call_next(request)
