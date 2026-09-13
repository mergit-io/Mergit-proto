"""Sign in with Google, done properly.

The flow this replaces (`api/auth.py`, now deleted) had none of the four things that make
an OAuth login safe:

  * **No `state`.** An attacker could feed a victim a crafted `?code=…` callback and log
    them into the *attacker's* account — after which anything the victim connects,
    the attacker owns. This is login CSRF, and it is the serious one.
  * **No `nonce`**, so a replayed ID token could not be detected.
  * **No PKCE.**
  * **No `id_token` validation at all** — identity came from a separate userinfo call
    against the deprecated `oauth2/v2/userinfo` endpoint, and the signed assertion Google
    had already provided was discarded unread.

Authlib supplies all four from the discovery document, which is the entire reason to take
the dependency rather than hand-roll ~40 lines of `httpx` again. `authorize_access_token`
validates the ID token's signature against Google's JWKS and checks `iss`, `aud`, `exp`
and `nonce` before returning claims.

**Scopes are `openid email profile`, forever.** They are non-sensitive, so this app never
needs Google verification or a CASA assessment — a real cost, in weeks and in money, that
is avoided entirely by keeping Google to identity. Anything more (Gmail, Drive, Calendar)
becomes a separate *connection* under `credentials/`, requested at the point of use.

**No refresh token is requested.** Login needs no offline access, and Google caps live
refresh tokens at 100 per account per client — minting one per sign-in would eventually
start silently invalidating a power user's own earlier sessions.
"""
import logging

from authlib.integrations.starlette_client import OAuth

from config import settings

logger = logging.getLogger(__name__)

#: Google publishes endpoints, the JWKS URI and supported algorithms here. Using discovery
#: rather than hard-coded URLs means a Google-side endpoint change does not become an
#: outage, and it is what lets Authlib validate the ID token without further configuration.
GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"

_oauth: OAuth | None = None


def client() -> OAuth:
    """The configured Authlib registry, built once.

    Constructed lazily rather than at import so that tests — and a deployment with no
    Google credentials — can import this module without configuring OAuth.
    """
    global _oauth
    if _oauth is None:
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=settings.oauth_google_client_id,
            client_secret=settings.oauth_google_client_secret,
            server_metadata_url=GOOGLE_DISCOVERY,
            client_kwargs={
                "scope": "openid email profile",
                # S256, not plain. Not strictly required for a confidential server-side
                # client, but it is free here and closes authorization-code interception
                # if this ever moves to a public client.
                "code_challenge_method": "S256",
            },
        )
        _oauth = oauth
    return _oauth


def reset() -> None:
    """Drop the cached registry so a test can re-register with different settings."""
    global _oauth
    _oauth = None


def redirect_uri() -> str:
    """The callback URL, always from configuration.

    Deliberately not `request.url_for(...)`. Behind the Vite dev proxy that yields the
    backend's own `:8000` origin while Google is registered against whatever the operator
    entered, and the mismatch surfaces as `redirect_uri_mismatch` — an error that says
    nothing about proxies. Config is also the safer default: a redirect URI derived from
    the request is a redirect URI an attacker has a say in.
    """
    return settings.oauth_google_redirect_uri


def profile_from_claims(claims: dict) -> dict:
    """Normalise the validated ID token into the fields we store.

    `sub` is the identity. It is the only Google-issued value that is stable for the life
    of the account — emails get reassigned within an organisation, and `email_verified`
    can go from true to false. Keying users on email would let a reassigned address
    inherit the previous holder's stored GitHub and Slack credentials.
    """
    return {
        "google_sub": claims["sub"],
        "email": claims.get("email", ""),
        # Google sends this as a real bool or the string "true" depending on the path.
        "email_verified": str(claims.get("email_verified", "")).lower() in ("true", "1"),
        "name": claims.get("name", "") or claims.get("given_name", ""),
        "picture": claims.get("picture", ""),
    }


def is_admin(profile: dict) -> bool:
    """Admin is a config list, re-evaluated on every login.

    Two deliberate choices:

    * **Never "first user wins".** On a public URL the first user is a stranger.
    * **Verified email required.** Admin gates the provider keys the whole deployment
      shares, so an unverified address must not reach it.
    """
    from config import admin_email_set
    if not profile.get("email_verified"):
        return False
    email = (profile.get("email") or "").lower()
    return bool(email) and email in admin_email_set()
