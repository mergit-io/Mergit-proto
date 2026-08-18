# Mergit — Progress Log

Track of every significant piece of work completed. Update this after each session.

---

## 2026-07-19 — Ship the Mergit showcase prototype (issues #1–#7)

Built the missing backend economy engine and integrated + merged all outstanding showcase PRs end-to-end.

**Backend (Workstream A, #1 → PR #12):**
- 3 SQLite tables (`agent_passports`, `agent_reputation`, `proofs`) + accessors in `db.py`.
- `economy.py`: deterministic hashing + reputation math (composite 0..1000, Gold/Silver/Bronze badges, ±20% delta cap) + `seed_passports`/`recompute_role`/`record_proof`/`backfill`. `record_proof` never raises into the worker; emits `proof_recorded`/`reputation_update` on the `economy` SSE channel.
- `worker._after_task_done` mints a proof per completed task; `main.py` seeds + backfills on startup and registers `api/economy.py` (`/passports|leaderboard|proofs|agents/{role}|chain|stream`). `deployments/10143.json` mocks Monad testnet. 13 pytest cases pass.

**Integration + fixes:**
- Merged PRs #8 (C: DEMO_MODE + wallet), #9 (E: rebrand), #10 (B: economy UI), #11 (D: replay), #12 (A: backend) into `main` — AppNav auto-merged cleanly (Mergit wordmark + Economy link + WalletConnect).
- Reconciled the B frontend (was written against an imagined API) with the real backend: rewrote `lib/api.ts` economy types/fetchers (bare arrays, real fields) + all economy components/pages (badge + score bars, NFT-style passports with DID/soulbound/capabilities/mint block, tx/result-hash proof rows, `:role` route).
- Rewrote `scripts/replay_demo.py` to the real `record_proof(task, output)` interface. `seed_passports` now seeds a neutral reputation row per role so all 6 agents rank. Dropped unused `Bell` imports blocking `tsc -b`.

**Verified:** 13 backend tests pass; `npm run build` clean; replay mints 3 proofs (blocks 18100000+); live endpoints return chainId 10143, 6 passports, a 6-agent leaderboard. All 7 issues closed; all 5 PRs merged.

---

## Session 1 — Initial Prototype
**Commit:** `ca12e75 [init] initial prototype`

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

### Distributed tracing (full coverage for +10% bonus)
- Rewrote `tracing.py` entirely:
  - `init_tracing()` — initialises the tracing SDK with `auto_trace=False`
  - `goal_trace_context()` — context manager creating the tracer scoped to one goal, opens `goal_run` root span
  - `task_span()` — context manager for `task/{agent_name}` spans
  - `tool_span()` — context manager for `tool/{tool_name}` spans; tags `cached=true` for replayed idempotent calls
  - `webhook_span()` — context manager for `webhook_resume` spans
  - `_truncate_args()` — strips `_`-prefixed internal keys, truncates long strings to 300 chars
  - All functions degrade gracefully to no-ops if the tracing SDK is not installed
- Updated `worker.py` — wraps orchestrator call in `goal_trace_context`, opens `task_span` per task execution
- Updated `agent_runner.py` — `tracer` param threaded through, `tool_span` wraps every tool call, sets error/output attributes
- Updated `api/webhooks.py` — wraps webhook processing in `webhook_span`
- Causal linking: all spans share `execution_id = goal.trace_id` (UUID stored in DB), so full trace appears as one chain in the tracing dashboard

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
- **`.gitignore`** (new) — covers `backend/.env`, `backend/model_config.json`, `backend/mergit.db`, `backend/workspace/`, `frontend/node_modules/`, `frontend/dist/`, `__pycache__/`

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
User pointed out that the PR ecosystem icon fix had not been implemented, asked what the tracing crash list meant, and requested that `progress.md` be updated after every prompt going forward.

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
  - The tracing dashboard showed `tool call validation failed` / `tool_use_failed` errors where Groq generated malformed function-call syntax such as embedding JSON in the tool name.
  - Existing recovery handles `<function=...>` failed generations; now `tool call validation failed` is also treated as a retryable model-format failure so the agent receives a stricter tool-call hint instead of immediately crashing.

- **Crash class 2: Groq rate limits**
  - The tracing dashboard showed repeated `litellm.RateLimitError` entries for Groq `llama-3.3-70b-versatile`.
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
- Added GitHub link (the GitHub repo) with `GitBranch` icon

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

---

## Session 14 — Full Provider Fallback Chain + Gemini Key Bridging

### Problem
Goals were failing when using Gemini models. Two root causes:

1. **`gemini-2.5-pro` has zero free-tier quota** — hits `RESOURCE_EXHAUSTED` immediately. The fallback chain only had Groq ↔ Anthropic entries; no Gemini model was in `_FALLBACKS` so it raised immediately.
2. **`GEMINI_API_KEY` not set at startup** — `llm.py` only called `os.environ.setdefault` for Anthropic and Groq. Even if the user had `GOOGLE_API_KEY` in `.env`, LiteLLM wouldn't find it because it looks for `GEMINI_API_KEY`.
3. **`OPENAI_API_KEY` and `MISTRAL_API_KEY` not loaded** — same startup omission for those providers.

### Fixes

**`backend/config.py`**:
- Added `openai_api_key`, `gemini_api_key`, `google_api_key`, `mistral_api_key` settings fields so pydantic-settings reads them from `.env` at startup.

**`backend/llm.py`**:
- Added `os.environ.setdefault` calls for `OPENAI_API_KEY` and `MISTRAL_API_KEY`.
- Bridges `GOOGLE_API_KEY` → `GEMINI_API_KEY` at startup (uses whichever is set in `.env`).
- Extended `_FALLBACKS` to cover all 40 models across 5 providers:
  - Gemini paid (`gemini-2.5-pro`, `gemini-1.5-pro`) → Gemini free flash variants → Groq
  - Gemini free tier (`gemini-2.5-flash`, `gemini-2.0-flash`, etc.) → Groq fallback
  - OpenAI GPT-4o, o-series → cheaper OpenAI variants → Groq
  - Mistral Large/Medium/Small → smaller Mistral → Groq
  - All Anthropic models (Opus 4.7, Sonnet 4.6, Haiku 4.5, 3.5/3 series) → Groq
  - All Groq Llama 4/3.x/specialised models → smaller Groq variants → Anthropic Haiku
- Added `resource_exhausted` to `_is_hard_rate_limit()` for Gemini quota errors.

**`backend/api/keys.py`**:
- When user saves the `google` provider key, also writes `GEMINI_API_KEY` to `.env` and `os.environ` immediately.

### Result
- Gemini 2.5 Pro → falls back to Gemini 2.5 Flash → Gemini 2.0 Flash → Anthropic Haiku automatically
- All 5 providers fully initialised at startup from `.env`
- Key saved via UI takes effect without restart (both `GOOGLE_API_KEY` and `GEMINI_API_KEY` set)

---

## Session 15 — Gemini Deprecation & Fallback Chain Fix

### Diagnosis (live test, not guesswork)

Ran `acompletion` against every model in `model_config.json`:

| Model | Result |
|-------|--------|
| `gemini-2.5-pro` | QUOTA_EXCEEDED (free tier = 0) |
| `gemini-2.5-flash` | **OK** |
| `gemini-2.0-flash` | QUOTA_EXCEEDED (daily limit) |
| `gemini-2.0-flash-lite` | QUOTA_EXCEEDED |
| `gemini-1.5-flash` | **MODEL_NOT_FOUND** — deprecated by Google |
| `gemini-1.5-flash-8b` | **MODEL_NOT_FOUND** — deprecated |
| `gemini-1.5-pro` | **MODEL_NOT_FOUND** — deprecated |
| Groq models | **INVALID_KEY** |
| `anthropic/claude-haiku-4-5-20251001` | **OK** |

Three distinct failure modes: quota, deprecated model IDs, invalid Groq key.

### Fixes

**`backend/llm.py`**:
- Added `"not_found"`, `"model not found"`, `"404" + "model"` to `_is_hard_rate_limit()` — MODEL_NOT_FOUND now triggers the fallback chain instead of crashing immediately
- Rewrote Gemini fallback chains: removed all `gemini-1.5-*` references (deprecated), made `anthropic/claude-haiku-4-5-20251001` the reliable last resort (Anthropic key is valid, Groq key is not)
- `gemini-2.5-pro` → `gemini-2.5-flash` → `gemini-2.0-flash` → `anthropic/claude-haiku`
- `gemini-2.5-flash` → `gemini-2.0-flash` → `anthropic/claude-haiku` → Groq
- `gemini-2.0-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash` → `anthropic/claude-haiku`

**`backend/model_config.py`**:
- Removed all 3 deprecated Gemini 1.5 models from `AVAILABLE_MODELS`

**`backend/model_config.json`**:
- `coder`: `gemini-1.5-flash-8b` → `gemini/gemini-2.5-flash`
- `integrator`: `gemini-1.5-pro` → `gemini/gemini-2.5-flash`

### Confirmed working
`acompletion("gemini/gemini-2.5-pro", ...)` → hits quota → falls back to `gemini-2.5-flash` → SUCCESS (1 choice returned)

### Pending user action
Groq API key in `backend/.env` is invalid (rotated after GitHub exposure, not updated). Update it via the Models → API Keys section in the UI, or directly in `.env`.

---

## Session: 2026-05-15 — GitHub Automation Pivot

### Context
Hackathon mentor feedback: "research + summarize is too basic." Pivoted to the primary use case: **Autonomous GitHub Issue/PR Solver**. Zero human interaction: webhook fires → multi-agent pipeline → real PR created, comment posted.

### New files
- `backend/tools/github_ops.py` — 5 new GitHub tools: `github_read_file`, `github_list_dir`, `github_get_issue`, `github_post_comment`, `github_search_code`
- `backend/api/github_webhook.py` — `POST /api/webhooks/github` — receives GitHub webhook events (issues.opened, pull_request.opened, ping) and auto-creates goals. HMAC-SHA256 verification supported via `GITHUB_WEBHOOK_SECRET` env var (optional for local dev).
- `frontend/src/pages/Webhooks.tsx` — "GitHub Automation" page at `/app/webhooks`; webhook URL with copy, setup guide (ngrok steps), "Simulate GitHub Issue" form

### Updated files
**`backend/tools/__init__.py`**: Registered all 5 new `github_ops` tools in `TOOL_REGISTRY`

**`backend/agent_registry.py`**: 
- researcher: added github_read_file, github_list_dir, github_get_issue, github_search_code; output_schema gains `code_context` field; max_iterations 10→15
- coder: added github_read_file for reading existing code before writing fixes
- integrator: added github_post_comment, github_read_file; system_prompt updated with GitHub automation guidance

**`backend/orchestrator.py`**:
- Agent descriptions updated to mention GitHub tools
- Rules 8+9 expanded with GitHub automation patterns
- Rule 10 added: explicit "researcher→coder→integrator" 3-task DAG for GitHub issue fixing
- `_is_github_automation_plan()` added: returns True when plan has both coder+integrator agents
- `_validate_plan()` allows integrator as terminal task when it's a GitHub automation plan (creates PR + posts comment = the final action)

**`backend/llm.py`**:
- Claude 4 models (claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5-20251001) excluded from `temperature` param (they return `invalid_request_error: temperature is deprecated`)
- `not_found_error` / `notfounderror` / `model not found` in exception string → mark unhealthy 1h + try next fallback (was `raise` before, crashing the task)

**`backend/main.py`**: Registered `github_webhook.router` BEFORE `webhooks.router` (specific route before generic `/{token}` catch-all to avoid route collision)

**`frontend/src/App.tsx`**: Added `/app/webhooks` route
**`frontend/src/components/AppNav.tsx`**: Added "Automate" nav link (Zap icon)

### Demo flow
```
POST /api/webhooks/github   (X-Github-Event: issues)
→ goal created: "Fix GitHub issue #N in owner/repo"
→ orchestrator plans: researcher → coder → integrator
→ researcher: reads repo structure + relevant files via GitHub API
→ coder: writes fix, runs tests
→ integrator: creates PR with fix, posts comment on original issue
```

Local testing: `ngrok http 8000` → paste URL into GitHub repo webhook settings. Or use "Simulate" form at /app/webhooks.

### Verified
- Webhook endpoint creates goal correctly (200 OK, goal_id returned)
- 3-agent DAG planned and executing: researcher DONE → coder RUNNING → integrator PENDING
- Frontend builds clean (0 TypeScript errors)

---

## Session: 2026-07-19 — Rebrand to Mergit (Issue #5)

Full visual identity pass for the Mergit showcase prototype (agent economy on a simulated Monad chain).

- Replaced all legacy display strings across `frontend/src` and `frontend/index.html` (title, nav wordmark, landing copy, footer, webhooks page, login page) with "Mergit"
- New palette: deep indigo/violet base (`bg: #07060f`), electric indigo/violet accents (`accent: #6d4aff`, `purple: #a855f7`), electric cyan (`cyan: #22d3ee`), new `proof-green` (`#2eff9e`) token for on-chain proof/reputation accents — `frontend/tailwind.config.js`, `frontend/src/index.css`
- Added JetBrains Mono (`@fontsource/jetbrains-mono`) for hashes/scores/blocks per the on-chain identity brief
- Redesigned the logo mark from a generic 4-square grid to a literal "merge" glyph — two nodes converging into one proof node — in `AppNav.tsx`, `Navbar.tsx`, `LandingFooter.tsx`
- Rewrote hero narrative to pitch the agent economy; added a "Watch proofs mint live" teaser linking to `/app/economy` (ships in #2)
- Rebranded `README.md`, `CLAUDE.md`, this file's title, and `pitch/DEMO_VIDEO_SCRIPT.md`

**Deliberately left unchanged** (real infra identifiers, not brand text):
- `frontend/src/lib/firebase.ts` — the Firebase project id/authDomain (a project id is immutable, so renaming breaks the actual auth backend)
- Legacy service and disk names in `render.yaml`, `compose.yaml`, and the data path (out of scope for a frontend/docs rebrand; renaming would touch live deploy config)

### Verified
- `npx tsc -b`: same 2 pre-existing unrelated errors as `main` (confirmed via `git stash` diff), no new errors
- `npx vite build`: succeeds
- `grep -ri` for the legacy name over `frontend/src` and `frontend/index.html`: clean except the Firebase config noted above
- Manual browser check: `/app` and `/` (landing) render the new palette/wordmark correctly

---

## Session: 2026-08-12 — Real on-chain proof layer + self-heal overhaul + tracing removal

Replaced the simulated Monad economy with a **real EVM proof pipeline**, made self-heal a
showcaseable feature, and removed the third-party tracing dependency.

Spec: `docs/superpowers/specs/2026-08-12-onchain-proof-layer.md`
Plan: `docs/superpowers/plans/2026-08-12-onchain-proof-layer.md`

### Decisions
- **Chain: Monad testnet (10143).** Sepolia was considered but its faucets gate on the same
  ~0.001 mainnet-ETH check as Monad's, so it bought nothing while costing the Monad narrative.
- **Contracts live in `mergit-proto`** for now; they lift into `mergit-contracts` (MIT, Foundry)
  for the production build.
- **Local in-process EVM is the default runtime** so nothing — development, tests, CI, demos —
  ever blocks on faucet funding.

### M1 — Contracts (`backend/contracts/src/`)
Solidity 0.8.24, self-contained (no OpenZeppelin, so `solcx` alone compiles them).
- `Roles.sol` — minimal AccessControl stand-in
- `AgentPassport.sol` — soulbound, one per address; transfer/approve paths all revert
- `ProofOfWork.sol` — **idempotent by revert**: a task is provable exactly once, enforced in bytecode
- `ReputationRegistry.sol` — 0..10000 scores; the PRD's 20% max-delta rule enforced **on chain**,
  so a compromised oracle still cannot move a score arbitrarily
- `AuditTrail.sol` — events only, zero SSTORE
- `chain/compiler.py` — solcx compilation cached by source hash → `contracts/out/` (gitignored)
- `test_contracts.py` — 17 tests on a real EVM. Largest contract 4842 bytes (EIP-170 limit 24576).

### M2 — Chain layer (`backend/chain/`)
- `networks.py` — LOCAL (31337) / MONAD_TESTNET (10143) with explorer URL templates + faucet list
- `provider.py` — `LocalEvmProvider` (py-evm, in-process) and `RpcProvider` (JSON-RPC, local
  signing, nonce management, EIP-1559 with legacy fallback, exponential-backoff retry). Both
  simulate via `.call()` first so a revert surfaces as a clean error instead of a burnt tx.
- `client.py` — `ChainClient`; every method degrades to `None` rather than raising
- `deployer.py` / `registry.py` — dependency-ordered deploy + role grants; `deployments/{chainId}.json`
- `role_address()` duplicates `economy.owner_address` to keep `chain/` free of app imports;
  `test_chain_client.py` asserts the two never diverge

### M3 — Proof outbox (PRD §5.4)
`proof_outbox` table + `chain_worker.py`. `economy.record_proof` mints the local proof instantly and
enqueues; the loop drains `pending→submitting→confirmed` with backoff and dead-lettering at 10
attempts. Restart-safe. A dead chain queues proofs; it never blocks or fails a goal run.

**Bug caught by test:** re-submitting an already-recorded proof returned `tx_hash: None` (the chain
stores the result, not the transaction that delivered it), which would have overwritten settled
history with a null. Now preserves the original.

### M4 — Verification
`GET /api/economy/verify/{task_id}` + `scripts/verify_proof.py`. Recomputes
`sha256(canonical_json(output))` and compares against `ProofOfWork.getProof`, returning every
intermediate so the check is reproducible by hand. **Verified end-to-end that tampering with a
stored output in SQLite is detected.**

The CLI exposed a real limitation: with `CHAIN_TARGET=local` the EVM is in-process, so a separate
CLI process sees an empty chain. It now verifies through the running server's API on local, and
reads the chain directly on a real network.

### M5 — Deploy tooling
`scripts/deploy_contracts.py --network local|monad-testnet [--dry-run]`. Reports missing RPC/key and
lists faucets instead of failing opaquely. Local auto-deploys on boot (`main.py::_init_chain`);
a real network never auto-deploys.

### M6 — Frontend
`ProofLedger` links tx hashes to the active chain's explorer, shows queue depth, and gives each proof
a **Verify** button rendering verified / tampered / not-yet-recorded inline. New `/app/heal` page.

### M7 — Self-heal overhaul
Audit found the mechanism worked but was unobservable and unsafe to leave running: no tests, no
dedup (N failures → N identical issues), no recursion guard, no persistence, **no API or UI at all**,
and a silent no-op without `GITHUB_TOKEN`. Fixed all of it:
- `heal_attempts` table; fingerprint dedup (line numbers/ids/hex/timestamps normalised away)
- recursion guard via `goals.source`/`heal_depth`, `MAX_HEAL_DEPTH=1`
- offline `simulated` mode records the issue body it would have filed — demoable with zero creds
- outcome tracking (`fixed`/`failed`) when the fix goal settles
- `/api/heal/{attempts,stats,stream}`
- background tasks now log exceptions instead of swallowing them
- 24 classifier tests + 13 self-heal tests

Verified live: the same bug fired 3× produced **one** attempt with `seen=3x`, and the "Invalid API
Key" planning failures correctly did *not* trigger heal (classified external).

### M9 — Tracing removal (user request)
The tracing SDK was never load-bearing — `tracing.py` no-opped whenever the SDK was absent, which was every
environment; every boot logged that tracing was disabled. Deleted `tracing.py` and all call sites across
14 modules, config, env vars and four deploy files. Pitch materials repointed at on-chain proof-of-work.

### Also fixed along the way
- `backend/.env.example` did not exist, so the README's `cp .env.example .env` was broken. Written
  in full, covering every setting in `config.py`.
- `conftest.py` gives each test a fresh event loop, so the legacy `get_event_loop()` style and
  `asyncio.run()` coexist regardless of test order (Python 3.13 raises otherwise).

### Verified
- **131 backend tests pass** (was 38), all with no RPC URL, no private key and no network
- `npx tsc --noEmit` clean; `npm run build` succeeds
- Live run: boot → contracts deploy → `replay_demo.py` → 3 proofs confirmed on chain with real tx
  hashes → API and CLI verification both pass → tampering detected

### Follow-up (same day): "are the features actually working end to end?"

A fair challenge, and the honest answer was **partly**. The chain work had been verified with
`replay_demo.py`, which mints proofs from canned data and never runs an agent or calls a model —
so the *execution path* was untested. There are also no API keys in this environment
(`backend/.env` does not exist), so a live model run is impossible here.

Closed the gap by driving the real production path with only `llm.acompletion` stubbed:

- **`test_e2e_workflow.py`** (7) — goal → real orchestrator → persisted DAG → agents →
  interpolation → proofs → chain → verify. Proves `{{t1.output.summary}}` genuinely reaches the
  next agent, that a researcher cannot open PRs and a writer cannot execute code, and that a
  second goal reuses the same passports (on-chain `tasksCompleted` reaches 2).
- **`test_github_automation.py`** (11) — the flagship demo, previously untested. Webhook receipt
  including bot-PR skipping and HMAC verification, then the full researcher→coder→integrator fix
  pipeline with a real `github_pr` invocation and exactly one PR write.
- **`test_replanner.py`** (11) — the "route around failure" claim, previously untested. Includes
  three failure modes that must not silently consume the single replan a goal is entitled to.

**Two bugs this surfaced, both only on a second run:**
1. `replay_demo.py` used fixed task ids → `UNIQUE constraint failed: tasks.id` on the second
   invocation. Now generates ids per run.
2. Restarting the backend wipes the in-process EVM while `proof_outbox` still says `confirmed`,
   so every previously proven task silently stopped verifying. `chain_worker` now requeues
   confirmed proofs on boot when the chain is ephemeral; verification recovers by itself.
   Verified: a task returning `verified=null` after restart now returns `verified=true`.

**163 tests passing.** Remaining unverified: whether a real LLM produces a *good* plan and *good*
agent outputs. The wiring is proven; the model's judgement is not.

---

## 2026-08-13 — Ship it: the container deploy, and three things that only break in one

Goal for the day was mundane — get the image building and running so the current state can be
shown to someone. The container turned out to be a better test than the test suite: it runs as an
unprivileged user against a read-only source tree, which is a configuration nothing local ever
exercises. Three real bugs fell out of that, all of the same family — *the app reported success
while a feature was silently off.*

**1. The chain switched itself off inside the container, behind a green health check.**
First run of the image: `Chain layer unavailable: [Errno 13] Permission denied:
'/app/backend/deployments/31337.json'`. All four contracts had deployed fine; only the write of
the *record about them* failed, because the Dockerfile chowned `contracts/` and `/opt/solcx` but
not `deployments/`. `_init_chain` degrades rather than crashes — by design — so `/api/health`
answered `{"status":"ok"}` with `"chain":"disabled"` buried in it. Two fixes, because either one
alone leaves a hole: the Dockerfile now creates and chowns `deployments/`, and `deploy_all`
treats a failed record write as a warning. The contracts are deployed either way; the JSON is a
note about them, not the thing itself.

**2. `ChainClient` reported READY for contracts that did not exist.** Readiness was decided by
"addresses present in the deployment file + ABI binds cleanly" — but binding a contract is pure
local ABI work that succeeds against any address, deployed or not. `deployments/10143.json` held
four invented addresses left over from the simulated era, so flipping `CHAIN_TARGET=monad-testnet`
would have produced a UI announcing *"Live on Monad Testnet"* while every call returned nothing.
Readiness now requires bytecode at every address (`eth_getCode`). The check immediately earned its
keep: it fired during a test run against a stale local `31337.json`, exactly the scenario it was
written for.

**3. `GET /api/economy/chain` hardcoded `deployments/10143.json`.** It reported Monad Testnet and
those same invented addresses regardless of the chain actually running underneath, and its test
asserted `chainId == 10143` — passing happily while the app ran on 31337. Endpoint now reports the
live client; the test asserts it *matches the running chain* rather than a constant. Deleted the
fabricated deployment record.

Also: `solcx` reads `SOLCX_BINARY_PATH` but never creates it, so a baked-in container path died
with `FileNotFoundError` (fixed defensively); `deploy/backup-sqlite.sh` autodetects the container
engine instead of hardcoding `docker`; `.env.production.example` gained the four `CHAIN_*` vars;
README no longer calls the economy "simulated".

**Verified in the production container, not just locally:** `/api/health` →
`{"chain":"ready","chain_id":31337}`, `replay_demo.py` minted 3 proofs, the outbox drained all 3 to
`confirmed`, and `demo_tamper.py` ran the whole arc — verify ✓ → rewrite the output directly in
SQLite → ✗ MISMATCH → restore ✓.

**170 tests passing.** Still blocked: no MON, so nothing has ever been deployed to a public
network. Every faucet gates on an Ethereum mainnet balance. The cheap way out, if a real chain
matters more than *Monad specifically*, is an `anvil` node next to the app — real RPC, real tx
hashes, survives restarts, no faucet.

---

## 2026-08-13 — Capacity measurement and the issue register

No code changed this session. Two questions got answered with evidence instead of estimates.

**Can it carry 10 concurrent users on a free tier?** Yes, with room. `backend/scripts/loadtest.py`
(new) holds N SSE streams open while polling all six dashboard endpoints at the frontend's real 5s
SWR interval. Against a container throttled to `--cpus 0.1 --memory 512m`: **348 requests, 0
errors**, p50 300ms, p95 1.3s, 250 MB of 512 MB. Unthrottled the same run gives p95 265ms. CPU is
not the ceiling.

Four things that *are*: the worker loops live in the FastAPI lifespan and the EVM is in-process, so
**one instance is mandatory** — no autoscaling, no `--workers 2`. **Cold start is 70 seconds** (the
chain deploys during it), which rules out sleep-on-idle tiers unless a cron keeps them warm. Free
tiers without a persistent disk wipe SQLite *and* the chain on every redeploy. And the real limit on
goal throughput is Groq's free-tier RPM/TPM, not the host — `MAX_CONCURRENT_TASKS=3` on a free box.

One host blocker worth recording: **Oracle's ARM Always Free tier cannot build this image.**
`solcx/install.py::_get_os_name()` maps every Linux to one target and downloads `linux-amd64` with
no CPU-arch check, so ARM64 fetches an x86 ELF that cannot exec — and `contracts/out/` is gitignored,
so a clean clone has no cached artifact to fall back on. x86 shape, or commit the artifacts.

**What is actually left to do?** Written up as `ROADMAP.md` — seven milestones, every item rated P0–P3
with the reasoning attached. Three findings from checking the register against the live DB rather
than trusting the notes:

- Two of the eight open issues in the working list were **already fixed and verified** last session
  (`deployments/10143.json` deleted; the `eth_getCode` readiness check landed).
- The PLANNING-stranded-goal bug has a **live victim**: goal `f3e6b093` has sat in PLANNING with zero
  task rows since before the reboot, invisible to the reclaim loop because
  `find_orphaned_goals` requires `terminal_task_id IS NOT NULL`.
- A **second stranding** nobody had listed: goal `b3e2ba89` is RUNNING with its integrator task in
  `WAITING_CREDENTIAL`, correctly suspended on the missing `GITHUB_TOKEN` — the design working
  exactly as intended, and completely invisible in the UI. The resume path exists; only the banner
  telling a human which variable to supply is missing.

The register's blunt conclusion: almost nothing outstanding is *broken*. It's blocked on a
credential or an account. The GitHub automation pipeline — the flow `CLAUDE.md` calls the main demo
— has never once run, because there is no token. That single credential is the highest-value item
in the document.

---

## 2026-08-13 — Purging the legacy brand and tracing SDK

User asked for every trace of the pre-rebrand name and the removed tracing SDK to be gone. A
`grep` found five categories, only one of which was a simple string replace.

**The one that mattered: `frontend/src/lib/firebase.ts` hardcoded a Firebase project id.** A
project id is immutable, so it could never be renamed — only replaced. Config now reads from
`VITE_FIREBASE_*` env vars with no hardcoded fallback, plus an `isAuthConfigured` flag; added
`frontend/.env.example` documenting all seven vars. Swapping Firebase projects is now a config
change instead of a code change, and the source tree names no project at all. None of these are
secrets — Firebase web config ships inside every client bundle by design — so they live in `.env`
for portability, not confidentiality.

**The trap: `frontend/dist/` still had the old project id compiled in.** The source was clean and
every `grep` over tracked files passed, but `dist/` is gitignored *and* is what FastAPI serves at
`/` in production. The stale bundle carried 3 matches of the old id plus the API key. Rebuilt;
the shipped bundle now scans clean. **Scrubbing source is not scrubbing the product** — check
build output separately, because ignored files never show up in `git grep`.

**Historical docs were reworded, not deleted.** `progress.md` and the three `docs/superpowers`
plans/specs documented the rebrand and the tracing removal — erasing those entries would make the
changelog lie about what happened. Every mention became a description instead of a name ("the
tracing SDK", "legacy brand string"), so the history stays honest and the names are gone.

**Artifacts removed:** the stale submission PDF (superseded — `pitch/generate_pdf.py` already
emits a Mergit-branded file), and a stray SQLite db plus its `-wal`/`-shm` sidecars. `.gitignore`
had anchored its db rules to `backend/mergit.db`, which matched exactly one path — any tool run
from another cwd left a stray git offered to commit, which is how the frontend db got tracked in
the first place. Rules are now unanchored (`*.db`, `-wal`, `-shm`, `-journal`).

**Gotcha for anyone repeating this:** `omium` is a substring of `chromium`, so a naive
case-insensitive grep hits `electron-to-chromium` in `package-lock.json` forever. Use word
boundaries.

170 tests pass, frontend typecheck clean, shipped bundle clean. **Not done:** git history still
contains the old name in commit messages and file contents — that needs `git filter-repo` and a
force push, which rewrites every SHA and breaks existing clones.

**Direction change (user, this session):** this is no longer a hackathon submission — it is being
built as a real product. The pitch/submission track is dropped. `ROADMAP.md` is currently framed
around "show the manager a working demo" and needs rewriting against the actual product vision
before it drives work again.

---

## 2026-08-13 — Legacy brand purge, and the gate a public URL needed

**Chose Hugging Face Spaces over Oracle Always Free.** Oracle's signup could not be completed,
and on inspection the free x86 shape (1 core / 1 GB) was the weaker box anyway — `npm run build`
would have needed a swap file to avoid OOM. HF gives 2 vCPU / 16 GB, builds on x86 so the solcx
arch bug is moot, and needs no card. It costs an ephemeral disk and a *listed* public URL, and the
second of those turned out to matter far more than the first.

**Checking whether HF was safe found a P0 that had been filed as P3.** `PUT /api/config/keys` has
no authentication — no dependency, no token. Neither does `POST /api/goals`, and `VITE_DEMO_MODE=true`
removes the login. So on any reachable URL a stranger can overwrite the provider keys, read them
masked, burn the LLM quota, and reach the coder agent's `code_exec` — arbitrary Python in a
subprocess. That is remote code execution by design rather than by bug. It was rated P3 under
"real authentication"; on a discoverable host it is P0, and the roadmap now says so.

Fix is `access_gate.py`: HTTP Basic on every route except `/api/health`, active only when
`ACCESS_PASSWORD` is set, so local dev and the suite stay credential-free. Basic rather than a
bearer token on purpose — the browser prompts natively, which covers the SPA, the REST API and SSE
in one move, and `EventSource` cannot send custom headers but the browser attaches Basic
credentials for it. `secrets.compare_digest`, not `==`. Added last in `main.py` so it is the
outermost middleware and rejects before anything else touches the request.

**`demo_seed.py` — seeding, not shipping, the demo data.** The ephemeral disk wipes SQLite and the
chain on every restart. Committing a populated database looked like the obvious answer and is the
wrong one: its proofs reference a chain that died with the process that minted them, so every
Verify button would answer `verified: null` — worse than an empty ledger, because it looks broken
rather than new. Seeding mints against the chain running *now*. Confirmed end to end: booted with
`SEED_DEMO=true`, `/api/economy/verify/{id}` returned `verified: true` with computed and on-chain
hashes matching. `scripts/replay_demo.py` is now a thin wrapper over the same module so the two
cannot drift.

Verified live rather than only in tests: health open (200) so the container healthcheck still
passes, `/api/config/keys` and `POST /api/goals` both 401 without credentials, 200 with, 401 on a
wrong password, and 3 proofs seeded and verifying.

**Legacy brand purge.** `frontend/src/lib/firebase.ts` hardcoded a Firebase project id — and a
project id is immutable, so it could never be renamed, only replaced. Config now comes from
`VITE_FIREBASE_*` env vars with no fallback, so the source tree names no project at all and
swapping projects is a config change. Added `frontend/.env.example`. Scrubbed the legacy brand and
the old tracing SDK's name from `progress.md` and the superpowers plans/specs by rewording rather
than deleting, so the changelog still records that a rebrand and a tracing removal happened.
Regenerated the pitch PDF from `pitch/generate_pdf.py` (which already emitted the current name) and
verified 0 byte-matches for the old brand in the output. One gotcha for anyone repeating this:
`omium` is a substring of `chromium`, so a naive grep hits `package-lock.json`.

Also: `.gitignore`'s SQLite rules were anchored to `backend/mergit.db`, so a tool run from any
other cwd left a stray `mergit.db` that git offered to commit — `sqlite3.connect()` creates the
file when it is missing. Now unanchored (`*.db`, `-wal`, `-shm`, `-journal`). A stray db under
`frontend/` had already been committed exactly that way; scanned clean (empty schema, no
credentials) so it needs untracking, not a history rewrite. Dockerfile now creates the app user at
UID/GID 1000 because HF Spaces runs containers as user 1000, and a system user below 1000 owning
`/data` means the app cannot write its own database.

**186 tests passing**, up from 170. Runbook at `deploy/HUGGINGFACE.md`.

**Host decision, after two dead ends.** Oracle Always Free was the technical pick — persistent
disk, always on, and arm64 builds fine now that `contracts/out/artifacts.json` is tracked
(`compile_all()` returns the cache before it ever asks solcx for solc, so the x86-only solc
download never happens). Card verification could not be completed, so it is deferred rather than
rejected; `docs/DEPLOYMENT.md` stands. Hugging Face Spaces was the no-card fallback until the
Space creation page showed Docker Spaces now require PRO — only Static Spaces are free, and a
static host cannot run this backend. That runbook is kept, marked out of date, for anyone with PRO.

Landed on **Render free**, which `render.yaml` had been wired for all along — including a comment
anticipating that the free plan has no disk and would need to "re-seed on boot", which is exactly
what `demo_seed.py` now does. Added `ACCESS_PASSWORD` (sync:false), `SEED_DEMO=true` and
`MAX_CONCURRENT_TASKS=3` to it, and wrote `docs/RENDER.md`. The free plan's real cost is the 15-minute
idle sleep and the ~70s cold start behind it; a free 10-minute cron against `/api/health` — which sits
outside the access gate precisely so unauthenticated pings work — keeps it warm inside the 750h/month
allowance. Oracle and AWS come back into scope when there is a reason to scale, not before.

## 2026-08-13 — API contract tests, and what testing the live deployment turned up

Every router except `api/economy.py` had no test file. Wrote contract tests for the rest and, while
exercising the deployed instance at `mergit.onrender.com`, found nine defects — all fixed here, each
with a test that fails on the old code first.

**The two that mattered.** `llm.py` walked `_FALLBACKS` without checking whether the fallback
provider had a key. `groq/llama-3.3-70b-versatile` falls back to Claude Haiku, `ANTHROPIC_API_KEY`
is unset on that deployment, and the resulting `AuthenticationError` is neither a rate limit nor a
missing model — so it escaped the retry logic and propagated, discarding the Groq error that caused
the fallback in the first place. Every goal submitted while Groq was throttling failed with
"Missing Anthropic API Key" on a deliberately Groq-only instance. Reproduced three times; the fix
skips providers with no credentials and raises the *first* error rather than the last, because the
first one is the one that explains the run.

Underneath that: `model_health` was never wired to anything. Nothing called `mark_unhealthy`, so
`GET /api/config/model-health` answered `all_healthy: true` throughout — while nothing worked. Its
docstring promised that "subsequent acompletion() calls skip unhealthy models"; `llm.py` did not
import the module. Now a hard rate limit registers a cooldown, cooling models are skipped, and if
every candidate is cooling down the least cold is tried anyway — a cooldown must slow the worker,
never stop it.

**The rest.** `GET /api/goals/{id}/stream` on an already-finished goal never closed: 75 seconds and
nine keepalives with no terminating event, one leaked connection per visit to a past goal. It only
broke on a live `goal_done` it happened to witness. It now subscribes *first*, then re-reads the
goal — which also closes the race where a goal finishing between the 404 lookup and the subscription
emitted its event to nobody — and re-checks stored state on each keepalive so a lost event is
bounded by `PING_TIMEOUT` instead of forever. `SPAStaticFiles` is mounted at `/` and swallowed 404s
for every path including `/api/…`, so `/api/nope` returned 200 and 479 bytes of SPA index; callers
expecting JSON got a decode error instead of a status code. `limit` reached `LIMIT ?` unvalidated
and SQLite reads a negative limit as unbounded, so `?limit=-1` dumped whole tables from
unauthenticated endpoints. `POST /api/goals` accepted a 20,000-character body and stored it whole.
`PUT /api/config/models` accepted any string as a model id, which saves cleanly and then fails every
goal with a provider error naming a model nobody chose. Both new limits are settings
(`max_goal_chars`, `max_page_size`), not constants.

**And the one that hid the others.** `scripts/test-local.sh` — the script the README points at —
ran `py_compile` and a frontend build, printed "Local checks passed", and never invoked pytest.
`pytest` was not in `requirements.txt` either, so a clean checkout could not run the suite at all.

**270 tests passing**, up from 186. `test_live_deployment.py` runs the same contract against a
running instance (`MERGIT_BASE_URL=…`), skipping entirely when unset; `MERGIT_LIVE_GOAL=1`
additionally drives one real goal to completion and verifies its proofs. Nothing in it issues a PUT
— on an ungated deployment a test suite must not be the thing that overwrites live provider keys.
Against production it reports 18 passed / 9 failed, and the nine are exactly the fixes above.

Confirmed working on the live instance, unchanged: a real goal ran researcher → writer in 49s,
`{{t1.output}}` interpolated, both tasks minted proofs that verify against the chain
(`computed_hash == onchain_hash`, real tx hashes, blocks 12 and 14), and reputation moved.

---

## 2026-08-13 — The GitHub write surface: audit, merge guard, and the blind reviewer

Audited what the agent can actually do on GitHub when a user asks it to open a PR, fix an issue,
or merge a PR. Two of those three worked. The third did not exist.

**`merge PR` was not implemented at all.** `grep -rn "merge" backend/**/*.py` returned nothing
outside a dict merge in `context.py`. No merge tool, nothing in `TOOL_REGISTRY`, nothing in the
integrator's `allowed_tools`, no mention in the orchestrator prompt. A goal saying "merge PR #5"
planned a DAG, ran an integrator with no way to merge anything, and terminated on whatever the
model chose to claim.

**"Review a GitHub PR" was documented, routed, and blind.** The orchestrator prompt promised
`researcher (reads changed files) → writer`, but no tool in the registry returned a PR's diff or
even its changed-file list. `github_get_issue` resolves a PR number — GitHub treats PRs as issues —
and returns title, body and comments, so the pipeline *succeeded* while the reviewer never saw a
line of the code. It shipped a review written from the PR title. The failure mode was silent,
which is why 11 passing tests never caught it: they stub every GitHub tool, so they prove the
wiring and assume the semantics.

**The token had two sources that disagreed.** `github_pr` read `os.environ` *or*
`settings.github_token`; every tool in `github_ops` read only `os.environ`. `Settings` loads
`backend/.env` through pydantic-settings, which populates the settings object and never touches
`os.environ`. So the documented setup — token in `backend/.env` — left `github_pr` working while
the other nine tools reported a missing credential and parked their task in `WAITING_CREDENTIAL`.
Render injects real environment variables, which is why production never showed it. Now one
`github_token()` in `tools/github_client.py`, env first so a runtime `PUT /api/config/keys` still
wins without a restart.

**Ten new tools**, all on the integrator except the read paths: `github_merge_pr`,
`github_get_pr`, `github_get_pr_files`, `github_list_prs`, `github_review_pr`,
`github_request_review`, `github_update_pr`, `github_create_issue`, `github_close_issue`,
`github_add_labels`. Twenty GitHub tools registered, up from ten.

**The merge guard.** Merging is the one GitHub action an agent cannot walk back, so
`github_merge_pr` gates rather than attempts: it merges only when `mergeable_state` is `clean` or
`has_hooks` and no reviewer's latest review is `CHANGES_REQUESTED`, and otherwise returns
`refused=True` naming the blocker — including which check failed. The review check is not
redundant with `mergeable_state`: on a repo without branch protection, a `CHANGES_REQUESTED`
review leaves the state `clean`, so trusting the state alone merges a rejected PR. `unknown` is
polled rather than refused, because GitHub computes mergeability asynchronously and a PR read
moments after creation always reports `unknown`. An already-merged PR returns `ok=True,
already_merged=True` — the `tool_calls` idempotency cache replays a merge after a restart, and a
replay must not read as a failure. The integrator's prompt states that a refusal is a correct
final outcome, not something to retry or route around.

**`github_pr` hardening.** An empty `files[]` was rejected by GitHub as "No commits between" only
*after* the branch had been created, leaving a stray branch behind on every attempt — now refused
up front. A re-run against an already-open PR raised 422; it now returns the existing PR, which
matters because the task cache replays tool calls. The fork path branched from the fork's own
default branch, so a fork taken weeks earlier produced a PR whose diff reverted every upstream
commit landed since — it now branches from the upstream base sha (forks share an object store),
falling back with a warning. Base-branch detection walked every branch in the repository on every
call; now one lookup. The 60-second fork poll used `time.sleep` inside an `async def`, blocking the
event loop for all five concurrent worker tasks — now `asyncio.sleep`.

`test_github_tools.py` adds 29 tests over the merge-guard refusal matrix, diff truncation, the
self-review downgrade (GitHub rejects approving your own PR, and the agent usually authored it),
PR-creation robustness, and a check that every tool named in `allowed_tools` is actually
registered. **215 tests passing**, up from 186. `scripts/github_e2e.py <owner/repo>` drives the
whole surface against a real repository — real issue, real PR, real diff, real review, real merge,
and a real conflicting PR to prove the guard refuses — because faked PyGithub proves the tools'
decisions but not that GitHub accepts the calls they make.

**Unrelated and urgent, found while probing the deployment:** `https://mergit.onrender.com` serves
`/api/goals`, `/api/config/models` and `/api/config/keys` with HTTP 200 and no authentication.
`ACCESS_PASSWORD` is unset in the Render environment. Per `access_gate.py`'s own docstring that
makes `POST /api/goals` plus the coder's `code_exec` remote code execution, and lets anyone
rewrite the provider keys. Set it in the Render dashboard.

**Follow-up, same branch — the gate that was never set.** `ACCESS_PASSWORD` was `sync: false`,
which means "an operator sets this by hand in the dashboard". Two environments existed where
nobody had: production, and — once Viscous106 enabled pull request previews — every preview.
Render's blueprint spec is explicit about the second: "Render does not include `sync: false`
environment variables in preview environments", so a preview could not have inherited a password
even if production had one, and `mergit-pr-<n>.onrender.com` is guessable from the PR number.
Confirmed on the live preview for PR #13: `/api/goals`, `/api/config/models` and
`/api/config/keys` all returned 200 unauthenticated. Now `generateValue: true`, which mints a
random 256-bit value when the variable does not already exist — an operator who wants a chosen
password still sets one and it is left alone, but no environment can boot without a gate. The
generated value is read from the Render dashboard.

**Second follow-up — the merge route was unreachable.** Running the real goal ("Merge pull request
#3 in OfficialAbhinavSingh/mergit-e2e-sandbox") against a live Groq model and live GitHub failed
before a single GitHub call: `Orchestrator failed after 5 attempts. Last error: terminal task 't2'
uses agent 'integrator' which produces raw data.` `_validate_plan` permitted a terminal integrator
only when the plan also contained a `coder` — the issue-fix shape. A merge needs no coder, so the
prompt was routing "merge PR #N → integrator alone" into a plan the validator rejected every time.
`_integrator_terminal_is_an_action()` now also accepts a direct action on a named PR or issue,
detected structurally by a `pr_number`/`issue_number` input with a write-verb fallback on the task
description. The stubbed suite could not have caught this: it scripts the plan instead of asking a
model for one, so the validator never saw a real merge plan — the same shape of blind spot as the
reviewer that never read a diff. Re-run after the fix: plan `integrator → integrator`, t1 read PR #3
(`mergeable: false`), t2 returned `merged: false, reason: "the branch has merge conflicts with the
base"`, and GitHub confirms PR #3 is still open and unmerged. The agent attempted a real merge, was
refused, and reported the refusal instead of claiming success. 220 tests passing.

---

## 2026-08-14 — CLAUDE.md audited against the tree: how to run tests, and four stale claims

`CLAUDE.md` had no test commands at all. Anyone following it could develop the backend without
ever learning that 364 tests exist, how to run one, or that `pytest-asyncio` is absent — so a new
`async def test_x` written the obvious way is collected, skipped and reported as passing. The
Commands section now carries the whole-suite, single-file, single-test and `-k` invocations, the
frontend `lint`/`build` (the latter being the only type check there is), `scripts/test-local.sh`,
the `MERGIT_BASE_URL` gate on `test_live_deployment.py`, and a note that `backend/jsonstats.py` is
agent output rather than app code.

Four claims in the architecture summary had drifted from the code:

- **"40 predefined models across Groq, Anthropic, OpenAI, Google, Mistral"** — `AVAILABLE_MODELS`
  holds 15 ids across Groq, Anthropic and OpenRouter. Worse, the doc said "any LiteLLM-compatible
  string also accepted"; `model_config.update()` rejects anything not in the list, and has since
  the unauthenticated `PUT /api/config/models` made a bad id a way to break every goal at once.
- **"sets env vars for all 5 providers"** — `llm.py` sets three (Anthropic, Groq, OpenRouter), and
  the `GOOGLE_API_KEY → GEMINI_API_KEY` bridge the doc described no longer exists. The OpenRouter
  last-resort tier appended to every fallback chain was undocumented entirely.
- **"reads/writes provider API keys (Groq, Anthropic, OpenAI, Google, Mistral, Tavily)"** —
  `PROVIDER_KEYS` is groq / anthropic / openrouter / tavily / github, and saving one resumes tasks
  parked in `WAITING_CREDENTIAL`, which was the part worth documenting and the part missing.
- **"a visually-simulated Monad chain"** — left over from before the real EVM landed. "Simulated"
  here means the chain runs in-process, not that the transactions are fake.

Newly documented because nothing in the summary mentioned them: `replanner.py` (a goal gets one
alternative plan when a task exhausts its attempts), `model_health.py` (cooldowns, and the
least-cold pick that keeps a fully-throttled chain moving), `context.py` (operator context injected
into both orchestrator and agent prompts), the `RUNTIME_CONFIG_DIR` indirection all three
config files resolve through and read at import time, the `WAITING_CREDENTIAL` sentinel protocol,
and the API routes in `api/tasks.py`, `api/actions.py`, `api/context.py` and `api/auth.py`.

Not fixed, only flagged: `backend/.env.example` still lists `OPENAI_API_KEY`, `GOOGLE_API_KEY` and
`MISTRAL_API_KEY`, which no model uses, and omits `OPENROUTER_API_KEY`, which every fallback chain
now ends in — so a deployment set up from the example has no cross-provider escape when a daily
quota runs out.
---

## 2026-08-15 — The auth plan, and the three bugs that stood in its way

**Planned:** per-user identity and delegated authorization — Google sign-in, per-user GitHub and
Slack connections, and the "build me a Slack bot" flow end to end. Researched by a 26-agent
workflow (nine domains, each adversarially fact-checked; three candidate architectures scored by
security / time-to-ship / product judges; synthesised and put through a completeness critic). The
blueprint lives in the approved plan file; the decisions that matter are recorded below.

**This flips `final.md` D3 from C to B.** The decision register decided *solo dev, self-hosted,
single-tenant is correct, not a gap* one day earlier and rated multi-tenancy + auth XL, gated on
"only if D3 = B". That gate is now open by explicit choice. `final.md` D3/D4 and `ROADMAP.md` M4
must be updated to say so, or the next reader finds a register that contradicts the code.

**The premise that had to be corrected first.** The request assumed Google auth could authorize
GitHub and Slack. It cannot, by any mechanism: `include_granted_scopes` unions scopes across
*Google's own* services, Google's STS exchanges credentials *inbound* to Google Cloud only, and
RFC 8693 is unusable where you are not the authorization server. Google is the identity anchor;
each provider needs its own OAuth client, consent and stored token. One identity, N grants.

**Shipped this session — Phase 1's correctness half.** Three bugs on the park/resume path, all
live on `main`, all invisible while parking was rare. Per-user OAuth makes every "connect your
GitHub" prompt a park, which turns each of them into a product defect:

- **The idempotency cache missed on every resume.** `_idempotency_key` included `attempt`, and
  `claim_ready_task` increments `attempt_count` on *every* claim — including the claim after a
  resume. Identical work hashed to a different key, so a resumed task re-fired every write it had
  already completed. Reproduced: a goal that paused once posted its issue comment **twice**.
- **The naive fix was worse, and nearly shipped.** Dropping `attempt` alone livelocks the product.
  `_execute_tool_idempotent` settles `SUCCESS` unconditionally, and the `WAITING_*` sentinels are
  ordinary dict returns, not exceptions — so a park was stored as a completed call. With a stable
  key it replays on the next claim, parks again, and does so forever regardless of what the user
  connects. A park is now deleted from `tool_calls` (`db.delete_tool_call`) before it can settle.
  Verified both ways against a scratch copy of `HEAD`.
- **Parking spent the retry budget.** `worker.py` checked `attempt_count` against `max_attempts`,
  so a task that paused three times had nothing left for its first genuine failure. New
  `tasks.failure_count` column (migrated + backfilled in `init_db`) is the budget and moves only
  on a real exception; `attempt_count` stays the claim counter that makes lease reclaim crash-safe.
- **The orphan sweeper killed goals that were waiting on a human.** `find_orphaned_goals` counted
  `WAITING_CREDENTIAL`/`WAITING_WEBHOOK` as stalled, and its caller marks such goals `FAILED` with
  "All tasks failed — no progress possible". A goal died while its connect prompt was on screen.
  Both statuses now count as progress.

**Verified:** `test_park_and_resume.py` — four tests, all four **fail on `HEAD`** and pass after,
with the double-post reproducing as `['on it', 'on it']`. Suite 331 → **335 passed, 35 skipped**.

**Still open in Phase 1** (not started): fail-close the GitHub webhook and move the Simulate form
to an authenticated route in the same commit — `frontend/src/pages/Webhooks.tsx:25` posts it
unsigned at `/api/webhooks/github`, so fail-closing alone breaks the deployed demo; `code_exec`
and `http_request` hardening; log/DB redaction; dependency pinning; and the Render persistent disk
(a billing change, deliberately left for the operator).

---

## 2026-08-15 — Per-user identity and delegated authority, built

The plan from earlier today, implemented. Google sign-in, per-user GitHub and Slack connections, an
encrypted credential vault, a human-in-the-loop gate on irreversible actions, and multi-tenancy
across every read path. **461 tests passing** (was 331), frontend builds clean, verified against a
running server.

**What shipped, by phase.**

*Phase 1 — hardening and three live correctness bugs* (recorded in the earlier session block, plus):
the GitHub webhook now **fails closed** and reads its secret from `Settings` **or** the environment —
it read only `os.environ`, so a secret set the documented way left it failing *open*, the third time
that split has bitten this repo. `POST /api/actions/simulate-issue` was added in the same commit,
because the Automate page's Simulate button posted an unsigned payload at the receiver and
fail-closing alone would have broken the demo. `code_exec` no longer inherits the environment — it
had `GITHUB_TOKEN`, every provider key and `CHAIN_PRIVATE_KEY`, and `print(os.environ)` carried them
to stdout → tool result → `tool_calls` → SSE → back into model context. `http_request` was an SSRF
and exfiltration primitive on both the researcher and integrator; it is now https-only, refuses
private/loopback/link-local after resolution, does not follow redirects, and its `headers` parameter
is gone from the schema entirely.

*Phase 2 — identity and multi-tenancy.* Authlib + Google OIDC replaces the hand-rolled flow, which
had no `state` (login CSRF), no PKCE, no `nonce`, and never validated the `id_token` it was handed.
Opaque server-side sessions, because a live session can tell agents to merge into someone's default
branch and revocation must be immediate. One `/api/`-scoped middleware rather than `Depends()` on
~40 routes — a forgotten dependency is a public endpoint, a forgotten middleware is a broken route.
`db.create_goal` now takes `user_id` as a **required positional**: all seven call sites were missing
it, and a goal without an owner parks on `conn:github:` with an empty user and can never be resumed
or even seen.

*Phase 3 — the vault.* AES-256-GCM envelope encryption with associated data binding every ciphertext
to `(user_id, provider, purpose)`. Not Fernet, and the test proves why: without AAD an attacker with
DB write access moves one user's sealed token into another's row and it decrypts cleanly. The KEK is
read once and popped from `os.environ` before the worker starts.

*Phase 4 — the broker.* `credentials/broker.py` is the only module that can decrypt, enforced by an
AST check in CI. It returns clients, never token strings, so no tool argument can hold a credential
and no tool result can return one. All 20 GitHub tools rewired through it; the repository allowlist —
the list the user ticked at install time — is enforced in code before any HTTP call.

*Phase 5 — approvals.* The gate lives in the tool wrapper, outside the LLM loop, bound to a hash of
the exact arguments. Approving "merge PR #12" does not authorise "merge PR #99".

**Storage, on a $0 budget** (D7 in `final.md`): Litestream → Backblaze B2. Researched by a 15-agent
workflow; the decisive measurement was that the 1 Hz worker polling generates **zero WAL bytes**
(2,000 no-op claim cycles grew the WAL by 0), so the ~2.6M monthly statements cost nothing and the
bill is set by compaction timers alone — ~76k operations/month, and B2 has no operation cap at all.
Also found and fixed: `claim_new_goal` ran `SCAN goals` plus a sort **once per second, forever**, and
goals are never deleted. Migration 006 adds the index; verified the plan becomes `SEARCH … USING INDEX`.

**Verified live**, not just in tests: health 200 while `/api/goals`, `/api/connections`,
`/api/approvals`, `/api/config/keys` and `/api/economy/proofs` all 401; the SPA still served at `/`;
an unsigned webhook rejected; and the authorize redirect carrying `state`, `nonce`,
`code_challenge` + `code_challenge_method=S256`, with scopes at `openid email profile`.

**Not done, and deliberately so.** The Slack *bot factory* (create → install → test → deliver) is
designed in the plan but unbuilt — it depends on `code_exec` running out of process, which is its own
phase. Slack *connect* works; building bots does not yet. No commits made: the working tree is left
for review.

---

## 2026-08-18 — The stash pop that never finished, and the API drift it hid

The tree was stuck mid-`git stash pop`. `git pull origin main --rebase` had fast-forwarded `main`
from `dcbbfae` to `8e8814f`, pulling in five upstream fix commits; popping the auth/credentials WIP
on top of them collided in three files. There was no `MERGE_HEAD` — the pop had been `git add`ed
*while still conflicted* and then re-popped, so stage 2 ("ours") literally contained
`<<<<<<< Updated upstream` markers. The working tree held a hand-resolution that was never staged.

**The three resolutions, all keeping both sides rather than picking one:**

- `worker.py` — upstream fenced `settle_task` with `worker_id=lease_holder`; the stash switched the
  retry budget from `attempt_count` to `failures`. Both are needed and neither subsumes the other:
  the fence stops a reclaimed worker settling, and `failure_count` is what makes parking-not-failing
  true. Kept `failures >= fresh.max_attempts` **and** `worker_id=lease_holder`.
- `tools/github_pr.py` — upstream added `import language` and the `_changes_nothing` guard; the stash
  added `credential_check` to the import list and the `as_user=True` fork path (an installation token
  has no user, so `g.get_user()` cannot run on it). Kept all four.
- `progress.md` — both session blocks, separated by a rule. Nothing dropped.

**What the conflict was hiding.** Resolving the markers left 26 tests failing, and they were real
drift, not resolution damage — the two sides had changed APIs the other side's tests still called:

- 25 failures, one cause: the five test files the rebase brought in
  (`test_blocked_tasks`, `test_fabricated_claims`, `test_forced_final_submit`, `test_lease_fencing`,
  `test_malformed_tool_call`) call `db.create_goal("...")`, and the stashed multi-tenancy work made
  `user_id` a **required positional**. That is the design working exactly as intended — a missed call
  site is a loud `TypeError`, not an ownerless goal. Fixed to `user_id="usr_legacy_demo"`, matching
  every other test.
- 1 failure, and two silent false passes beside it. Three `github_post_comment` tests stubbed
  `_require_token` and a **sync** `_client()`; the stash made the gate `_credential_check(args)` and
  `_client` async. Only the third test noticed, because it asserts `ok is True`. The other two assert
  `ok is False` — and passed for the wrong reason: the unstubbed credential gate refused the call
  before the placeholder guard ever ran, so the guard those tests exist to protect was untested.
  All three now stub the modern seam, and all three assert against real tool logic.

**Verified, not assumed:** 616 passed / 35 skipped. `tsc --noEmit` clean, `npm run build` clean. Boot
smoke-tested on a throwaway DB both ways — with Google unconfigured every `/api/` route serves the
documented single-tenant fallback, and with `OAUTH_GOOGLE_CLIENT_ID`/`_SECRET` set every route except
`/api/health` returns **401**, `/api/auth/login` 302s to Google carrying `state`, `nonce`,
`code_challenge` and `code_challenge_method`, and an unauthenticated `POST /api/goals` is refused.
Migration `001_failure_count` applies clean on an empty DB; chain reaches `status=ready`.

Conflicts staged as resolved. Still uncommitted and left for review, as the previous block intended;
`stash@{0}` is deliberately not dropped until that review lands.
