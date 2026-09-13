# Mergit — The AI Agent Economy
Assign any goal to an AI. It decomposes the task, spins up specialized agents, uses your tools, and delivers results. Every completed task mints a proof of work on a real EVM — Solidity contracts, real tx hashes, real receipts — and bumps its agent's reputation. No workflows to define. No steps to configure. Just delegate.

Out of the box the chain runs *inside* the app process (`CHAIN_TARGET=local`), so it needs no keys, no tokens and no network. Point `CHAIN_TARGET` at `monad-testnet` and the same code records the same proofs on a public network.

## Setup

Create `backend/.env` from the example and fill in provider/tool keys:

```bash
cd backend
cp .env.example .env
```

Required for normal agent runs:

```env
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...
```

Optional integrations:

```env
SLACK_WEBHOOK_URL=...
GITHUB_TOKEN=...
GITHUB_DEFAULT_REPO=owner/repo
```

## Test Locally

```bash
./scripts/test-local.sh
```

This installs backend/frontend dependencies, compiles backend Python files, and builds the frontend.

## Development

Terminal 1:

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000/app`.

## Production

### Render

Use Render for the managed cloud deployment. The repo includes `render.yaml`, so Render can create the web service, Docker build, health check, and persistent disk from the Blueprint.

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from the repo.
3. Use the generated `mergit` web service.
4. Set these environment variables in Render:

```env
FRONTEND_URL=https://your-render-or-custom-domain
CORS_ORIGINS=https://your-render-or-custom-domain
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...
```

Optional integrations:

```env
SLACK_WEBHOOK_URL=...
GITHUB_TOKEN=...
GITHUB_DEFAULT_REPO=owner/repo
OAUTH_GOOGLE_CLIENT_ID=...
OAUTH_GOOGLE_CLIENT_SECRET=...
OAUTH_GOOGLE_REDIRECT_URI=https://your-render-or-custom-domain/api/auth/google/callback
OAUTH_GITHUB_CLIENT_ID=...
OAUTH_GITHUB_CLIENT_SECRET=...
OAUTH_GITHUB_REDIRECT_URI=https://your-render-or-custom-domain/api/auth/github/callback
```

Open:

```text
https://your-render-or-custom-domain/app
```

The Render service mounts a persistent disk at `/data`. The app stores state at `/data/mergit.db`, `/data/workspace`, and `/data/config`.

Run one instance only. The planner/executor worker starts inside the FastAPI lifespan, so multiple app instances would start multiple internal workers.

### One container, no proxy

The fastest way to see the production image work — useful before you point a domain at anything. Works the same with `docker` in place of `podman`:

```bash
podman build -t mergit:local -f Dockerfile .
podman run -d --name mergit -p 8000:8000 \
  -e GROQ_API_KEY="$GROQ_API_KEY" \
  -v mergit_data:/data \
  mergit:local

curl -s localhost:8000/api/health
```

A healthy response reports the chain the container actually brought up:

```json
{"status":"ok","db":"ok","worker":"running","chain":"ready","chain_id":31337}
```

`"chain":"disabled"` there means the contracts did not compile in the image — the app keeps serving, so the health check alone would not tell you.

### Docker / Podman Compose

Use this if you deploy to your own VPS instead of Render. Every `docker compose` command below works as `podman-compose` (or `podman compose`) unchanged.

The production deployment is a Docker Compose stack:

- `mergit`: one FastAPI process that serves the built frontend and runs the internal planner/executor worker.
- `caddy`: HTTPS reverse proxy with automatic TLS certificates.
- `mergit_data`: persistent volume for SQLite and agent workspace files.

```bash
cp .env.production.example .env.production
```

Edit `.env.production` and set:

```env
DOMAIN=your-domain.com
FRONTEND_URL=https://your-domain.com
CORS_ORIGINS=https://your-domain.com
AUTH_SECRET_KEY=replace-with-a-long-random-secret
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
TAVILY_API_KEY=...
```

Point your domain's `A` record at the server, then start the stack:

```bash
docker compose --env-file .env.production up -d --build
```

Open `https://your-domain.com/app`.

Check health and logs:

```bash
curl https://your-domain.com/api/health
docker compose --env-file .env.production logs -f mergit
```

Create a SQLite backup from the running container:

```bash
./deploy/backup-sqlite.sh
```

Run one app container and one uvicorn worker for now. The planner/executor worker starts inside the FastAPI lifespan, so multiple app replicas would start multiple internal workers. The production container stores state at `/data/mergit.db`, `/data/workspace`, and `/data/config`.
