# omniBox
Assign any goal to an AI. It decomposes the task, spins up specialized agents, uses your tools, and delivers results. No workflows to   define. No steps to configure. Just delegate.

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
OMIUM_API_KEY=...
OMIUM_SKIP_WORKFLOW_REGISTER=true
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

```bash
./scripts/run-prod.sh
```

Open `http://localhost:8000`. The backend serves `frontend/dist` directly in production.

Run one uvicorn process for now. The planner/executor worker starts inside the FastAPI lifespan, so multiple uvicorn workers would start multiple internal workers.
