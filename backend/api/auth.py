"""Sign in with Google, sign out, and "who am I".

This replaces a hand-rolled flow that implemented Google *and* GitHub OAuth, had no
`state`, no PKCE, no `nonce` and no `id_token` validation, threw away every access token
it obtained, stored nothing, and was called by no one.

GitHub is deliberately **not** an identity provider here. It is a *connection* — see
`api/connections.py`. Offering "Sign in with GitHub" next to "Sign in with Google" is
precisely the confusion this design exists to remove: signing in with GitHub grants Mergit
nothing on GitHub, and a user who did it would reasonably expect otherwise.
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

import auth.oidc as oidc
import auth.sessions as sessions
import db
from config import auth_enabled, settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Best-effort client address, trusting the proxy chain the app is deployed behind.

    Only ever hashed (`sessions.hash_ip`), never stored or logged raw.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/login")
async def login(request: Request):
    """Begin sign-in. Authlib stashes state, nonce and the PKCE verifier in the session."""
    if not auth_enabled():
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on this deployment "
                   "(set OAUTH_GOOGLE_CLIENT_ID and OAUTH_GOOGLE_CLIENT_SECRET).",
        )
    google = oidc.client().create_client("google")
    return await google.authorize_redirect(request, oidc.redirect_uri())


@router.get("/callback")
async def callback(request: Request):
    """Complete sign-in and start a session.

    `authorize_access_token` is where the safety lives: it checks `state` against the
    value stored at /login, exchanges the code with the PKCE verifier, then validates the
    ID token's signature against Google's JWKS along with `iss`, `aud`, `exp` and `nonce`.
    A failure of any of those raises, and we send the user back to /login with a reason
    rather than signing anybody in.
    """
    if not auth_enabled():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")

    google = oidc.client().create_client("google")
    try:
        token = await google.authorize_access_token(request)
    except Exception as e:
        # Includes a mismatched state — i.e. a login-CSRF attempt, or simply a stale tab.
        logger.warning("OAuth callback rejected: %s", e)
        return RedirectResponse(f"{settings.frontend_url}/login?auth=failed")

    claims = token.get("userinfo")
    if not claims or not claims.get("sub"):
        logger.warning("OAuth callback returned no verified id_token claims")
        return RedirectResponse(f"{settings.frontend_url}/login?auth=no_identity")

    profile = oidc.profile_from_claims(claims)
    user = await db.upsert_user(
        google_sub=profile["google_sub"],
        email=profile["email"],
        email_verified=profile["email_verified"],
        name=profile["name"],
        picture=profile["picture"],
        is_admin=oidc.is_admin(profile),
    )

    session_id, _csrf = await sessions.start(
        user["id"],
        user_agent=request.headers.get("user-agent", ""),
        ip=_client_ip(request),
    )

    # Absolute, from config — NOT a relative "/app". A relative redirect resolves against
    # the callback's own origin, which in development is the backend on :8000, where the
    # SPA is not served and the developer lands on a 404 at their first ever login.
    response = RedirectResponse(f"{settings.frontend_url}/app")
    sessions.attach(response, session_id)
    logger.info("signed in user=%s admin=%s", user["id"], user["is_admin"])
    return response


@router.get("/me")
async def me(request: Request) -> JSONResponse:
    """The signed-in user, and the CSRF token the SPA must echo on unsafe requests.

    Handing the token out here rather than in a JS-readable cookie is what makes it a
    synchronizer token: a cross-site page can cause a request to be *sent* with the
    session cookie attached, but it cannot read this response to learn the token.
    """
    if not auth_enabled():
        # No login is possible, so report the single-tenant local mode honestly instead of
        # a 401 the SPA would bounce to a login page that cannot work.
        return JSONResponse({
            "authenticated": True,
            "auth_configured": False,
            "user": {"id": db.LEGACY_USER_ID, "email": "", "name": "Local",
                     "picture": "", "is_admin": True},
            "csrf_token": "",
        })

    session = await sessions.load(request.cookies.get(sessions.cookie_name()))
    if not session:
        return JSONResponse({"authenticated": False, "auth_configured": True}, status_code=401)

    return JSONResponse({
        "authenticated": True,
        "auth_configured": True,
        "user": {
            "id": session["id"],
            "email": session["email"],
            "name": session["name"],
            "picture": session["picture"],
            "is_admin": session["is_admin"],
        },
        "csrf_token": session["csrf_token"],
    })


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """End the session server-side, then clear the cookie.

    Order matters. The old implementation only deleted the client's copy, so a cookie
    captured beforehand stayed valid for its full seven days — logout looked like it
    worked and did nothing an attacker would notice.
    """
    session_id = request.cookies.get(sessions.cookie_name())
    await sessions.end(session_id)
    response = JSONResponse({"ok": True})
    sessions.clear(response)
    return response
