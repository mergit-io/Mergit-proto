# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Update Protocol

After every piece of work completed in this repo, update **both** files:
- `CLAUDE.md` — keep architecture section current (models, new files, changed behaviour)
- `progress.md` — append a new dated session block describing what was built/fixed

`ROADMAP.md` is the issue register: every open item, rated P0–P3, with what unblocks it. Check an
item off there when you fix it — and verify against the live DB before trusting its status, since
two entries were already stale when it was written.

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

Mergit is a generic multi-agent autonomy system: a user submits any natural language goal, the orchestrator decomposes it into a task DAG, and specialized worker agents execute each task using tools, with full persistence for restart-resumability. Layered on top is a simulated agent economy — every completed task mints a proof and bumps its agent's reputation on a visually-simulated Monad chain.

### Backend (`backend/`)

**Entry point**: `main.py` — FastAPI app with lifespan that initializes DB, starts the worker, registers all routers, and optionally serves the frontend static build.

**Core execution loop** (`worker.py`):
- `goal_planner_loop` — polls NEW goals → calls `orchestrator.run_plan()` → creates task rows
- `task_executor_loop` — polls READY tasks → runs `agent_runner.run()` — up to 5 concurrent (Semaphore)
- `reclaim_loop` — every 30s, reclaims RUNNING tasks with expired leases back to READY

**Orchestrator** (`orchestrator.py`): Uses the model from `model_config.get_model("orchestrator")` (defaults to `groq/llama-3.3-70b-versatile`). Forced tool call → `PlanSchema` (task DAG JSON). Retries 5x with rate-limit backoff. Handles Groq `tool_use_failed` by salvaging the plan from `failed_generation` in the error response (`_salvage_failed_generation()`). Falls back to `tool_choice="auto"` on attempts 2+. Task IDs are prefixed with `goal.id[:8]_` to avoid UNIQUE constraint collisions. `_rewrite_templates()` rewrites `{{t1.output.field[0]}}` refs to include the prefix.

**Agent runner** (`agent_runner.py`): Generic LLM tool-call loop. Reads agent config via `get_agent_config(name)` (reads live model from `model_config` on every call), calls `acompletion()` in a loop until the agent calls `submit_result`. Idempotency: each tool invocation is hashed and cached in `tool_calls` table — re-runs return the stored result without re-firing. Includes: exponential backoff for rate limits, retry-hint injection for Groq `tool_use_failed` errors, `consecutive_errors` counter that forces a "use your knowledge and submit NOW" message after 3 consecutive tool failures, and an early-warning nudge at `max_iter - 3`.

**Agents** (`agent_registry.py`): `researcher` (web_search, http_request, **github_read_file, github_list_dir, github_get_issue, github_search_code**), `writer` (file_ops), `notifier` (slack_notify, http_request), `coder` (code_exec, file_ops, web_search, **github_read_file**), `integrator` (**github_pr, github_post_comment, github_read_file**, http_request, wait_webhook). All go through the same `agent_runner.run()`. Use `get_agent_config(name)` — not `AGENT_REGISTRY[name]` directly — to get the live model setting.

**Model config** (`model_config.py`): Per-role model store. Defaults all roles to Groq. Persists to `backend/model_config.json` (gitignored). `get_model(role)`, `get_all()`, `update(dict)`. Cache invalidated on write. 40 predefined models across Groq (Llama 4, Llama 3.x, DeepSeek, Qwen, Mixtral, Gemma), Anthropic (Claude 4/3.5/3), OpenAI (GPT-4o, o-series, GPT-3.5), Google (Gemini 2.5/2.0/1.5), Mistral (Large/Medium/Small/Codestral). Any LiteLLM-compatible string also accepted. **Note**: `gemini-2.5-pro` and `gemini-1.5-pro` require paid Google AI billing (free tier quota = 0) — the fallback chain handles this automatically.

**LLM layer** (`llm.py`): `acompletion()` wraps LiteLLM with full provider fallback chains for all 40 models. At startup, sets env vars for all 5 providers from `config.settings`; bridges `GOOGLE_API_KEY` → `GEMINI_API_KEY` (LiteLLM uses `GEMINI_API_KEY` for `gemini/` prefix). `_is_hard_rate_limit()` catches daily quota (`tpd`, `quota`), Gemini `resource_exhausted`, and insufficient-quota errors — any of these trigger the fallback chain. `_is_soft_rate_limit()` catches per-minute throttling and sleeps the declared retry delay instead. **Claude 4 models** (`claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`) don't accept `temperature` — it's excluded for them. `not_found_error` (model deprecated) triggers fallback to next candidate and 1h cooldown.

**Tools** (`tools/`): `web_search` (Tavily → DuckDuckGo fallback → training-knowledge note), `http_request` (httpx), `slack_notify`, `file_ops` (workspace-scoped, path traversal protected), `github_pr` (create PR with file commits), `github_read_file` / `github_list_dir` / `github_get_issue` / `github_post_comment` / `github_search_code` (GitHub API operations in `tools/github_ops.py`), `code_exec` (subprocess, 30s timeout), `wait_webhook` (suspends task to `WAITING_WEBHOOK` state).

**Persistence** (`db.py`): SQLite WAL mode, `aiosqlite`. Tables: `goals`, `tasks`, `messages`, `tool_calls`, economy tables `agent_passports`, `agent_reputation`, `proofs`, plus `proof_outbox` (chain submission queue) and `heal_attempts` (self-heal history). Task claim is atomic via `UPDATE ... WHERE id=(SELECT ... LIMIT 1) RETURNING *`. `goals` carries `source`/`heal_depth` (added by migration in `init_db`) so self-heal fix goals are distinguishable and cannot recurse.

**Economy** (`economy.py` + `api/economy.py`): Simulated Monad agent-economy computed from real task history — deterministic, no RNG. `economy.py` provides canonical hashing (`result_hash`/`tx_hash`/`owner_address`), reputation math (`compute_scores`→composite 0..1000, `badge_for` Gold≥800/Silver≥600/Bronze, `apply_delta_cap` ±20%), and orchestration (`seed_passports` — 6 passports + neutral reputation per role; `recompute_role`; `record_proof` — mints a proof + refreshes reputation, **never raises into the worker**, emits `proof_recorded`/`reputation_update` on the `economy` SSE channel; `backfill`). `worker._after_task_done` calls `economy.record_proof(task, output)`. Seed+backfill run in `main.py` lifespan. Contract addresses come from `chain/registry.py` (`deployments/{chainId}.json`) and are real once deployed. Tests: `test_economy{,_db,_flow,_api}.py`. `scripts/replay_demo.py` mints 3 proofs offline (no LLM keys) for a live demo.

**Chain — real on-chain proof-of-work** (`chain/` + `contracts/` + `chain_worker.py`): Replaces the
simulated tx hashes with a real EVM. `contracts/src/*.sol` (Solidity 0.8.24, self-contained, no
OpenZeppelin) define `AgentPassport` (soulbound, one per agent address), `ProofOfWork` (idempotent —
a duplicate `taskId` **reverts on chain**), `ReputationRegistry` (0..10000, 20% max-delta guard
enforced in bytecode) and `AuditTrail` (events only). `chain/compiler.py` compiles via `solcx`, cached
by source hash. `chain/provider.py` offers two interchangeable backends: `LocalEvmProvider`
(in-process py-evm — real bytecode, tx hashes, receipts and event logs with **no keys, tokens or
network**) and `RpcProvider` (JSON-RPC + local signing, nonce management, EIP-1559, retry).
`chain/client.py` is the only thing the app imports; every method degrades to `None` rather than
raising. Target is chosen by `CHAIN_TARGET` (`local` = 31337 default, `monad-testnet` = 10143) with no
code change. On `local` the contracts redeploy on every boot (`main.py::_init_chain`); deploying to a
real network is an explicit operator action (`scripts/deploy_contracts.py --network monad-testnet`).
`READY` requires **bytecode at every address** (`eth_getCode`), not merely a
`deployments/{chainId}.json` that lists them — binding a contract is local ABI work that
succeeds against any address, so without that check a stale or invented record would make the
UI announce a network nothing is deployed on. Failing to *write* the deployment record is a
warning, never fatal: the contracts are deployed either way.

**Proof outbox** (`chain_worker.py`): `economy.record_proof` mints the local proof instantly and
enqueues to `proof_outbox`; `chain_submit_loop` drains it, submits, and advances
`pending→submitting→confirmed`, with exponential backoff and dead-lettering after 10 attempts. A
chain that is down, slow or undeployed only delays settlement — it never blocks or fails a goal.
Restart-safe: rows stranded in `submitting` are reclaimed on boot. Tests:
`test_contracts.py`, `test_chain_client.py`, `test_chain_pipeline.py`, `test_proof_outbox.py`.

**Verification** (`GET /api/economy/verify/{task_id}`, `scripts/verify_proof.py`): recomputes
`sha256(canonical_json(task.output))` and compares it against `ProofOfWork.getProof`, returning every
intermediate so the check is reproducible by hand. Detects post-hoc tampering of a stored output.
Note: with `CHAIN_TARGET=local` the EVM lives inside the backend process, so the CLI verifies through
the running server's API by default; on a real network it reads the chain directly.

**Self-heal** (`self_heal.py` + `error_classifier.py` + `api/heal.py`): on a goal failure the worker
classifies the error; developer-side bugs fingerprint the error (line numbers, ids, hex and
timestamps normalised away), deduplicate against prior attempts (a bug recurring N times bumps
`recurrence_count` instead of filing N issues), record a `heal_attempts` row, file a GitHub issue —
or record a `simulated` attempt with the issue body it *would* have filed when no `GITHUB_TOKEN` is
set, so the feature demos with zero credentials — and spawn a fix goal tagged `source='self_heal'`,
`heal_depth+1`. `MAX_HEAL_DEPTH=1` means a failing fix goal can never spawn another. Outcomes settle
to `fixed`/`failed` via `settle_outcome` when the fix goal ends. Tests: `test_self_heal.py`,
`test_error_classifier.py`.

**SSE** (`api/stream.py` + `events.py`): In-process `asyncio.Queue` per goal (plus global `economy` and `heal` channels). Worker calls `events.emit()`, stream endpoint drains the queue via Server-Sent Events.

**Interpolation** (`interpolation.py`): Resolves `{{task_id.output.field}}` templates in task inputs before execution. Supports array index access (`{{id.output.key_points[0]}}`) and nested paths (`{{id.output.field[0].subfield}}`). `_resolve_path()` splits on `.` and `[N]` segments.

**API Keys** (`api/keys.py`): `GET/PUT /api/config/keys` — reads/writes provider API keys (Groq, Anthropic, OpenAI, Google, Mistral, Tavily) to `backend/.env` via `python-dotenv.set_key()` and updates `os.environ` immediately. Returns masked values. Saving the `google` key also sets `GEMINI_API_KEY` (LiteLLM's expected env var for `gemini/` models).

### Frontend (`frontend/`)

Vite + React + TypeScript + Tailwind CSS + Framer Motion + React Flow + SWR.

- `pages/Dashboard.tsx` — goal list + submission input, stats strip, status filters
- `pages/Webhooks.tsx` — GitHub Automation page at `/app/webhooks`; shows webhook URL with copy button, setup guide (ngrok + GitHub settings), and a "Simulate GitHub Issue" form for testing without a real webhook
- `pages/GoalDetail.tsx` — split-pane: task DAG (React Flow) + expandable task panels + live SSE log
- `components/AppNav.tsx` — sticky nav with Dashboard / Models / API Docs links; active-route highlighting
- `pages/Models.tsx` — full-page model config at `/app/models`; Visual tab (per-role cards + custom model input) and JSON tab (raw editor + live validation); API Keys section (all 6 providers, inline key input, saves to `.env` live)
- `pages/Economy.tsx` — Agent Economy hub at `/app/economy`; tabbed Leaderboard / Passports / Proof Ledger, live via `/api/economy/stream`. `pages/AgentDetail.tsx` at `/app/economy/agents/:role` — NFT-style passport + score breakdown + proof history. Components in `components/economy/{Leaderboard,PassportCard,ProofLedger}.tsx`; economy fetchers/types in `lib/api.ts` mirror the backend responses exactly (bare arrays). `ProofLedger` links tx hashes to the active chain's explorer and offers a per-proof **Verify** button showing computed vs on-chain hash
- `pages/SelfHeal.tsx` — Self-Heal timeline at `/app/heal`; stats strip plus every detected bug with classification, recurrence count, linked issue and fix goal
- `components/WalletConnect.tsx` — mock Monad "Connect Wallet" button (deterministic fake 0x address, localStorage-persisted); mounted in `AppNav.tsx`. `ProtectedRoute.tsx` honours `VITE_DEMO_MODE=true` (`frontend/.env`) to bypass Firebase login for demos
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
| POST | `/api/webhooks/github` | GitHub webhook receiver — auto-creates goals |
| GET | `/api/economy/passports` | List 6 agent passports |
| GET | `/api/economy/leaderboard` | Ranked reputation (composite + badge) |
| GET | `/api/economy/proofs` | Proof-of-work ledger (newest first) |
| GET | `/api/economy/agents/{role}` | Passport + reputation breakdown + proofs |
| GET | `/api/economy/chain` | The chain the app is actually on (id, name, explorer, addresses) |
| GET | `/api/economy/stream` | Economy SSE stream (`proof_recorded`/`reputation_update`/`proof_*`) |
| GET | `/api/economy/verify/{task_id}` | Verify a stored output against its on-chain proof |
| GET | `/api/economy/chain/status` | Active chain, deployment addresses, outbox depth |
| GET | `/api/heal/attempts` | Self-heal history (deduplicated, newest first) |
| GET | `/api/heal/stats` | Distinct bugs, total recurrences, fixed count |
| GET | `/api/heal/stream` | Self-heal SSE stream |
| GET | `/api/health` | Health check |

### Environment

Copy `backend/.env.example` to `backend/.env` and fill in: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `TAVILY_API_KEY`, `SLACK_WEBHOOK_URL`, `GITHUB_TOKEN`, `GITHUB_DEFAULT_REPO`.

Chain settings (`CHAIN_TARGET`, `CHAIN_RPC_URL`, `CHAIN_PRIVATE_KEY`) default to `local`, which needs
nothing. To use Monad testnet, fund the deployer (free MON: `chainstack.com/monad-faucet` has no gate;
`faucet.monad.xyz` gives 10 MON if the wallet holds ≥0.001 ETH on Ethereum mainnet), then:

```bash
cd backend
.venv/bin/python scripts/deploy_contracts.py --network monad-testnet --dry-run   # check first
.venv/bin/python scripts/deploy_contracts.py --network monad-testnet
```

Model selection is managed at runtime via `backend/model_config.json` (created automatically on first run, gitignored). Edit through the UI "Models" button or directly via `PUT /api/config/models`.

### GitHub Automation (the main demo flow)

`POST /api/webhooks/github` (`api/github_webhook.py`) receives GitHub webhook events and auto-creates goals:
- `issues.opened` → creates goal: "Fix GitHub issue #{n} in {repo}" → orchestrator plans researcher→coder→integrator
- `pull_request.opened` → creates goal: "Review PR #{n} in {repo}" → orchestrator plans researcher→writer→integrator

Standard 3-agent pipeline for issue fixing:
1. **researcher**: `github_list_dir` + `github_read_file` + `github_get_issue` to understand the codebase and bug
2. **coder**: writes the fix using `code_context` from researcher, runs tests via `code_exec`
3. **integrator**: `github_pr` (creates PR with fixed files) + `github_post_comment` (posts PR link on original issue)

`_validate_plan` in `orchestrator.py` allows `integrator` as terminal task when the plan has both `coder` and `integrator` agents (detected by `_is_github_automation_plan()`).

**Local demo setup**: `ngrok http 8000` → copy ngrok URL → GitHub repo Settings → Webhooks → Add webhook. Or use the "Simulate GitHub Issue" form on the Automate page (`/app/webhooks`) to test without a real webhook.
