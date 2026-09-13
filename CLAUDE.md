# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (first time)
make install                # creates backend/.venv + installs Python deps + npm install

# Development (two terminals, or run together)
make dev-backend            # backend on :8000 (cd backend && .venv/bin/python main.py)
make dev-frontend           # frontend on :3000 with /api proxy to :8000

# Or both at once
make dev

# Build frontend for production (served by FastAPI at /)
make build

# Reset database
make reset-db
```

The backend venv is at `backend/.venv/`. Always use `.venv/bin/python` for backend work.

## Architecture

omniBox is a generic multi-agent autonomy system: a user submits any natural language goal, the orchestrator (Claude) decomposes it into a task DAG, and specialized worker agents execute each task using tools, with full persistence for restart-resumability.

### Backend (`backend/`)

**Entry point**: `main.py` — FastAPI app with lifespan that initializes DB, starts the worker, and optionally serves the frontend static build.

**Core execution loop** (`worker.py`):
- `goal_planner_loop` — polls NEW goals → calls `orchestrator.run_plan()` → creates task rows
- `task_executor_loop` — polls READY tasks → runs `agent_runner.run()` — up to 5 concurrent (Semaphore)
- `reclaim_loop` — every 30s, reclaims RUNNING tasks with expired leases back to READY

**Orchestrator** (`orchestrator.py`): Claude (`claude-sonnet-4-20250514`) via forced tool call → `PlanSchema` (task DAG JSON). Retries 3x on `ValidationError`.

**Agent runner** (`agent_runner.py`): Generic LLM tool-call loop. Reads agent config from `AGENT_REGISTRY`, calls `acompletion()` in a loop until the agent calls `submit_result`. Idempotency: each tool invocation is hashed and cached in `tool_calls` table — re-runs return the stored result without re-firing.

**Agents** (`agent_registry.py`): `researcher` (Groq 70b, web_search), `writer` (Groq 70b, file_ops), `notifier` (Groq 8b, slack_notify), `coder` (Groq 70b, code_exec), `integrator` (Groq 70b, github_pr/wait_webhook). All go through the same `agent_runner.run()`.

**Tools** (`tools/`): `web_search` (Tavily), `http_request` (httpx), `slack_notify`, `file_ops` (workspace-scoped), `github_pr`, `code_exec` (subprocess), `wait_webhook` (suspends task to `WAITING_WEBHOOK` state).

**Persistence** (`db.py`): SQLite WAL mode, `aiosqlite`. Tables: `goals`, `tasks`, `messages`, `tool_calls`. Task claim is atomic via `UPDATE ... WHERE id=(SELECT ... LIMIT 1) RETURNING *`.

**SSE** (`events.py` + `api/stream.py`): In-process `asyncio.Queue` per goal. Worker calls `events.emit()`, stream endpoint drains the queue via Server-Sent Events.

**Interpolation** (`interpolation.py`): Resolves `{{task_id.output.field}}` templates in task inputs before execution.

**Tracing** (`tracing.py`): Omium SDK wrapper — degrades to no-ops if `omium` not installed. `trace_id` stored in DB so workers reconstitute causal context after restart.

### Frontend (`frontend/`)

Vite + React + TypeScript + Tailwind CSS + Framer Motion + React Flow + SWR.

- `pages/Dashboard.tsx` — goal list + submission input
- `pages/GoalDetail.tsx` — split-pane: task DAG (React Flow) + expandable task panels + live SSE log
- `lib/api.ts` — fetch wrappers for all API endpoints
- `lib/sse.ts` — `useSSE()` hook — `EventSource` auto-reconnect

In dev, Vite proxies `/api/*` to `:8000`. In production, FastAPI serves `frontend/dist/` at `/`.

### API

All routes under `/api/`. Key: `POST /api/goals`, `GET /api/goals/{id}`, `GET /api/goals/{id}/stream` (SSE), `POST /api/webhooks/{token}` (resume WAITING_WEBHOOK tasks).

### Environment

Copy `backend/.env.example` to `backend/.env` and fill in: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `TAVILY_API_KEY`, `SLACK_WEBHOOK_URL`, `GITHUB_TOKEN`, `OMIUM_API_KEY`.
