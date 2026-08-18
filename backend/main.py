import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

import db
import redaction
import worker
from access_gate import add_access_gate
from api import actions, approvals, auth, config, connections, context as ctx_api, github_webhook, goals, health, keys, stream, tasks, webhooks
from api import economy as economy_api
from api import heal as heal_api
from auth.gate import SessionGate
from config import cors_origin_list, require_auth_secret, settings
from crypto import envelope

# ── Logging setup ────────────────────────────────────────────────────────────────
_log_fmt = "%(asctime)s %(levelname)-8s %(name)-24s %(message)s"
_log_date = "%H:%M:%S"
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format=_log_fmt,
    datefmt=_log_date,
)
# Also write to a rotating file so you can debug without watching the terminal
import os
from logging.handlers import RotatingFileHandler as _RFH
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_fh = _RFH(os.path.join(_log_dir, "mergit.log"), maxBytes=5_000_000, backupCount=3)
_fh.setFormatter(logging.Formatter(_log_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
_fh.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_fh)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────────────────────

def _init_chain() -> None:
    """Bring the chain layer up.

    On the local in-process EVM the contracts are deployed fresh on every boot, so a
    developer gets a live chain with no keys, no tokens and no setup. On a real network
    we only ever *load* an existing deployment — deploying to a live chain is an explicit
    operator action via scripts/deploy_contracts.py.
    """
    if not settings.chain_enabled:
        logger.info("Chain layer disabled (chain_enabled=false)")
        return
    try:
        from chain import networks
        from chain.client import ChainClient, set_client
        from chain.deployer import deploy_all
        from chain.provider import build_provider

        network = networks.get_network(settings.chain_target)
        provider = build_provider(
            settings.chain_target, settings.chain_rpc_url, settings.chain_private_key
        )

        if network.is_local:
            addresses = deploy_all(provider, persist=True)
            logger.info("Chain: deployed contracts to %s", network.name)
        else:
            from chain import registry
            addresses = registry.load_addresses(network.chain_id)
            if not addresses:
                logger.warning(
                    "Chain: no deployment found for %s (chainId %s) — run "
                    "scripts/deploy_contracts.py --network %s",
                    network.name, network.chain_id, network.key,
                )

        client = ChainClient(provider, addresses)
        set_client(client)
        logger.info("Chain: %s (chainId %s) status=%s",
                    network.name, network.chain_id, client.status.value)
    except Exception as e:
        # The app must run even with no chain at all.
        logger.warning("Chain layer unavailable: %s", e)
        from chain.client import set_client
        set_client(None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Mergit (host=%s port=%s debug=%s)", settings.host, settings.port, settings.debug)

    # Refuse to boot with a guessable session secret once sign-in is live. It defaulted to
    # "change-me-in-env" for as long as the signing code was dead; the moment it signs a
    # real OAuth transaction, a deployment that missed the variable has forgeable state.
    require_auth_secret()

    # Read the key-encryption key once, then remove it from the environment — BEFORE the
    # worker starts, and therefore before any agent can run. `PUT /api/config/keys` writes
    # into os.environ at runtime and `code_exec` used to inherit the whole of it, so a KEK
    # left lying there was one `print(os.environ)` away from unwrapping every stored
    # OAuth token in the database.
    envelope.load_keys_and_scrub_env()

    redaction.install()
    await db.init_db()
    import economy
    await economy.seed_passports()
    await economy.backfill()
    Path(settings.workspace_dir).mkdir(parents=True, exist_ok=True)
    logger.info("DB initialised at %s", settings.db_path)
    _init_chain()
    # After the chain is up, so the seeded proofs are minted against the live chain and
    # actually verify — the whole point of seeding rather than shipping a populated db.
    if settings.seed_demo:
        import demo_seed
        await demo_seed.seed_if_empty()
    await worker.start()
    logger.info("Mergit ready ✓")
    yield
    logger.info("Shutting down Mergit…")
    await worker.stop()
    logger.info("Mergit stopped")


# ── App ───────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Mergit",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request logging middleware ────────────────────────────────────────────────────

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()

    # Skip SSE endpoints from verbose logging (they stay open)
    is_sse = "stream" in request.url.path

    if not is_sse:
        logger.debug("[%s] → %s %s", req_id, request.method, request.url.path)

    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if not is_sse:
            level = logging.WARNING if response.status_code >= 400 else logging.DEBUG
            logger.log(level, "[%s] ← %d %s %s (%.0fms)",
                       req_id, response.status_code, request.method,
                       request.url.path, elapsed_ms)

        response.headers["X-Request-Id"] = req_id
        return response

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.error("[%s] ✗ %s %s — unhandled exception after %.0fms: %s",
                     req_id, request.method, request.url.path, elapsed_ms, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": req_id},
            headers={"X-Request-Id": req_id},
        )


# ── Routers ───────────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(connections.router)
app.include_router(approvals.router)
app.include_router(config.router)
app.include_router(keys.router)
app.include_router(ctx_api.router)
app.include_router(goals.router)
app.include_router(tasks.router)
app.include_router(stream.router)
app.include_router(github_webhook.router)  # specific route before generic /{token}
app.include_router(webhooks.router)
app.include_router(actions.router)
app.include_router(economy_api.router)
app.include_router(heal_api.router)
app.include_router(health.router)


# ── Auth middleware ───────────────────────────────────────────────────────────────
# Order note: Starlette runs the LAST-added middleware outermost, so these execute in the
# reverse of the order written here — access gate, then session gate, then the OAuth
# transaction session, then request logging, then CORS.
#
# `SessionMiddleware` carries the OAuth `state`, `nonce` and PKCE verifier across the
# redirect to Google and back. It must be *inside* the session gate, because the callback
# needs to read it while the user has no Mergit session yet — that is the whole point of
# the callback. It is short-lived, signed, and holds nothing but the in-flight handshake.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.auth_secret_key,
    session_cookie="mergit_oauth",
    max_age=600,           # a login that takes longer than ten minutes is an abandoned one
    same_site="lax",       # must survive the top-level redirect back from Google
    https_only=settings.cookie_secure,
)

# Rejects anything under /api/ without a valid session, and enforces CSRF on unsafe
# methods. No-op when Google is unconfigured, so a local checkout still runs.
app.add_middleware(SessionGate)

# ── Access gate ───────────────────────────────────────────────────────────────────
# Added last, so it is the OUTERMOST middleware and rejects unauthorised requests before
# anything else touches them. No-op unless ACCESS_PASSWORD is set. Retained alongside the
# session gate because it covers the SPA and static assets too, which the session gate
# deliberately does not.
add_access_gate(app, settings.access_password)


# ── Frontend static files (production) ────────────────────────────────────────────


class SPAStaticFiles(StaticFiles):
    """Static files with SPA fallback: serve index.html for any unmatched path so
    client-side routes (/app, /app/economy, /login, …) work on direct load/refresh.

    The API is excluded. This mount is at "/", so without the exclusion an unmatched
    `/api/...` path — a typo, a removed endpoint, a client built against a newer
    version — was answered with 200 and the SPA's HTML. Callers expecting JSON got a
    decode error instead of a status code they could act on.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not _is_api_path(scope):
                return await super().get_response("index.html", scope)
            raise


def _is_api_path(scope) -> bool:
    """True for requests under /api — read from the ASGI scope so the mount's stripped
    `path` cannot disagree with the URL the client actually asked for."""
    full = scope.get("root_path", "") + scope.get("path", "")
    return full == "/api" or full.startswith("/api/")


_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", SPAStaticFiles(directory=str(_frontend_dist), html=True), name="static")
    logger.info("Serving frontend from %s", _frontend_dist)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_includes=["*.py"] if settings.debug else [],
        reload_excludes=["*/__pycache__/*", "*.pyc", "*.db", "*.db-wal", "*.db-shm"] if settings.debug else [],
        log_level="warning",
    )
