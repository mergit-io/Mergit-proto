# omniBox — Progress Log

Track of every significant piece of work completed. Update this after each session.

---

## Session 1 — Initial Prototype
**Commit:** `ca12e75 [init] initial prototype of the omniBox`

- Scaffolded the full project: FastAPI backend + Vite/React/TypeScript frontend
- Implemented SQLite WAL schema: `goals`, `tasks`, `messages`, `tool_calls` tables
- Built `orchestrator.py` — Claude forced tool call → `PlanSchema` task DAG
- Built `agent_runner.py` — generic LLM tool-call loop with `submit_result`
- Built `worker.py` — three asyncio loops: goal planner, task executor, lease reclaim
- Built all 7 tools: `web_search`, `http_request`, `slack_notify`, `file_ops`, `github_pr`, `code_exec`, `wait_webhook`
- Built `interpolation.py` — resolves `{{task_id.output.field}}` templates
- Built SSE streaming — in-process `asyncio.Queue` per goal, `EventSource` on frontend
- Built all API routes: `POST /api/goals`, `GET /api/goals/{id}`, `GET /api/goals/{id}/stream`, `POST /api/webhooks/{token}`, `GET /api/health`
- Basic React frontend: Dashboard (goal list + submit), GoalDetail (tasks + live log)
- LiteLLM as multi-provider wrapper (`anthropic/...`, `groq/...` prefixes)

---

## Session 2 — UI/UX Overhaul
**Commit:** `232fef6 [ui/ux] improved the ui ux of the site`

- Redesigned full frontend with dark glassmorphism aesthetic
  - Near-black `#0a0a0a` background, `#111` cards
  - Electric blue accent (`#3b82f6`) + status colors (green/red/amber)
  - Inter font, tight tracking, monospace for output
  - Framer Motion animations: page transitions, staggered card entrances, pulsing status badges
- Created `Landing.tsx` — marketing landing page at `/` with hero, features section, CTA
- Rewrote `Dashboard.tsx`:
  - `StatsStrip` — 4-stat grid (Active/Completed/Failed/Total)
  - `EmptyState` — animated bot icon with glow
  - Status filter tabs (All / RUNNING / COMPLETED / FAILED)
  - `AnimatePresence` for goal list transitions
  - Error display for submit failures, skeleton loading cards
- Rewrote `GoalCard.tsx` — relative timestamps, blue glow strip on left for active goals
- Rewrote `GoalInput.tsx` — focus glow border, animated hint text, char count
- Rewrote `GoalDetail.tsx` — better error state, planning spinner, `isLoading` handling
- Created `AppNav.tsx` — sticky glassmorphic nav (logo, Dashboard, API Docs links)

---

## Session 3 — Bug Fixes, Tracing, Backend Hardening

### Bug Fixes
- **LiteLLM tool_choice format** — Changed orchestrator `tool_choice` from `{"type":"function","name":"..."}` to `{"type":"function","function":{"name":"..."}}` (OpenAI format required by LiteLLM)
- **Task ID UNIQUE constraint** — Orchestrator reused short IDs (`t1`, `t2`) per goal, causing DB conflicts on the second goal. Fixed by prefixing all task IDs with `goal.id[:8]_` in `run_plan()`. Added `_rewrite_templates()` to rewrite `{{t1.output.field}}` refs to match new IDs.
- **`_truncate_args` NameError** — Function used in `tool_span()` but never defined. Added definition in `tracing.py`.
- **`file_ops` path traversal check** — `WORKSPACE` was relative; `full_path.relative_to()` raised `ValueError` on absolute-vs-relative mismatch. Fixed to `Path(settings.workspace_dir).resolve()`. Also strips absolute LLM-injected paths via `os.path.basename()`.
- **Groq rate limits** — Added exponential backoff `wait = min(2 ** iteration, 30)` in `agent_runner.py`
- **Groq `tool_use_failed`** — Added retry hint injection + `_try_parse_json_result()` fallback parser
- **Orchestrator retry count** — Raised from 3 to 5 attempts with rate-limit backoff

### Omium Tracing (full coverage for +10% bonus)
- Rewrote `tracing.py` entirely:
  - `init_tracing()` — initialises Omium SDK with `auto_trace=False`
  - `goal_trace_context()` — context manager creating `OmiumTracer` scoped to one goal, opens `goal_run` root span
  - `task_span()` — context manager for `task/{agent_name}` spans
  - `tool_span()` — context manager for `tool/{tool_name}` spans; tags `cached=true` for replayed idempotent calls
  - `webhook_span()` — context manager for `webhook_resume` spans
  - `_truncate_args()` — strips `_`-prefixed internal keys, truncates long strings to 300 chars
  - All functions degrade gracefully to no-ops if `omium` not installed
- Updated `worker.py` — wraps orchestrator call in `goal_trace_context`, opens `task_span` per task execution
- Updated `agent_runner.py` — `tracer` param threaded through, `tool_span` wraps every tool call, sets error/output attributes
- Updated `api/webhooks.py` — wraps webhook processing in `webhook_span`
- Causal linking: all spans share `execution_id = goal.trace_id` (UUID stored in DB), so full trace appears as one chain in Omium dashboard

### Backend Logging
- `main.py` — `logging.basicConfig` with structured format, silences `httpx`/`litellm`/`anthropic`/`openai` noise
- Request logging middleware logs method/path/status/timing per request
- Unhandled exception handler returns JSON `{detail, request_id}`

### config.py
- Added `debug: bool = False` setting

### Landing Page Background Fix
- Fixed background disappearing after scrolling — changed to `position: fixed` at `z-0` with content at `z-10`
- Added dot grid overlay and 5 ambient orbs at `top`/`120vh`/`240vh`/`360vh` for coverage throughout full page scroll

---

## Session 4 — Per-Role Model Configuration

### Goal
User requested: default all agents to Groq only; provide a UI section where each agent role's model can be independently configured (e.g. use Claude for orchestrator, Groq for leaf agents).

### Backend
- **`backend/model_config.py`** (new) — Per-role model store
  - `DEFAULTS` — all roles default to Groq (`llama-3.3-70b-versatile`, notifier uses `llama-3.1-8b-instant`)
  - `AVAILABLE_MODELS` — 5 models: Groq 70B versatile, Groq 70B 3.1, Groq 8B instant, Claude Haiku 4.5, Claude Sonnet 4.6
  - `get_model(role)` / `get_all()` / `update(dict)` — read/write with JSON file persistence
  - Persists to `backend/model_config.json` (gitignored)
  - In-process cache; merges saved config with DEFAULTS so new roles always have a value

- **`backend/api/config.py`** (new) — REST endpoints
  - `GET /api/config/models` — returns `{models, available, defaults}`
  - `PUT /api/config/models` — validates role names + model IDs, saves and returns updated config

- **`backend/orchestrator.py`** — reads orchestrator model via `model_config.get_model("orchestrator")` at call time (no more hardcoded model constant); added JSON-body fallback for when Groq ignores forced tool_choice

- **`backend/agent_registry.py`** — added `get_agent_config(name)` which overlays the live model config on top of the static registry dict

- **`backend/agent_runner.py`** — uses `get_agent_config(task.agent_name)` instead of static `AGENT_REGISTRY[...]` so model changes take effect immediately

- **`backend/main.py`** — registers `config.router` at `/api/config`

### Frontend
- **`frontend/src/lib/api.ts`** — added `ModelOption`, `ModelConfig` types + `getModelConfig()` and `updateModelConfig()` API methods

- **`frontend/src/components/ModelSettings.tsx`** (new) — full settings modal
  - One card per role (Orchestrator, Researcher, Writer, Notifier, Coder, Integrator) with icon, label, description
  - Per-role `ModelSelect` dropdown showing all available models with provider/tier labels
  - Provider color coding: Groq = emerald, Anthropic = violet
  - Save button (active only when dirty), Reset to defaults, error display
  - Framer Motion backdrop + panel entrance animation

- **`frontend/src/components/AppNav.tsx`** — added "Models" button (gear icon) that opens `ModelSettings` modal

### Other
- **`.gitignore`** (new) — covers `backend/.env`, `backend/model_config.json`, `backend/omnibox.db`, `backend/workspace/`, `frontend/node_modules/`, `frontend/dist/`, `__pycache__/`

---

---

## Session 5 — Researcher Failure Bug Fix + Web Search Resilience

### Bug
`researcher` agent failing with "did not call submit_result within 8 iterations". Root cause confirmed via DB inspection: `web_search` was returning `{"error": "Unauthorized: missing or invalid API key."}` on every call (Tavily key was placeholder). The model saw the error and retried the same tool all 8 iterations, never calling `submit_result`.

### Fixes

**`backend/tools/web_search.py`** — Tiered search with graceful fallback:
1. Try Tavily first — only if key is set and not the `tvly-...` placeholder
2. Fall back to DuckDuckGo Instant Answer API (free, no key needed) — returns abstract + related topics
3. Final fallback: returns `{"results": [], "note": "Web search unavailable. Use your training knowledge to answer about: <query>"}` — tells the model exactly what to do instead of returning a cryptic error

**`backend/agent_runner.py`** — Added two safety mechanisms:
- `consecutive_errors` counter — when 3+ consecutive tool calls fail, injects: *"These tools are failing: X. Stop calling them. Use your training knowledge and call submit_result NOW."*
- `_failing_tools` set — tracks which tools failed so the nudge message names them explicitly
- Early warning at `max_iter - 3` iterations — tells model to wrap up
- Stronger final nudge: "Call submit_result NOW. Do not call any other tools."
- `consecutive_errors` resets to 0 after a successful tool call and after the forced-submit injection

**`backend/agent_registry.py`** — Updated researcher:
- System prompt now explicitly says: "If web_search returns a 'note' field saying it's unavailable, do NOT retry it — answer from your training knowledge"
- System prompt says: "If any tool fails twice in a row, stop calling it"
- `max_iterations` increased from 8 → 10
- `allowed_tools` already included `http_request` (can fetch arbitrary URLs/APIs as an alternative search path)

### How it works now
- Tavily key present → uses Tavily (fast, rich results)
- Tavily key missing/invalid → DuckDuckGo free API (no key needed)
- DuckDuckGo returns nothing → model gets a note saying "use your knowledge" → submits answer from training data
- Any tool fails 3× in a row → forced submit message injected regardless of which tool it is

---

---

## Session 6 — Provider Fallback Chain (Groq Daily Token Limit)

### Bug
Groq free tier has a **100K tokens/day (TPD)** limit per model. After testing, `llama-3.3-70b-versatile` hit its daily quota → orchestrator failed on all 5 retry attempts with the same provider error. No fallback existed.

### Fix — `backend/llm.py`
Added `_FALLBACKS` dict: when a model hits a hard rate limit (daily quota / `tokens per day`), `acompletion()` automatically tries the next model in the chain before raising.

Fallback chains:
- `groq/llama-3.3-70b-versatile` → `groq/llama-3.1-8b-instant` → `anthropic/claude-haiku-4-5-20251001`
- `groq/llama-3.1-8b-instant` → `anthropic/claude-haiku-4-5-20251001`
- `anthropic/claude-haiku-4-5-20251001` → `groq/llama-3.1-8b-instant` → `groq/llama-3.3-70b-versatile`

Added `_is_hard_rate_limit()` (daily quota / TPD → switch provider) vs `_is_soft_rate_limit()` (TPM / per-minute → caller backs off with sleep). Only hard limits trigger a fallback; soft limits are left for the caller's existing retry logic in `agent_runner.py`.

---

---

## Session 7 — Dedicated Model Configuration Page (`/app/models`)

### What was built
Full-page model configuration at `/app/models` replacing the modal approach. Two editor modes that stay in sync.

**`frontend/src/pages/Models.tsx`** (new):
- **Visual Editor tab** — per-role cards (Orchestrator / Researcher / Writer / Notifier / Coder / Integrator), each with a `ModelPicker` dropdown
  - Grouped by provider (Groq / Anthropic sections)
  - Tier badges (Fast / Instant / Powerful)
  - **Custom model ID** entry — "Custom model ID…" option opens an inline text input accepting any `provider/model-name` string (e.g. `openai/gpt-4o`, `mistral/mistral-large-latest`)
- **JSON Editor tab** — raw textarea with line numbers, live validation
  - Parses on every keystroke; shows inline error for invalid JSON or unknown roles
  - Syncs to/from Visual tab bidirectionally
- **Available Models reference table** — shows all suggested models with provider/tier badges; notes any LiteLLM-compatible ID also works
- Save/Reset buttons with dirty-state detection

**`frontend/src/App.tsx`** — added `/app/models` route

**`frontend/src/components/AppNav.tsx`** — "Models" link now navigates to `/app/models` (active highlight when on that page); removed modal dependency

**`backend/model_config.py`** — relaxed validation: any non-empty string is accepted as a model ID (not just predefined list). Custom provider IDs (openai/, mistral/, cohere/, etc.) now work.

**Provider detection** — `detectProvider()` auto-detects provider from model ID prefix and applies color coding:
- `groq/` → emerald
- `anthropic/` → violet
- `openai/` → blue
- `cohere/` → orange
- `mistral/` → amber
- unknown → white (custom)

---

---

## Session 8 — UI/UX Consistency Across All App Pages

### Problem
Landing page (`/`) had the full design treatment: fixed dot-grid background + ambient orbs + glassmorphism. All three `/app` pages (Dashboard, GoalDetail, Models) had flat `bg-black` — no dot grid, no orbs, cards looked opaque and lifeless.

### Fix

**`frontend/src/components/AppBackground.tsx`** (new) — shared fixed background component:
- Same dot grid (32px, opacity 0.14) as Landing
- Top-right accent orb (blue→purple, `blur(90px)`, animated with `glow-pulse`)
- Bottom-left purple orb (opacity 0.15, `blur(100px)`, delay 1.8s)
- Subtle centre wash orb (very low opacity 0.06)
- `fixed inset-0 z-0 pointer-events-none` — sits behind all content

**All three app pages updated** (`Dashboard.tsx`, `GoalDetail.tsx`, `Models.tsx`):
- Root div changed from `min-h-screen bg-black` → `relative min-h-screen` with `background: "#000"`
- `<AppBackground />` inserted at root
- Content wrapped in `relative z-10 flex flex-col min-h-screen`

**GoalDetail panes** — changed from opaque `bg-black` to `bg-black/20 backdrop-blur-sm` and `bg-black/30 backdrop-blur-sm` so the dot grid and orbs show through the split panes.

**Dashboard filter bar** — changed from opaque `bg-surface border-border` to `bg-black/30 backdrop-blur-sm border-white/8` for consistency.

---

---

## Session 9 — Interpolation Array Index Fix

### Bug
Two task failures observed:
1. **`56002610_t2` researcher** — "did not call submit_result within 10 iterations". Root cause: agent received raw unresolved template strings like `{{t1.output.key_points[0]}}` as literal text in its inputs.
2. **`56002610_t3` writer** — "Interpolation error: '56002610_t2'" — t3 depended on t2 output, but t2 failed because its inputs were never resolved.

Two bugs working together:
- `_rewrite_templates()` in `orchestrator.py` used regex `r"\{\{(\w+)(\.output\.\w+)\}\}"` — the `\.output\.\w+` segment does not match `[0]` (array index), so `{{t1.output.key_points[0]}}` was silently NOT rewritten with the goal prefix. The template survived as `{{t1.output.key_points[0]}}` (unprefixed) into the DB.
- `TEMPLATE_RE` in `interpolation.py` used `r"\{\{(\w+)\.output\.(\w+)\}\}"` — same problem: `(\w+)` doesn't match `key_points[0]`, so the template was never resolved at execution time.

### Fixes

**`backend/interpolation.py`**:
- New `TEMPLATE_RE = re.compile(r"\{\{(\w+)\.output\.([\w\[\]\.0-9]+)\}\}")` — path group now matches `field`, `field[0]`, `field[0].subfield`
- New `_resolve_path(obj, path)` — splits on `.` then on `[N]` within each segment; traverses dicts by key and lists by integer index
- `resolve_value()` now calls `_resolve_path(task_outputs[task_id], path)` instead of a direct dict key lookup

**`backend/orchestrator.py`** `_rewrite_templates()`:
- `TMPL` regex updated to `r"\{\{(\w+)(\.output\.[\w\[\]\.0-9]+)\}\}"` — group 2 now captures the full path including array indices
- No logic change — the substitution lambda still uses `id_map.get(m.group(1), m.group(1))` which is correct

---

---

## Session 10 — Orchestrator Groq `tool_use_failed` Fix

### Bug
Goal immediately transitions PLANNING → FAILED with:
`litellm.BadRequestError: GroqException - {"code":"tool_use_failed","failed_generation":"<function=submit_plan> {...} </function>"}`

Root cause: Groq generates the plan correctly but uses an XML-function format (`<function=submit_plan>`) instead of a proper JSON tool call. Groq itself rejects this as malformed and returns a 400 `BadRequestError`. The orchestrator's `except Exception` block only retried on rate limits — for any other exception it raised immediately, causing the goal to fail.

The plan JSON was right there in `failed_generation` but was never extracted.

### Fix — `backend/orchestrator.py`

1. **`_salvage_failed_generation(error_str)`** (new helper): Extracts JSON from Groq's `failed_generation` field. Handles both the direct `<function=name> {...} </function>` pattern and the escaped JSON string form in the error response.

2. **`tool_use_failed` handler in the retry loop**: When a `BadRequestError` with `tool_use_failed` is caught:
   - First tries to salvage the plan directly from `failed_generation`
   - If salvage succeeds and validates, returns the plan immediately (no extra round-trip)
   - If salvage fails, `continue`s to the next attempt

3. **Progressive `tool_choice` relaxation**: Attempts 0-1 use forced `{"type":"function","function":{"name":"submit_plan"}}`. Attempts 2+ fall back to `"auto"` — lets Groq choose when to call the tool, avoiding the format mismatch that causes `tool_use_failed`.

4. Removed stray `import re` inside `plan()` — now uses module-level import.

---

## Session 11 — PR Follow-Up: Ecosystem Icons + Crash Hardening

### User Request
User pointed out that the PR ecosystem icon fix had not been implemented, asked what the Omium crash list meant, and requested that `progress.md` be updated after every prompt going forward.

### Frontend
- **`frontend/src/components/landing/PartnersMarquee.tsx`**
  - Replaced the nearly invisible generic square placeholders with visible branded ecosystem badges.
  - Added per-partner accent colors and monogram marks for Anthropic, Groq, Tavily, LiteLLM, FastAPI, ReactFlow, Framer Motion, and SQLite.
  - Kept the implementation dependency-free because `npm install simple-icons` hung in the sandboxed environment.

- **`frontend/src/components/AppNav.tsx`**
  - Fixed production build failure: current `lucide-react` package does not export `Github`.
  - Replaced `Github` with existing `GitBranch` icon.

### Backend Crash Hardening
- **Crash class 1: Groq malformed tool calls**
  - Omium showed `tool call validation failed` / `tool_use_failed` errors where Groq generated malformed function-call syntax such as embedding JSON in the tool name.
  - Existing recovery handles `<function=...>` failed generations; now `tool call validation failed` is also treated as a retryable model-format failure so the agent receives a stricter tool-call hint instead of immediately crashing.

- **Crash class 2: Groq rate limits**
  - Omium showed repeated `litellm.RateLimitError` entries for Groq `llama-3.3-70b-versatile`.
  - `backend/llm.py` now retries short soft rate limits internally using parsed `try again in ...` delays.
  - Long waits or hard quota errors still trigger the existing fallback chain to another model.

### Verification
- `backend/.venv/bin/python -m py_compile llm.py agent_runner.py`
- `npm run build`

---

## Session 12 — Compile Command Path Clarification

### User Request
User ran `backend/.venv/bin/python -m py_compile llm.py agent_runner.py` from the repo root and got `[Errno 2] No such file or directory: 'llm.py'`.

### Clarification
- `llm.py` and `agent_runner.py` live inside `backend/`.
- From repo root, use:
  - `backend/.venv/bin/python -m py_compile backend/llm.py backend/agent_runner.py`
- Or first `cd backend`, then use:
  - `.venv/bin/python -m py_compile llm.py agent_runner.py`

### Verification
- Confirmed both corrected commands pass.

---

---

## Session 13 — Model Error UX, API Keys UI, Full Model Catalogue

### Model Error Banner
- **`frontend/src/components/ModelErrorBanner.tsx`** (new) — centered modal with dark backdrop
  - Detects `invalid_api_key`, quota exceeded, rate limit from goal error string
  - Detects failing provider (Groq/Anthropic/OpenAI/Google/Mistral) from error text
  - **"Add API key"** button expands inline password input (show/hide toggle) to save key immediately
  - **"Change model"** button navigates to `/app/models`
  - Dismiss closes; clicking backdrop closes
  - Fixed centering: backdrop is `fixed inset-0 flex items-center justify-center` — not affected by Framer Motion ancestor transforms
- Wired into `GoalDetail.tsx` — appears whenever `data.error` contains a model error

### API Keys Section on Models Page
- **`backend/api/keys.py`** (new) — `GET /api/config/keys` + `PUT /api/config/keys`
  - Maps 6 providers → env var names (GROQ, ANTHROPIC, OPENAI, GOOGLE, MISTRAL, TAVILY)
  - Reads from both `os.environ` and `.env` file; writes via `python-dotenv.set_key()`
  - Updates `os.environ` immediately — no backend restart needed for key to take effect
  - Returns masked values (`first6...last4`)
- **`frontend/src/pages/Models.tsx`** — new `ApiKeysSection` component
  - One row per provider with color-coded badge, env var name, masked value / "Not set" status
  - Inline expand/collapse password input with show/hide toggle
  - Save writes to backend immediately
- **`frontend/src/lib/api.ts`** — added `getApiKeys()` and `updateApiKey()` methods

### Model Catalogue Expanded (40 models, 5 providers)
- **Groq**: Llama 4 Maverick/Scout, Llama 3.3/3.1/3.2 (70B→3B), DeepSeek R1 70B, Qwen QwQ 32B, Mixtral 8x7B, Gemma 2 9B
- **Anthropic**: Claude Opus 4.7, Sonnet 4.6, Haiku 4.5, Claude 3.5 Sonnet/Haiku, Claude 3 Opus
- **OpenAI**: GPT-4o/Mini, o3, o4-mini, o3-mini, o1, GPT-4 Turbo, GPT-3.5 Turbo
- **Google**: Gemini 2.5 Pro/Flash, 2.0 Flash/Lite, 1.5 Pro/Flash/Flash-8B
- **Mistral**: Large, Medium 3, Small 3, Codestral, Pixtral Large
- Provider detection updated: `gemini/` and `google/` → sky blue
- Dropdown: `overflow-y-auto max-h-72` (was clipping off-screen)

### AppNav — GitHub Link
- Added GitHub link (`https://github.com/viscous106/omniBox`) with `GitBranch` icon

### Bug Fixes
- **Makefile** — `dev-backend` used `$(PYTHON)` (root-relative path) after `cd backend`, causing "No such file" error. Fixed to `.venv/bin/python main.py`
- **Watchfiles spam** — silenced `watchfiles` logger in `main.py` logging setup
- **`reload_includes`/`reload_excludes`** added to uvicorn config to only watch `.py` files

---

## Known Issues / Pending

- **Tavily API key** — optional now (system falls back), but setting a real key gives better search results
- **React Flow / TaskDAG** — `TaskDAG.tsx` component exists in plan but may not be fully wired in `GoalDetail.tsx`
- **OutputDisplay** — final goal output rendering as markdown not yet verified end-to-end
- **Frontend bundle size** — single chunk ~686 kB; consider `React.lazy()` for React Flow if it becomes an issue
