# Mergit Showcase Prototype — Design

**Date:** 2026-07-18
**Status:** Approved (design), pending implementation plan

## Purpose

Turn the working multi-agent autonomy engine (this repo, `mergit-proto`) into a
**Mergit** showcase prototype that can be put in front of people today to gauge preference for
the *Mergit vision*: an AI **agent economy** on the Monad blockchain (per `mergit-docs.git/PRD.md`).

The real orchestration engine (orchestrator → task DAG → specialist agents) stays intact and runs
for real. On top of it we add a **simulated Monad agent-economy layer** — agent passports, live
reputation, proof-of-work ledger, leaderboard — and a **full rebrand** to Mergit.

**This is a preference-gathering demo, not a production build.** Blockchain is visually simulated;
no real Monad/contract integration. YAGNI applies to anything beyond selling the vision.

## Guiding principle: the economy must feel *alive*

Static mock screens read as fake. The economy layer is **computed from real task runs**:
run a goal → agents execute for real → each completed task mints a proof and bumps its agent's
reputation → the ledger and leaderboard update live over SSE. That is the "wow" that reads as real.

## Success criteria

1. App runs end-to-end locally from a clean checkout after a documented setup (`make` targets).
2. Landing + app are branded "Mergit" with a distinct on-chain visual identity (no legacy branding left visible).
3. Running a real goal produces: live proofs in the ledger, rising reputation, updated leaderboard.
4. Passports, Leaderboard, and Proof Ledger pages are populated on first load (seeded), not empty.
5. A scripted **replay mode** can run the full flow as a safety net even if live LLM calls fail.
6. Login does not block the demo (DEMO_MODE bypass).

## Scope (in)

- Backend agent-economy module + tables + API + live SSE channel.
- Frontend economy pages (Leaderboard, Passports, Proof Ledger, Agent detail) + mock wallet connect.
- Full rebrand + new visual identity.
- Runnability: env/deps/build, DEMO_MODE auth bypass, seed data, replay mode, updated demo script.

## Scope (out)

- Real Monad testnet integration, real contracts, real wallet signing.
- Rust services from the PRD (api-gateway, identity, indexer, reputation service). The economy layer
  is a single Python module inside the existing FastAPI process.
- Postgres/Redis. Stays on the existing SQLite/aiosqlite persistence.

---

## Architecture

### 1. Economy engine — `backend/economy.py`

Pure functions + DB access; no LLM calls. Deterministic (no RNG).

**Passports** — one per agent role (`orchestrator`, `researcher`, `writer`, `coder`,
`integrator`, `notifier`), seeded on init:
- `did` = `did:mergit:agent:<role>`
- `token_id` = sequential (1..N), `soulbound` = true
- `capabilities` = tool names from `agent_registry` for that role
- `owner_address` = deterministic mock Monad address (e.g. `0x` + first 40 hex of `sha256(role)`)
- `minted_at`, `mint_block` (seeded base block + index)

**Reputation** — composite score `0..1000`, computed from real `tasks` history for the role:
- `success_rate` = done / (done + failed)
- `speed` = normalized against a baseline task duration (settled_at − started_at)
- `volume` = log-scaled count of completed tasks
- `composite` = weighted sum (weights documented in code), clamped 0..1000
- Badge tier: Gold ≥ 800, Silver ≥ 600, Bronze otherwise.
- Reputation update honors the PRD's "max 20% delta per update" anti-manipulation rule (cosmetic here,
  but keeps the narrative consistent).

**Proof-of-Work** — one proof per completed task, idempotent on `task_id`:
- `result_hash` = `SHA-256(canonical_json(output))`
- `tx_hash` = `0x` + `SHA-256(task_id + result_hash)[:64]`
- `block_number` = monotonic counter (seeded base + increment)
- fields: `task_id`, `goal_id`, `agent_role`, `result_hash`, `tx_hash`, `block_number`, `recorded_at`

**Entry point:** `economy.record_proof(task, output)` — called from the worker. Writes the proof
(idempotent), recomputes the agent's reputation, writes a reputation snapshot, and emits live events.

### 2. Persistence — new tables in `backend/db.py`

- `agent_passports` (role PK, did, token_id, soulbound, capabilities JSON, owner_address, minted_at, mint_block)
- `agent_reputation` (role PK, composite, success_rate, speed, volume, badge, updated_at)
- `proofs` (task_id PK, goal_id, agent_role, result_hash, tx_hash, block_number, recorded_at)

`init_db()` seeds passports for all roles and, if `proofs` is empty, backfills historical proofs +
reputation from existing completed tasks in the DB (so pages are populated on first load).

### 3. Live channel — `backend/events.py`

Reuse the existing per-key `asyncio.Queue` infra with a reserved global key `"economy"`.
`economy.record_proof` emits `proof_recorded` and `reputation_update` on that key. A new SSE endpoint
drains it. No change to existing per-goal streaming.

### 4. API — `backend/api/economy.py` (router mounted under `/api/economy`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/economy/passports` | All agent passports |
| GET | `/api/economy/leaderboard` | Agents ranked by composite score + badges |
| GET | `/api/economy/proofs?limit=&before=` | Proof ledger feed (newest first, paginated) |
| GET | `/api/economy/agents/{role}` | Passport + score breakdown + recent proofs |
| GET | `/api/economy/chain` | Mock chain info: chainId 10143, contract addresses |
| GET | `/api/economy/stream` | SSE: `proof_recorded`, `reputation_update` |

Mock contract addresses live in a committed `backend/deployments/10143.json`
(`AgentPassport`, `ProofOfWork`, `ReputationRegistry`, `AuditTrail`).

### 5. Worker hook — `backend/worker.py`

In `_after_task_done`, after `settle_task(... DONE)`, call
`await economy.record_proof(task, output)` inside try/except (economy failures must never break a run).

### 6. Frontend — new pages + rebrand

New identity applied via the `frontend-design` skill during implementation:
Mergit wordmark; on-chain aesthetic (deep indigo/violet base + electric cyan/green accents; monospace
numerals for hashes/scores/blocks). Replace all legacy brand strings and hero copy.

**Routing (`App.tsx`)** — add:
- `/app/economy` — economy hub with tabs: **Leaderboard**, **Passports**, **Proof Ledger**
- `/app/economy/agents/:role` — agent detail (passport + score breakdown + proofs)

**Components:**
- `pages/Economy.tsx` (tabbed hub)
- `components/economy/Leaderboard.tsx` — ranked rows, badge chips, animated score changes
- `components/economy/PassportCard.tsx` + gallery — NFT-style soulbound cards
- `components/economy/ProofLedger.tsx` — live-streaming feed (tx hash, block, result hash, agent), new rows animate in via `/api/economy/stream`
- `pages/AgentDetail.tsx`
- `components/WalletConnect.tsx` — mock "Connect Wallet" → fakes Monad testnet 10143 + a fake address; purely cosmetic, stored in local state.
- `lib/api.ts` — add economy fetchers; `lib/sse.ts` — reuse `useSSE` for the economy stream.
- Rebranded `pages/Landing.tsx` + landing components pitching the **agent economy**.
- `components/AppNav.tsx` — add "Economy" link + wallet button.

### 7. Runnability & demo-readiness

- **Setup:** `make install` (venv + pip + npm), create `backend/.env` from example with the live keys,
  `make build` for the frontend. Document exact steps.
- **Auth bypass:** add `DEMO_MODE` (frontend env `VITE_DEMO_MODE=true`). When set, `ProtectedRoute`
  renders children without requiring Firebase login. Default off; on for the showcase.
- **Seed data:** covered by `init_db()` backfill (§2) so all economy pages have content immediately.
- **Replay mode (safety net):** a scripted deterministic goal (`scripts/replay-demo.py` or a
  `REPLAY`-flagged goal path) that walks a canned researcher→coder→integrator run, emitting the same
  task/proof/reputation events without live LLM calls. Primary path is the live run; replay is the
  fallback so a rate-limit never kills the showcase.
- **Demo script:** update `pitch/DEMO_VIDEO_SCRIPT.md` for the Mergit agent-economy narrative.

## Data flow (live run)

```
User submits goal
  → orchestrator plans DAG (real)
  → agents execute tasks (real, via agent_runner)
  → on each task DONE: worker.settle_task → economy.record_proof
       → write proof (SHA-256 of real output, fake tx/block)
       → recompute + snapshot reputation (capped delta)
       → events.emit("economy", proof_recorded / reputation_update)
  → SSE /api/economy/stream pushes to Proof Ledger + Leaderboard (live update)
  → goal COMPLETED
```

## Error handling

- `economy.record_proof` wrapped in try/except in the worker — never breaks task settlement.
- Proof writes idempotent on `task_id` (safe on retries/reclaims).
- Economy API endpoints degrade gracefully (empty lists) if tables are empty.
- Replay mode isolated from live path; failure there doesn't affect real runs.

## Testing

- Unit: reputation composite math (deterministic inputs → known score, delta cap enforced),
  proof hashing (stable `result_hash`/`tx_hash` for fixed input), idempotency on repeat `record_proof`.
- Integration: init seeds passports; backfill populates proofs from existing completed tasks.
- Manual/e2e: run a real goal, confirm proofs stream into the ledger and a score rises live;
  run replay mode with no keys and confirm the same surfaces update.
- Frontend builds clean (0 TypeScript errors); no legacy brand string remains in shipped UI.

## Update protocol (per repo CLAUDE.md)

On completion, update `CLAUDE.md` (architecture: new `economy.py`, tables, API, pages, rebrand) and
append a dated session block to `progress.md`.
