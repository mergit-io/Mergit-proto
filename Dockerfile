FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DB_PATH=/data/omnibox.db \
    WORKSPACE_DIR=/data/workspace \
    RUNTIME_CONFIG_DIR=/data/config

WORKDIR /app

RUN addgroup --system omnibox && adduser --system --ingroup omnibox omnibox

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

RUN mkdir -p /data/workspace /data/config /app/backend/logs \
    && chown -R omnibox:omnibox /data /app/backend/logs

USER omnibox
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD sh -c "python -c \"import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=3).read()\""

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]
