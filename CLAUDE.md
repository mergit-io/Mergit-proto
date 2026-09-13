# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Update Protocol

After every piece of work completed in this repo, update **both** files:
- `CLAUDE.md` — keep architecture section current (models, new files, changed behaviour)
- `progress.md` — append a new dated session block describing what was built/fixed

---

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

---

## Architecture

omniBox is a generic multi-agent autonomy system: a user submits any natural language goal, the orchestrator decomposes it into a task DAG, and specialized worker agents execute each task using tools, with full persistence for restart-resumability.

### Backend (`backend/`)

**Entry point**: `main.py` — FastAPI app with lifespan that initializes DB, starts the worker, registers all routers, and optionally serves the frontend static build.

**Core execution loop** (`worker.py`):
- `goal_planner_loop` — polls NEW goals → calls `orchestrator.run_plan()` → creates task rows
- `task_executor_loop` — polls READY tasks → runs `agent_runner.run()` — up to 5 concurrent (Semaphore)
- `reclaim_loop` — every 30s, reclaims RUNNING tasks with expired leases back to READY

**Orchestrator** (`orchestrator.py`): Uses the model from `model_config.get_model("orchestrator")` (defaults to `groq/llama-3.3-70b-versatile`). Forced tool call → `PlanSchema` (task DAG JSON). Retries 5x with rate-limit backoff. Handles Groq `tool_use_failed` by salvaging the plan from `failed_generation` in the error response (`_salvage_failed_generation()`). Falls back to `tool_choice="auto"` on attempts 2+. Task IDs are prefixed with `goal.id[:8]_` to avoid UNIQUE constraint collisions. `_rewrite_templates()` rewrites `{{t1.output.field[0]}}` refs to include the prefix.

**Agent runner** (`agent_runner.py`): Generic LLM tool-call loop. Reads agent config via `get_agent_config(name)` (reads live model from `model_config` on every call), calls `acompletion()` in a loop until the agent calls `submit_result`. Idempotency: each tool invocation is hashed and cached in `tool_calls` table — re-runs return the stored result without re-firing. Includes: exponential backoff for rate limits, retry-hint injection for Groq `tool_use_failed` errors, `consecutive_errors` counter that forces a "use your knowledge and submit NOW" message after 3 consecutive tool failures, and an early-warning nudge at `max_iter - 3`.

**Agents** (`agent_registry.py`): `researcher` (web_search, http_request), `writer` (file_ops), `notifier` (slack_notify, http_request), `coder` (code_exec, file_ops, web_search), `integrator` (github_pr, http_request, wait_webhook). All go through the same `agent_runner.run()`. Use `get_agent_config(name)` — not `AGENT_REGISTRY[name]` directly — to get the live model setting.

**Model config** (`model_config.py`): Per-role model store. Defaults all roles to Groq. Persists to `backend/model_config.json` (gitignored). `get_model(role)`, `get_all()`, `update(dict)`. Cache invalidated on write. 40 predefined models across Groq (Llama 4, Llama 3.x, DeepSeek, Qwen, Mixtral, Gemma), Anthropic (Claude 4/3.5/3), OpenAI (GPT-4o, o-series, GPT-3.5), Google (Gemini 2.5/2.0/1.5), Mistral (Large/Medium/Small/Codestral). Any LiteLLM-compatible string also accepted.

**Tools** (`tools/`): `web_search` (Tavily → DuckDuckGo fallback → training-knowledge note), `http_request` (httpx), `slack_notify`, `file_ops` (workspace-scoped, path traversal protected), `github_pr`, `code_exec` (subprocess, 30s timeout), `wait_webhook` (suspends task to `WAITING_WEBHOOK` state).

**Persistence** (`db.py`): SQLite WAL mode, `aiosqlite`. Tables: `goals`, `tasks`, `messages`, `tool_calls`. Task claim is atomic via `UPDATE ... WHERE id=(SELECT ... LIMIT 1) RETURNING *`.

**SSE** (`api/stream.py` + `events.py`): In-process `asyncio.Queue` per goal. Worker calls `events.emit()`, stream endpoint drains the queue via Server-Sent Events.

**Interpolation** (`interpolation.py`): Resolves `{{task_id.output.field}}` templates in task inputs before execution. Supports array index access (`{{id.output.key_points[0]}}`) and nested paths (`{{id.output.field[0].subfield}}`). `_resolve_path()` splits on `.` and `[N]` segments.

**API Keys** (`api/keys.py`): `GET/PUT /api/config/keys` — reads/writes provider API keys (Groq, Anthropic, OpenAI, Google, Mistral, Tavily) to `backend/.env` via `python-dotenv.set_key()` and updates `os.environ` immediately. Returns masked values.

**Tracing** (`tracing.py`): Omium SDK wrapper — degrades to no-ops if `omium` not installed. Provides `goal_trace_context`, `task_span`, `tool_span`, `webhook_span` context managers. All spans share `execution_id = goal.trace_id` for causal linking in the Omium dashboard.

### Frontend (`frontend/`)

Vite + React + TypeScript + Tailwind CSS + Framer Motion + React Flow + SWR.

- `pages/Dashboard.tsx` — goal list + submission input, stats strip, status filters
- `pages/GoalDetail.tsx` — split-pane: task DAG (React Flow) + expandable task panels + live SSE log
- `components/AppNav.tsx` — sticky nav with Dashboard / Models / API Docs links; active-route highlighting
- `pages/Models.tsx` — full-page model config at `/app/models`; Visual tab (per-role cards + custom model input) and JSON tab (raw editor + live validation); API Keys section (all 6 providers, inline key input, saves to `.env` live)
- `components/ModelErrorBanner.tsx` — centered modal that appears on goal failure when error is key/quota related; detects provider from error string; inline key input + "Change model" button
- `lib/api.ts` — fetch wrappers for all API endpoints including `getModelConfig`, `updateModelConfig`, `getApiKeys`, `updateApiKey`
- `lib/sse.ts` — `useSSE()` hook — `EventSource` auto-reconnect

In dev, Vite proxies `/api/*` to `:8000`. In production, FastAPI serves `frontend/dist/` at `/`.

### API

All routes under `/api/`. Key endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/goals` | Submit goal → 202 |
| GET | `/api/goals` | List goals |
| GET | `/api/goals/{id}` | Full status + tasks + output |
| GET | `/api/goals/{id}/stream` | SSE event stream |
| GET | `/api/config/models` | Get per-role model config |
| PUT | `/api/config/models` | Update per-role model config |
| GET | `/api/config/keys` | Get provider API key status (masked) |
| PUT | `/api/config/keys` | Save provider API key to `.env` + `os.environ` |
| POST | `/api/webhooks/{token}` | Resume WAITING_WEBHOOK task |
| GET | `/api/health` | Health check |

### Environment

Copy `backend/.env.example` to `backend/.env` and fill in: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `TAVILY_API_KEY`, `SLACK_WEBHOOK_URL`, `GITHUB_TOKEN`, `GITHUB_DEFAULT_REPO`, `OMIUM_API_KEY`, `OMIUM_PROJECT`.

Model selection is managed at runtime via `backend/model_config.json` (created automatically on first run, gitignored). Edit through the UI "Models" button or directly via `PUT /api/config/models`.
