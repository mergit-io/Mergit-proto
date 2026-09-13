"""Opaque server-side sessions, and the cookie that carries one.

**Why not a JWT.** A live Mergit session can tell agents to merge a pull request into
someone's repository. Revocation therefore has to be immediate, and a self-contained token
cannot be revoked — only outlived. One indexed read per request is a very cheap price for
"logging out actually logs you out". The cookie value is 32 random bytes with no structure
and no meaning outside the `sessions` table.

**Why a cookie at all, rather than a header.** `frontend/src/lib/sse.ts` opens goal and
economy streams with `EventSource`, which cannot set headers. The alternatives were a
token in the query string — which lands in access logs and `Referer` — or a cookie the
browser attaches by itself. The SPA is served same-origin by this same FastAPI app, so the
cookie rides along on every existing `fetch` with no frontend change at all.

**The `__Host-` prefix.** A browser only accepts a `__Host-`-prefixed cookie when it is
`Secure`, `Path=/`, and has **no `Domain`** — which means no subdomain can set it. That
closes cookie-fixation from a neighbouring host. It requires HTTPS, so plain-HTTP local
development gets an unprefixed name instead; the prefix is a deployment property, not a
behaviour the code depends on.
"""
import hashlib
import hmac
import logging

from starlette.responses import Response

import db
from config import settings

logger = logging.getLogger(__name__)

#: Sent to browsers over HTTPS. The prefix is enforced by the browser, not by us.
SECURE_COOKIE_NAME = "__Host-mergit_session"
#: Local development over plain HTTP, where a `__Host-` cookie would simply be dropped.
#: Safari additionally refuses `Secure` cookies on http://localhost, so this is not
#: merely a nicety — without it, sign-in cannot be tested in Safari at all.
DEV_COOKIE_NAME = "mergit_session"

#: The SPA reads this from `GET /api/auth/me` and echoes it on unsafe requests.
CSRF_HEADER = "X-Mergit-CSRF"


def cookie_name() -> str:
    return SECURE_COOKIE_NAME if settings.cookie_secure else DEV_COOKIE_NAME


def hash_ip(ip: str) -> str:
    """Store a fingerprint, never the address.

    Enough to notice a session being used from somewhere new; not enough to reconstruct
    where a user was. Keyed with the app secret so the digest is not reversible by
    guessing the (small) space of IPv4 addresses.
    """
    if not ip:
        return ""
    return hmac.new(settings.auth_secret_key.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


async def start(user_id: str, user_agent: str = "", ip: str = "") -> tuple[str, str]:
    """Create a session row. Returns (session_id, csrf_token)."""
    return await db.create_session(
        user_id,
        ttl_seconds=settings.session_ttl_seconds,
        user_agent=user_agent,
        ip_hash=hash_ip(ip),
    )


async def load(session_id: str | None) -> dict | None:
    if not session_id:
        return None
    return await db.load_session(session_id)


async def end(session_id: str | None) -> None:
    if session_id:
        await db.revoke_session(session_id)


def attach(response: Response, session_id: str) -> None:
    """Set the session cookie on a response.

    `SameSite=Lax`, not `Strict`, and the difference matters: `Strict` withholds the
    cookie on the top-level navigation *back* from Google, so the callback would complete
    and then immediately land on a page that considers the user signed out.
    """
    response.set_cookie(
        key=cookie_name(),
        value=session_id,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        # No `domain=`. A `__Host-` cookie is rejected outright if one is present, and
        # omitting it is what stops a sibling host from writing this cookie.
    )


def clear(response: Response) -> None:
    """Remove the client's copy. The server-side revoke is what actually ends the session."""
    response.delete_cookie(cookie_name(), path="/")


def csrf_ok(request, session: dict) -> bool:
    """Synchronizer-token check for unsafe methods.

    Applied unconditionally rather than relying on `SameSite=Lax`. OWASP is explicit that
    SameSite is defence in depth and not a standalone control: `Lax` still permits
    top-level cross-site GETs, browser support is not uniform, and a same-site
    subdomain can be enough on a shared parent domain.

    The token lives in the session row and is delivered to the SPA by `/api/auth/me` —
    never as a JS-readable cookie, so a double-submit forgery has nothing to copy.
    """
    supplied = request.headers.get(CSRF_HEADER, "")
    expected = session.get("csrf_token", "")
    if not supplied or not expected:
        return False
    return hmac.compare_digest(supplied, expected)


def origin_ok(request) -> bool:
    """Reject cross-site unsafe requests by Origin, as a second, independent check.

    Compared against the configured frontend URL and CORS allowlist — deliberately **not**
    against the `Host` header, which an attacker controls and which would also break the
    Vite dev proxy, where `changeOrigin: true` rewrites Host to `localhost:8000` while the
    browser's Origin is `http://localhost:3000`.

    A missing Origin is allowed: browsers omit it on same-origin GETs, and non-browser
    clients (curl, the GitHub webhook) never send one. CSRF requires a browser, and every
    browser sends Origin on the unsafe methods this guards.
    """
    origin = request.headers.get("origin")
    if not origin:
        return True
    allowed = set(cors_origins()) | {settings.frontend_url.rstrip("/")}
    sec_fetch = request.headers.get("sec-fetch-site", "")
    if sec_fetch == "same-origin":
        return True
    return origin.rstrip("/") in allowed


def cors_origins() -> list[str]:
    from config import cors_origin_list
    return [o.rstrip("/") for o in cors_origin_list()]
