# Litestream, pinned. `latest` would change the binary under a rebuild, and this one
# is responsible for whether the database survives a redeploy.
FROM litestream/litestream:0.5.16 AS litestream

FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
# Defaults to FALSE now that Google sign-in exists. This flag used to default to true
# and compiled the login out of the production image entirely — the deployed build had
# no authentication at all. Kept only so a local demo can still bypass login.
ARG VITE_DEMO_MODE=false
ENV VITE_DEMO_MODE=$VITE_DEMO_MODE
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DB_PATH=/data/mergit.db \
    WORKSPACE_DIR=/data/workspace \
    RUNTIME_CONFIG_DIR=/data/config \
    SOLCX_BINARY_PATH=/opt/solcx

WORKDIR /app

# UID/GID 1000 explicitly: Hugging Face Spaces runs the container as user 1000, so a
# system user in the <1000 range owns /data and the app then cannot write its own database.
RUN addgroup --gid 1000 mergit && adduser --uid 1000 --gid 1000 --disabled-password --gecos "" mergit

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Compile the Solidity contracts at BUILD time. Without this the first boot would try to
# download solc from GitHub as an unprivileged user with no writable home — and because
# _init_chain degrades rather than crashes, the chain would silently switch itself off
# while the health check stayed green. Baking solc + the artifacts in makes startup
# offline, fast and deterministic.
# `deployments/` must be writable too: on the local chain the app redeploys on every boot
# and writes the address record there. Root-owned, that write fails with EACCES and the
# chain layer switches itself off while the health check stays green.
RUN mkdir -p /opt/solcx /app/backend/deployments \
    && cd /app/backend \
    && python -c "from chain import compiler; compiler.compile_all(); print('contracts compiled')" \
    && chown -R mergit:mergit /opt/solcx /app/backend/contracts /app/backend/deployments

# Continuous SQLite replication. Adds ~37 MB to the image and well under 30 MB
# resident, which matters on a 512 MB free instance already holding litellm and py-evm.
COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream
COPY deploy/litestream/litestream.yml  /etc/litestream.yml
COPY deploy/litestream/entrypoint.sh   /usr/local/bin/entrypoint.sh
COPY deploy/litestream/run-app.sh      /usr/local/bin/run-app.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/run-app.sh

RUN mkdir -p /data/workspace /data/config /app/backend/logs \
    && chown -R mergit:mergit /data /app/backend/logs

USER mergit
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD sh -c "python -c \"import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=3).read()\""

# Exec form, deliberately. Shell form wraps this in `/bin/sh -c`, and that shell does
# NOT forward SIGTERM to its child — which would silently disable Litestream's final
# sync and turn every redeploy into a data-loss event that still looks fine in the logs.
# entrypoint.sh runs uvicorn directly when LITESTREAM_BUCKET is unset, so `make dev`
# and the test suite are unaffected.
CMD ["/usr/local/bin/entrypoint.sh"]
