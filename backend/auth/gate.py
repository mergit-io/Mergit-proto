"""One middleware that decides whether a request may proceed.

**Why middleware and not `Depends(current_user)` on each route.** There are thirteen
routers and ~40 routes. With per-route dependencies, the failure mode of forgetting one is
a silently public endpoint, and nothing tells you. With a middleware the failure mode of
forgetting is a route that stops working — loud, immediate, and safe. `access_gate.py`
already proved the shape works here, including with SSE.

**Scoped to `/api/`.** The app mounts the built SPA at `/`, so a middleware that denied
every unknown path would reject `/`, `/login` and `/assets/*` — the login page would be
behind the login. The fail-closed guarantee is therefore not a runtime default but a CI
test (`test_route_coverage.py`) that walks `app.routes` and fails the build if any `/api/`
route is neither gated nor explicitly listed as public. That is a stronger guarantee than
a runtime default: it fires at build time, on the pull request, before deployment.

**CORS.** `CORSMiddleware` is registered before this one and is therefore *inner*, so a
rejection returned from here would carry no CORS headers and the dev frontend would see an
opaque network error instead of a 401 — and the SPA's "401 → go to /login" interceptor
would never fire. The rejection helper below adds the headers itself.
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import auth.sessions as sessions
from config import auth_enabled, cors_origin_list

logger = logging.getLogger(__name__)

#: Reachable with no session, matched exactly.
PUBLIC_EXACT = frozenset({
    "/api/health",       # the container healthcheck; must never require credentials
})

#: Reachable with no session, matched by prefix. Each one is public for a stated reason —
#: this list is the security boundary, so adding to it deserves the same scrutiny as
#: removing an auth check.
PUBLIC_PREFIX = (
    # The sign-in flow itself. Chicken and egg: you cannot authenticate to authenticate.
    "/api/auth/",
    # Inbound from third parties, which have no Mergit session and never will. These are
    # NOT unauthenticated: they carry their own HMAC signatures, verified by their
    # handlers. GitHub's receiver fails closed on a bad or missing signature.
    "/api/webhooks/",
    # OpenAPI. Public only in DEBUG — see `_is_public`.
    "/api/docs", "/api/redoc", "/api/openapi.json",
)

#: Methods that cannot change state, and so need no CSRF token.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_public(path: str, debug: bool) -> bool:
    if path in PUBLIC_EXACT:
        return True
    for prefix in PUBLIC_PREFIX:
        if path.startswith(prefix):
            # API docs enumerate every endpoint and its schema. Handy locally, an
            # unnecessary map of the attack surface in production.
            if prefix in ("/api/docs", "/api/redoc", "/api/openapi.json"):
                return debug
            return True
    return False


def _reject(status: int, detail: str, request) -> JSONResponse:
    """A rejection that the browser can actually read.

    Without the CORS headers here, a cross-origin 401 surfaces in the SPA as a generic
    network failure rather than a 401, and the client-side redirect to /login never runs.
    """
    resp = JSONResponse({"detail": detail}, status_code=status)
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") in {o.rstrip("/") for o in cors_origin_list()}:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Vary"] = "Origin"
    return resp


class SessionGate(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        from config import settings

        path = request.url.path

        # Anything outside /api/ is the SPA and its assets. See the module docstring.
        if not path.startswith("/api/"):
            return await call_next(request)

        # With Google unconfigured there is no way to sign in, so gating would lock every
        # operator out of their own deployment on upgrade. `request.state.user` is None
        # and ownership filters fall back to the legacy sentinel, which is exactly how the
        # deployment behaved before this feature existed.
        if not auth_enabled():
            request.state.user = None
            return await call_next(request)

        if _is_public(path, settings.debug):
            request.state.user = None
            return await call_next(request)

        session = await sessions.load(request.cookies.get(sessions.cookie_name()))
        if not session:
            return _reject(401, "Authentication required", request)

        if request.method not in SAFE_METHODS:
            # Two independent checks. Origin is cheap and catches the ordinary case; the
            # synchronizer token is the one that holds when Origin is absent or the
            # attacker is on a sibling host.
            if not sessions.origin_ok(request):
                logger.warning("cross-site %s %s rejected (origin=%s)",
                               request.method, path, request.headers.get("origin"))
                return _reject(403, "Cross-site request rejected", request)
            if not sessions.csrf_ok(request, session):
                return _reject(403, f"Missing or invalid {sessions.CSRF_HEADER} header", request)

        request.state.user = session
        return await call_next(request)


def current_user(request) -> dict | None:
    """The signed-in user, for handlers that need more than "not rejected"."""
    return getattr(request.state, "user", None)


def require_user(request) -> dict:
    """The signed-in user, or 401.

    Handlers use this rather than trusting the middleware's silence, so a route that is
    accidentally added to PUBLIC_PREFIX still cannot read another user's data.
    """
    from fastapi import HTTPException
    user = current_user(request)
    if user is None:
        if not auth_enabled():
            # Single-tenant fallback: everything belongs to the legacy owner, which is how
            # this deployment behaved before auth existed.
            import db
            return {"id": db.LEGACY_USER_ID, "email": "", "is_admin": True,
                    "name": "Local", "csrf_token": ""}
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(request) -> dict:
    """Admin-only routes: the shared provider keys and the deployment's model config.

    These are *Mergit's* credentials, shared by every user of the deployment — not the
    caller's own. A signed-in stranger being able to overwrite them is a design problem,
    not a rate-limiting one.
    """
    from fastapi import HTTPException
    user = require_user(request)
    if not user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin only. Add your email to ADMIN_EMAILS to manage deployment settings.",
        )
    return user
