import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE = "omnibox_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(settings.auth_secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _unsign(token: str) -> dict | None:
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(settings.auth_secret_key.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload_raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        payload = json.loads(payload_raw.decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def _set_session_cookie(resp: RedirectResponse, payload: dict) -> None:
    resp.set_cookie(
        key=SESSION_COOKIE,
        value=_sign(payload),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    if not settings.oauth_google_client_id:
        raise HTTPException(status_code=500, detail="Missing OAUTH_GOOGLE_CLIENT_ID")
    query = urlencode(
        {
            "client_id": settings.oauth_google_client_id,
            "redirect_uri": settings.oauth_google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")


@router.get("/github/login")
async def github_login() -> RedirectResponse:
    if not settings.oauth_github_client_id:
        raise HTTPException(status_code=500, detail="Missing OAUTH_GITHUB_CLIENT_ID")
    query = urlencode(
        {
            "client_id": settings.oauth_github_client_id,
            "redirect_uri": settings.oauth_github_redirect_uri,
            "scope": "read:user user:email",
        }
    )
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{query}")


@router.get("/google/callback")
async def google_callback(code: str = Query(default="")) -> RedirectResponse:
    if not code:
        return RedirectResponse(f"{settings.frontend_url}/login?auth=google_failed")
    if not settings.oauth_google_client_secret:
        raise HTTPException(status_code=500, detail="Missing OAUTH_GOOGLE_CLIENT_SECRET")

    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.oauth_google_client_id,
                "client_secret": settings.oauth_google_client_secret,
                "redirect_uri": settings.oauth_google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_res.status_code >= 400:
            return RedirectResponse(f"{settings.frontend_url}/login?auth=google_token_failed")
        access_token = token_res.json().get("access_token")
        if not access_token:
            return RedirectResponse(f"{settings.frontend_url}/login?auth=google_token_failed")
        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if user_res.status_code >= 400:
            return RedirectResponse(f"{settings.frontend_url}/login?auth=google_user_failed")
        user = user_res.json()

    payload = {
        "provider": "google",
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "picture": user.get("picture", ""),
        "exp": int(time.time()) + SESSION_MAX_AGE,
    }
    resp = RedirectResponse(f"{settings.frontend_url}/app")
    _set_session_cookie(resp, payload)
    return resp


@router.get("/github/callback")
async def github_callback(code: str = Query(default="")) -> RedirectResponse:
    if not code:
        return RedirectResponse(f"{settings.frontend_url}/login?auth=github_failed")
    if not settings.oauth_github_client_secret:
        raise HTTPException(status_code=500, detail="Missing OAUTH_GITHUB_CLIENT_SECRET")

    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "code": code,
                "client_id": settings.oauth_github_client_id,
                "client_secret": settings.oauth_github_client_secret,
                "redirect_uri": settings.oauth_github_redirect_uri,
            },
        )
        if token_res.status_code >= 400:
            return RedirectResponse(f"{settings.frontend_url}/login?auth=github_token_failed")
        access_token = token_res.json().get("access_token")
        if not access_token:
            return RedirectResponse(f"{settings.frontend_url}/login?auth=github_token_failed")
        user_res = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        if user_res.status_code >= 400:
            return RedirectResponse(f"{settings.frontend_url}/login?auth=github_user_failed")
        user = user_res.json()

    payload = {
        "provider": "github",
        "email": user.get("email", ""),
        "name": user.get("name") or user.get("login", ""),
        "picture": user.get("avatar_url", ""),
        "exp": int(time.time()) + SESSION_MAX_AGE,
    }
    resp = RedirectResponse(f"{settings.frontend_url}/app")
    _set_session_cookie(resp, payload)
    return resp


@router.get("/me")
async def me(request: Request) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return JSONResponse({"authenticated": False}, status_code=401)
    payload = _unsign(token)
    if not payload:
        return JSONResponse({"authenticated": False}, status_code=401)
    return JSONResponse({"authenticated": True, "user": payload})


@router.post("/logout")
async def logout() -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
