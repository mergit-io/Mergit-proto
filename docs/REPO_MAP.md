# Mergit — Repo Map

Where everything lives and what owns what. Verified against the tree on 2026-08-13.

---

## 1. Documentation

All docs are markdown. There is no generated doc site.

### Root — the six that matter

| File | Lines | What it is | Keep? |
|---|---:|---|---|
| `README.md` | 170 | Setup, local test, dev, production. **Start here.** | ✅ |
| `ARCHITECTURE.md` | 385 | System overview, request lifecycle, GitHub pipeline, agent registry, DB schema | ✅ |
| `CLAUDE.md` | 193 | Instructions for Claude Code + the canonical architecture summary | ✅ |
| `ROADMAP.md` | 214 | **The issue register** — every open item rated P0–P3 | ⚠️ needs reframing |
| `progress.md` | 833 | Dated changelog, one block per work session | ✅ |
| `EXPLANATION.md` | 138 | A 5-minute *pitch script* with timestamps (`[0:00 – 0:30] The Hook`) | ❌ hackathon artifact |

### `docs/` — design records

```
docs/
├── REPO_MAP.md                                  ← this file
└── superpowers/
    ├── specs/    2026-07-18-mergit-prototype-design.md   (what to build + why)
    │             2026-08-12-onchain-proof-layer.md
    └── plans/    2026-07-18-mergit-showcase.md           (step-by-step, checkboxes)
                  2026-08-12-onchain-proof-layer.md
```

Spec = the decision and its rationale. Plan = the ordered steps with `- [x]` state. Both are
**historical records** — they describe what was decided then, not necessarily what is true now.
`ARCHITECTURE.md` and `CLAUDE.md` are the current-state docs.

### Not documentation, despite living in `.md`

- `pitch/DEMO_VIDEO_SCRIPT.md` + `pitch/generate_pdf.py` — hackathon submission material.
  **Dropped as of 2026-08-13**; the directory can go.
- `deploy/Caddyfile`, `deploy/backup-sqlite.sh` — ops config
- `scripts/run-prod.sh`, `scripts/test-local.sh` — repo-root helper scripts

> ⚠️ **Three docs are stale in the same way:** `EXPLANATION.md`, `ROADMAP.md` and `pitch/` are all
> written for "impress a judge / show the manager a demo". Since this is now being built as a real
> product, they describe goals that no longer apply.

---

## 2. Backend — `backend/`

Python 3, FastAPI, aiosqlite. Venv at `backend/.venv/` — always use `.venv/bin/python`.

### Execution core

| File | Owns |
|---|---|
| `main.py` | FastAPI app + lifespan: init DB, start worker, register routers, deploy contracts, serve frontend |
| `worker.py` | The three loops: `goal_planner_loop`, `task_executor_loop` (5 concurrent), `reclaim_loop` (30s) |
| `orchestrator.py` | Goal → task DAG. Forced tool call → `PlanSchema`, 5 retries, Groq failure salvage |
| `agent_runner.py` | The generic LLM tool-call loop every agent runs through. Idempotency via `tool_calls` hashing |
| `agent_registry.py` | Which agent gets which tools. Use `get_agent_config(name)`, never the dict directly |
| `replanner.py` | When a task fails at `max_attempts`, asks the orchestrator for a repair plan |
| `interpolation.py` | Resolves `{{task_id.output.field[0]}}` refs in task inputs before execution |

### Data & state

| File | Owns |
|---|---|
| `db.py` | All SQLite. WAL mode. Atomic task claim via `UPDATE … RETURNING`. Every table lives here |
| `state.py` | Row dataclasses (`GoalRow`, `TaskRow`, …) + the `GoalStatus`/`TaskStatus` enums |
| `models.py` | Pydantic request/response schemas for the API |
| `events.py` | In-process SSE pub/sub — one `asyncio.Queue` per goal, plus `economy` and `heal` channels |
| `context.py` | User-supplied global context injected into agent prompts (`load`/`save`/`get_context_prompt`) |

### LLM layer

| File | Owns |
|---|---|
| `llm.py` | `acompletion()` — LiteLLM wrapper + provider fallback chains, hard/soft rate-limit handling |
| `model_config.py` | Per-role model store → `backend/model_config.json` (gitignored). **15** predefined ids: Groq (8), Anthropic (5), OpenRouter (2). `PUT /api/config/models` rejects anything not on the list. No OpenAI/Gemini/Mistral support exists |
| `model_health.py` | In-memory health tracker — cooldowns for deprecated/exhausted models |
| `config.py` | `settings` — env/`.env` loading for every key and chain var |

### Economy & chain

| File | Owns |
|---|---|
| `economy.py` | Canonical hashing, reputation math, `record_proof` (never raises into the worker), `backfill` |
| `chain/client.py` | **The only chain API the app imports.** Every method degrades to `None`, never raises |
| `chain/provider.py` | `LocalEvmProvider` (in-process py-evm) and `RpcProvider` (JSON-RPC + signing) |
| `chain/compiler.py` | solcx compilation, cached by source hash |
| `chain/deployer.py` | Deploys all four contracts; a failed record write is a warning, never fatal |
| `chain/registry.py` | Reads/writes `deployments/{chainId}.json` |
| `chain/networks.py` | Network definitions — `local` (31337), `monad-testnet` (10143) |
| `chain_worker.py` | Drains `proof_outbox`: `pending→submitting→confirmed`, backoff, dead-letter at 10 |
| `contracts/src/*.sol` | `AgentPassport`, `ProofOfWork`, `ReputationRegistry`, `AuditTrail` (Solidity 0.8.24) |

### Self-heal

| File | Owns |
|---|---|
| `error_classifier.py` | Is this failure a developer bug or an environment problem? |
| `self_heal.py` | Fingerprint → dedup → `heal_attempts` row → GitHub issue → fix goal (`MAX_HEAL_DEPTH=1`) |

### API — `backend/api/`

| Route file | Prefix |
|---|---|
| `goals.py` | `/api/goals` — submit, list, detail |
| `tasks.py` | `/api/tasks` |
| `stream.py` | `/api/goals/{id}/stream` — SSE |
| `economy.py` | `/api/economy/*` — passports, leaderboard, proofs, chain, verify, stream |
| `heal.py` | `/api/heal/*` — attempts, stats, stream |
| `config.py` | `/api/config/models` |
| `keys.py` | `/api/config/keys` — **writes provider keys to `.env`. Unauthenticated.** |
| `context.py` | `/api/config/context` |
| `webhooks.py` | `/api/webhooks/{token}` — resume a `WAITING_WEBHOOK` task |
| `github_webhook.py` | `/api/webhooks/github` — issue/PR events auto-create goals |
| `actions.py` | GitHub Actions & branch-protection management |
| `auth.py` | `/api/auth/*` — Google/GitHub OAuth, signed session cookie |
| `health.py` | `/api/health` |

### Tools — `backend/tools/`

`TOOL_REGISTRY` in `tools/__init__.py` is the source of truth: **26 entries, 20 of them GitHub.**

`web_search` (Tavily → DuckDuckGo Instant Answer → training-knowledge note; the middle step returns
nothing for ordinary dev queries) · `http_request` · `file_ops` (workspace-scoped,
traversal-protected) · `code_exec` (subprocess, 30s) · `github_ops` (18 read/write tools) ·
`github_pr` (commit + PR, forks when it lacks push access, refuses content that would truncate an
existing file) · `wait_webhook` (suspends to `WAITING_WEBHOOK`) · `credential_request` (the
`WAITING_CREDENTIAL` sentinel — a constant, not a callable tool) · `spawn_goal`

### Operator scripts — `backend/scripts/`

| Script | Does |
|---|---|
| `replay_demo.py` | Mints 3 proofs offline, no LLM keys — the demo seeder |
| `demo_tamper.py` | verify ✓ → edit SQLite behind the app's back → ✗ MISMATCH → restore ✓ |
| `verify_proof.py` | CLI for `GET /api/economy/verify/{task_id}` |
| `deploy_contracts.py` | Explicit deploy to a real network (`--network monad-testnet --dry-run`) |
| `loadtest.py` | N concurrent users on SSE + polling; p50/p95/max per endpoint |

### Tests — 170, all in `backend/test_*.py`

`conftest.py` provides an autouse fresh-event-loop fixture. Run: `.venv/bin/python -m pytest -q`

> 🔎 `jsonstats.py` + `test_jsonstats.py` are **not imported by the app**. They came in via
> commit `5795931` as an agent-generated fix target. Harmless, but they are not part of Mergit.

---

## 3. Frontend — `frontend/`

Vite + React + TypeScript + Tailwind + Framer Motion + React Flow + SWR.
Dev proxies `/api/*` → `:8000`. Production: FastAPI serves `frontend/dist/` at `/`.

### Pages — `src/pages/`

| Page | Route |
|---|---|
| `Landing.tsx` | `/` |
| `Login.tsx` | `/login` |
| `Dashboard.tsx` | `/app` — goal list, submission, stats, filters |
| `GoalDetail.tsx` | `/app/goals/:id` — task DAG + panels + live SSE log |
| `Economy.tsx` | `/app/economy` — leaderboard / passports / proof ledger |
| `AgentDetail.tsx` | `/app/economy/agents/:role` |
| `SelfHeal.tsx` | `/app/heal` |
| `Models.tsx` | `/app/models` — per-role models + API keys |
| `Webhooks.tsx` | `/app/webhooks` — webhook URL, setup guide, **Simulate GitHub Issue** form |
| `Actions.tsx` | GitHub Actions management |

### Components — `src/components/`

`AppNav` · `AppBackground` · `ProtectedRoute` (honours `VITE_DEMO_MODE`) · `WalletConnect`
(**mock** address) · `GoalCard` · `GoalInput` · `TaskDAG` · `TaskPanel` · `LiveLog` ·
`OutputDisplay` · `StatusBadge` · `AgentBadge` · `ModelSettings` · `ModelErrorBanner` ·
`economy/{Leaderboard,PassportCard,ProofLedger}` · `landing/`

### Lib — `src/lib/`

| File | Owns |
|---|---|
| `api.ts` | Every fetch wrapper + the economy types, mirroring backend responses exactly |
| `sse.ts` | `useSSE()` — `EventSource` with auto-reconnect |
| `firebase.ts` | Auth config, read from `VITE_FIREBASE_*` env vars — see `frontend/.env.example` |

---

## 4. Deploy & config

| Path | Purpose |
|---|---|
| `Dockerfile` | Multi-stage. `ARG VITE_DEMO_MODE=true`. Compiles contracts at build time |
| `compose.yaml` | App + Caddy |
| `render.yaml` | Render blueprint |
| `Makefile` | `install`, `dev`, `dev-backend`, `dev-frontend`, `build`, `reset-db` |
| `deploy/Caddyfile` | TLS reverse proxy |
| `deploy/backup-sqlite.sh` | Container-engine autodetect (docker/podman) |
| `backend/.env` | **gitignored** — all provider keys, chain settings |
| `frontend/.env` | `VITE_DEMO_MODE` only (tracked; not a secret) |
| `frontend/.env.example` | Demo mode + the seven `VITE_FIREBASE_*` vars |

---

## 5. Known gaps in the docs themselves

1. **`CLAUDE.md`'s architecture section is incomplete.** It does not mention `replanner.py`,
   `context.py`, `model_health.py`, `state.py`, `models.py`, `api/actions.py`, `api/auth.py`,
   `api/context.py`, `tools/spawn_goal.py`, `tools/credential_request.py`, or the `Landing`,
   `Login` and `Actions` pages. Anyone trusting it as the full map will miss ~10 modules.
2. **`ROADMAP.md` is framed for a demo**, not a product — its trade-offs (ephemeral chain,
   deferred auth, free-tier sizing) assume a throwaway deployment.
3. **`EXPLANATION.md` and `pitch/` are hackathon artifacts** and now describe a goal that no
   longer exists.
