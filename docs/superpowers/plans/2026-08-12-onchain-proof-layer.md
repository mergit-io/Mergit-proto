# Mergit On-Chain Proof Layer — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-08-12-onchain-proof-layer.md`
**Started:** 2026-08-12
**Completed:** 2026-08-12 — all milestones green, 131 backend tests passing

**Goal:** Replace the simulated Monad economy with a real EVM proof pipeline — real Solidity,
real transactions, real event logs, on-chain idempotency, and a verification endpoint — running
by default on an in-process EVM so it needs no keys, tokens, or network. Then make self-heal a
genuinely showcaseable feature.

**Tech:** Solidity 0.8.24 (`solcx`) · `py-evm`/`eth-tester` · `web3.py` 7.16 · FastAPI ·
aiosqlite · React/TS.

## Global Constraints

- **No git operations by the assistant.** Every milestone ends at a **CHECKPOINT** where the exact
  `git` commands are printed for the user to run. Never run them.
- Backend venv is `backend/.venv/`; always `backend/.venv/bin/python`.
- TDD for all backend logic: write the failing test, watch it fail, implement, watch it pass.
- Tests must pass with **no RPC URL, no private key, no network**.
- `economy.record_proof` must never raise into the worker. Chain failures degrade, never break.
- The existing 38 tests stay green at every checkpoint.
- Chain target default `local`; Monad testnet (10143) selected by env, no code change.
- No external Solidity imports (no OpenZeppelin) — contracts are self-contained.

## Milestones

| # | Milestone | Deliverable |
|---|---|---|
| M1 | Solidity contracts + EVM test harness | 4 contracts compiling and unit-tested on a real EVM |
| M2 | Chain layer (compiler, providers, client) | `ChainClient` usable against local EVM or any RPC |
| M3 | Durable proof outbox + worker submission | Proofs survive restarts; chain never blocks a goal |
| M4 | Verification API + CLI | `verify/{task_id}` proves stored output matches chain |
| M5 | Deploy tooling | One command deploys to local or Monad testnet |
| M6 | Frontend on-chain surfaces | Real tx links, chain status, verify button |
| M7 | Self-heal enhancement | Tested, deduped, loop-safe, observable, demoable |
| M9 | Remove Omium tracing | Third-party tracing dependency fully excised |
| M8 | Docs + full verification | `CLAUDE.md` + `progress.md`, whole suite green |

---

## M1 — Solidity contracts + EVM test harness

**Create:** `backend/contracts/src/{Roles,AgentPassport,ProofOfWork,ReputationRegistry,AuditTrail}.sol`,
`backend/chain/compiler.py`, `backend/test_contracts.py`

- [x] **Step 1** — Write `backend/test_contracts.py` covering: passport mints and is soulbound
      (transfer reverts); duplicate mint per address reverts; `recordProof` stores and emits;
      **duplicate `taskId` reverts**; `updateScore` accepts a legal move and **reverts >20% delta**;
      `logAction` emits with zero storage writes; non-role callers are rejected.
- [x] **Step 2** — Run; expect FAIL (no contracts, no compiler). → `ModuleNotFoundError: No module named 'chain'`
- [x] **Step 3** — Implement `compiler.py`: `compile_all()` → `{name: {abi, bin}}`, cached to
      `contracts/out/*.json`, invalidated by source hash.
- [x] **Step 4** — Implement the 5 `.sol` files per spec §1.
- [x] **Step 5** — Run; expect PASS. → **17 passed**, full suite **55 passed**. Artifacts written;
      largest contract 4842 bytes (EIP-170 limit 24576).
- [x] **CHECKPOINT M1**

## M2 — Chain layer

**Create:** `backend/chain/{__init__,networks,provider,client,registry}.py`, `backend/test_chain_client.py`
**Modify:** `backend/config.py` (chain settings), `backend/requirements.txt`

- [x] **Step 1** — Write `test_chain_client.py`: client boots on local EVM; `record_proof` returns a
      real 66-char tx hash and block number; event decodes; `get_proof` reads back; duplicate is
      benign not fatal; `task_id`→`bytes32` round-trips; no deployment → `not_deployed`, no crash.
- [x] **Step 2** — Run; expect FAIL.
- [x] **Step 3** — `networks.py` (LOCAL 31337, MONAD_TESTNET 10143 + explorer templates).
- [x] **Step 4** — `provider.py` (`LocalEvmProvider`, `RpcProvider` with signing/nonce/retry).
- [x] **Step 5** — `registry.py` (read/write `deployments/{chain_id}.json`).
- [x] **Step 6** — `client.py` (`ChainClient` + hash conversion + revert classification).
- [x] **Step 7** — Add `chain_target`/`chain_rpc_url`/`chain_private_key`/`chain_enabled` to config;
      pin `web3`, `py-solc-x`, `eth-tester[py-evm]` in requirements.
- [x] **Step 8** — Run; expect PASS.
- [x] **CHECKPOINT M2**

## M3 — Durable proof outbox + worker submission

**Modify:** `backend/db.py` (table + accessors), `backend/economy.py` (enqueue), `backend/worker.py` (loop)
**Create:** `backend/chain_worker.py`, `backend/test_proof_outbox.py`

- [x] **Step 1** — Write `test_proof_outbox.py`: enqueue creates `pending`; `claim_pending` is
      atomic; success → `confirmed` with tx/block; failure increments `attempts` + backoff;
      10 attempts → `dead_lettered`; enqueue is idempotent per `task_id`; pending rows survive restart.
- [x] **Step 2** — Run; expect FAIL.
- [x] **Step 3** — Add `proof_outbox` to `SCHEMA` + accessors in `db.py`.
- [x] **Step 4** — `economy.record_proof` also enqueues to the outbox (still never raises).
- [x] **Step 5** — `chain_worker.chain_submit_loop`: drain → submit → advance status → emit
      `proof_pending`/`proof_submitted`/`proof_confirmed`/`proof_failed` on the `economy` channel.
- [x] **Step 6** — Start the loop in `worker.start()`, gated on `chain_enabled`.
- [x] **Step 7** — Run full suite; expect PASS including the original 38.
- [x] **CHECKPOINT M3**

## M4 — Verification API + CLI

**Modify:** `backend/api/economy.py`
**Create:** `backend/scripts/verify_proof.py`, `backend/test_verify.py`

- [x] **Step 1** — Write `test_verify.py`: matching stored output → `verified: true` with all
      intermediates; tampered output → `verified: false` and hashes differ; unknown task → 404;
      task with no on-chain proof → `verified: null` + reason, not an error.
- [x] **Step 2** — Run; expect FAIL.
- [x] **Step 3** — Implement `GET /api/economy/verify/{task_id}` per spec §5.
- [x] **Step 4** — Implement `scripts/verify_proof.py <task_id>` printing a human-readable audit.
- [x] **Step 5** — Run; expect PASS.
- [x] **CHECKPOINT M4**

## M5 — Deploy tooling

**Create:** `backend/scripts/deploy_contracts.py`
**Modify:** `backend/main.py` (lifespan auto-deploy on local), `backend/.env.example`

- [x] **Step 1** — Deploy script: compile → deploy in dependency order (Passport → AuditTrail →
      ProofOfWork → ReputationRegistry) → grant roles → write `deployments/{chain_id}.json` →
      print explorer links. `--network local|monad-testnet`, `--dry-run`.
- [x] **Step 2** — On `local`, auto-deploy in the `main.py` lifespan so a dev run is chain-live
      with zero setup. Never auto-deploy to a real network.
- [x] **Step 3** — Document `CHAIN_TARGET`, `CHAIN_RPC_URL`, `CHAIN_PRIVATE_KEY` in `.env.example`
      with the Monad faucet options.
- [x] **Step 4** — Verify: `deploy_contracts.py --network local` writes `deployments/31337.json`;
      `--network monad-testnet --dry-run` reports what it would do without a key.
- [x] **CHECKPOINT M5**

## M6 — Frontend on-chain surfaces

**Modify:** `frontend/src/lib/api.ts`, `components/economy/ProofLedger.tsx`, `pages/AgentDetail.tsx`,
`components/AppNav.tsx`

- [x] **Step 1** — Types + fetchers for verify and chain status.
- [x] **Step 2** — Proof Ledger: real tx hash linking to the explorer; lifecycle status chip
      (pending → submitted → confirmed); live updates from the new SSE events.
- [x] **Step 3** — Per-proof **Verify** button showing computed vs on-chain hash.
- [x] **Step 4** — Nav chain badge: target name, chainId, connected/not-deployed state.
- [x] **Step 5** — `npx tsc --noEmit && npm run build` → 0 errors.
- [x] **CHECKPOINT M6**

## M7 — Self-heal enhancement

**Create:** `backend/api/heal.py`, `backend/test_self_heal.py`, `backend/test_error_classifier.py`,
`frontend/src/pages/SelfHeal.tsx`
**Modify:** `backend/db.py`, `backend/self_heal.py`, `backend/worker.py`, `backend/main.py`,
`frontend/src/App.tsx`, `frontend/src/components/AppNav.tsx`

Addresses the 9 gaps from the 2026-08-12 audit (spec §6).

- [x] **Step 1** — Write `test_error_classifier.py`: a table of real error strings → expected
      classification, covering every external pattern and every bug-exception branch.
- [x] **Step 2** — Write `test_self_heal.py`: identical errors dedupe to one attempt with
      `recurrence_count` incremented; a `heal_depth>=1` goal never triggers heal (recursion guard);
      with no `GITHUB_TOKEN` a `simulated` attempt is still recorded; outcome settles when the fix
      goal finishes.
- [x] **Step 3** — Run both; expect FAIL.
- [x] **Step 4** — Add `heal_attempts` table + accessors; add `source`/`heal_depth` to goals.
- [x] **Step 5** — Rework `self_heal.trigger`: fingerprint → dedup → recursion guard → record
      attempt → file issue (or simulate) → spawn tagged fix goal → emit SSE.
- [x] **Step 6** — Guard the `asyncio.create_task` call in `worker.py` with a done-callback that
      logs exceptions instead of swallowing them.
- [x] **Step 7** — `api/heal.py`: `GET /api/heal/attempts`, `GET /api/heal/stats`; register in `main.py`.
- [x] **Step 8** — `pages/SelfHeal.tsx` at `/app/heal`: timeline of attempts (error, classification,
      issue link, fix-goal link, outcome, recurrence count) + stats strip. Nav link.
- [x] **Step 9** — Run full suite + frontend build; expect PASS.
- [x] **CHECKPOINT M7**

## M9 — Remove Omium tracing (added 2026-08-12 at user request)

Omium was never load-bearing: `tracing.py` degraded to no-ops whenever the SDK was absent,
which is every environment here (`omium not installed — tracing disabled` on every boot).
It costs a module, config, env vars, deploy wiring and call sites in 7 modules for nothing.
Removing it outright rather than leaving a dead abstraction.

**Delete:** `backend/tracing.py`
**Modify:** `backend/worker.py`, `backend/agent_runner.py`, `backend/api/webhooks.py`,
`backend/api/keys.py`, `backend/tools/http_request.py`, `backend/config.py`, `backend/main.py`,
`backend/.env.example`, `render.yaml`, `.env.production.example`, `README.md`, `CLAUDE.md`,
`ARCHITECTURE.md`

- [x] **Step 1** — Remove `goal_trace_context` / `task_span` call sites from `worker.py`,
      preserving the surrounding control flow exactly.
- [x] **Step 2** — Remove `tool_span` / `trace` / `set_execution_context` from `agent_runner.py`
      and `tools/http_request.py`; drop the `tracer` parameter threading.
- [x] **Step 3** — Remove `webhook_span` from `api/webhooks.py`; drop the `omium` provider from
      `api/keys.py`.
- [x] **Step 4** — Drop `omium_*` settings from `config.py` and `init_tracing` from `main.py`.
- [x] **Step 5** — Delete `backend/tracing.py`. Purge `OMIUM_*` from `.env.example`,
      `.env.production.example`, `render.yaml`, `README.md`, `CLAUDE.md`, `ARCHITECTURE.md`.
      Drop `tracing.py` from the `error_classifier` "our files" regex.
- [x] **Step 6** — Full suite green; `grep -ri omium` returns nothing outside `progress.md`
      history. Boot the server and confirm the "omium not installed" warning is gone.
- [x] **CHECKPOINT M9**

## M8 — Docs + full verification

- [x] **Step 1** — Full backend suite green; report counts.
- [x] **Step 2** — Frontend `tsc --noEmit` + `build` clean.
- [x] **Step 3** — End-to-end: start backend on local chain, run `replay_demo.py`, confirm proofs
      reach `confirmed` with real tx hashes and verification passes.
- [x] **Step 4** — Update `CLAUDE.md` (chain package, contracts, outbox, endpoints, self-heal).
- [x] **Step 5** — Append a dated session block to `progress.md`.
- [x] **CHECKPOINT M8** — final summary.

---

## Self-Review

**Spec coverage:** contracts §1→M1; chain layer §2→M2; outbox §3→M3; events §4→M3+M6;
verification §5→M4; self-heal §6→M7. Deploy tooling→M5. Docs protocol→M8.

**Success criteria:** (1)→M1 (2)→M3 (3)→M1 contract revert + M2 client handling (4)→M4 (5)→every
milestone runs keyless (6)→M2 networks + M5 deploy (7)→M3 outbox (8)→M7.

**Consistency:** `result_hash` stays `sha256(canonical_json(output))` exactly as `economy.py`
computes today, so existing proofs and the new on-chain hashes agree. `task_id`→`bytes32` is
always `keccak(task_id)`. Outbox status vocabulary is fixed at
`pending|submitting|submitted|confirmed|failed|dead_lettered` across db, worker, API, and UI.
