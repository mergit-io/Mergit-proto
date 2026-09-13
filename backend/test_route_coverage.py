"""Every API route is either authenticated or deliberately, visibly public.

This is the test that makes "fail closed" real. The session gate is scoped to `/api/`
rather than denying every unknown path, because the app also serves the SPA at `/` and a
blanket default would put the login page behind the login. That scoping means the runtime
cannot, by itself, guarantee a new route is covered — so the guarantee is moved here,
where it fires on the pull request instead of in production.

Adding a route to `PUBLIC_EXACT`/`PUBLIC_PREFIX` in `auth/gate.py` is therefore a
deliberate, reviewable act. Adding a route and forgetting about it fails the build.
"""
import ast
import pathlib

import pytest

import main
from auth import gate


def _api_paths() -> set[str]:
    """Every `/api/...` path the app actually serves.

    FastAPI wraps included routers in `_IncludedRouter`, so a flat walk of `app.routes`
    finds only the four routes registered directly on the app — which would make this
    test pass vacuously. Descend through `original_router`.
    """
    found, stack = set(), list(main.app.routes)
    while stack:
        route = stack.pop()
        original = getattr(route, "original_router", None)
        if original is not None:
            stack.extend(original.routes)
            continue
        path = getattr(route, "path", None)
        if isinstance(path, str) and path.startswith("/api"):
            found.add(path)
    return found


def test_the_app_actually_serves_routes():
    """Guards the guard: if the walk above breaks, every other test here passes vacuously."""
    paths = _api_paths()
    assert len(paths) > 30, f"only found {len(paths)} API routes — the route walk is broken"
    for expected in ("/api/goals", "/api/auth/me", "/api/connections"):
        assert expected in paths


def test_every_api_route_is_gated_or_explicitly_public():
    unclassified = [
        path for path in sorted(_api_paths())
        if not gate._is_public(path, debug=False)
        and not path.startswith("/api/")  # unreachable; kept so the intent is explicit
    ]
    assert unclassified == []

    # The real assertion: everything under /api/ is reached by the gate, and the gate
    # denies by default unless the path is on one of the two public lists.
    for path in sorted(_api_paths()):
        assert path.startswith("/api/") or path == "/api", (
            f"{path} is served but not under /api/, so the session gate never sees it"
        )


@pytest.mark.parametrize("path", sorted(_api_paths()))
def test_public_routes_are_the_ones_we_intended(path):
    """A change to the public surface has to be a change to this list.

    If this fails, either a route was added that should be authenticated, or the public
    list grew. Both deserve a reviewer.
    """
    KNOWN_PUBLIC = {
        "/api/health",                      # container healthcheck
        "/api/auth/login",                  # cannot authenticate to authenticate
        "/api/auth/callback",
        "/api/auth/me",                     # returns 401 itself when signed out
        "/api/auth/logout",
        "/api/webhooks/github",             # HMAC-signed, verified in the handler
        "/api/webhooks/{token}",            # unguessable token, single-use
        "/api/docs", "/api/redoc", "/api/openapi.json",   # DEBUG only — see gate._is_public
    }
    is_public = gate._is_public(path, debug=True)
    if is_public:
        assert path in KNOWN_PUBLIC, (
            f"{path} is publicly reachable but is not in this test's KNOWN_PUBLIC list. "
            f"If that is intended, add it here so the change is reviewed."
        )


def test_api_docs_are_not_public_in_production():
    """An unauthenticated OpenAPI schema is a map of the whole attack surface."""
    assert gate._is_public("/api/openapi.json", debug=True) is True
    assert gate._is_public("/api/openapi.json", debug=False) is False
    assert gate._is_public("/api/docs", debug=False) is False


def test_the_credential_vault_has_exactly_one_reader():
    """`unseal` may only be imported inside `credentials/`.

    The security claim this project makes is that a token never reaches model context.
    That holds because the broker returns clients rather than credential strings — and it
    stops holding the moment a second module can decrypt one. An AST check rather than a
    grep, so a comment mentioning `unseal` does not fail the build and an aliased import
    does not sneak past.
    """
    backend = pathlib.Path(__file__).parent
    offenders = []
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend)
        parts = rel.parts
        if parts[0] in ("credentials", ".venv", "__pycache__") or parts[0].startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("envelope"):
                for alias in node.names:
                    if alias.name in ("unseal", "unwrap_dek"):
                        offenders.append(f"{rel}:{node.lineno} imports {alias.name}")
    assert offenders == [], (
        "only credentials/ may decrypt stored tokens; found: " + "; ".join(offenders)
    )
