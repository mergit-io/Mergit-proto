# Mergit — Real On-Chain Proof Layer (Design)

**Date:** 2026-08-12
**Status:** Approved (design), plan in `docs/superpowers/plans/2026-08-12-onchain-proof-layer.md`
**Supersedes:** the simulated chain in `docs/superpowers/specs/2026-07-18-mergit-prototype-design.md` §1/§4

## Purpose

The showcase prototype's agent economy is **entirely simulated** — `economy.py` derives fake
`tx_hash`/`block_number` values by hashing, and `deployments/10143.json` holds invented contract
addresses. Nothing touches an EVM. PRD §4.3 names this exact failure mode as what Mergit is
supposed to disprove: *"most AI agent demos have zero blockchain substance — vague 'we log to
chain' claims with no cryptographic integrity."*

This spec replaces the simulation with a **real EVM proof pipeline**: real Solidity contracts,
real compiled bytecode, real transactions, real receipts, real event logs, real on-chain
idempotency — and a verification path that proves a stored agent output matches what is on chain.

## Decisions taken (user, 2026-08-12)

| Decision | Choice | Rationale |
|---|---|---|
| Target chain | **Monad testnet, chainId 10143** | MON is free (Chainstack 0.5/24h no-gate; 10 MON with 0.001 ETH mainnet). Sepolia gates identically, so it bought nothing while costing the Monad narrative. |
| Contracts location | **`backend/contracts/` in mergit-proto** | Prototype stays one runnable, committable unit. Lifted into `mergit-contracts` (MIT, Foundry) for the real build. |
| Default run mode | **Local in-process EVM** | Every test and local run executes real bytecode with no keys, tokens, or network. Faucet funding never blocks development. |
| Live deploy | **One command, when funded** | `deploy_contracts.py --network monad-testnet` with an RPC URL + funded key. User's call, not a dependency. |

## Guiding principle: real cryptography, optional network

Every claim the UI makes must be **independently checkable**. A `tx_hash` shown in the Proof
Ledger must be a hash of an actual signed transaction that actually executed contract bytecode.
The chain it executed on is a deployment detail; the cryptographic integrity is not.

## Success criteria

1. Four Solidity contracts compile from source and pass unit tests against a real EVM.
2. A completed agent task results in a real `recordProof` transaction with a real receipt.
3. Recording the same `task_id` twice is rejected **on-chain** (contract revert), not just in Python.
4. `GET /api/economy/verify/{task_id}` recomputes the hash from stored output and proves it matches chain state.
5. The whole pipeline runs green in CI/tests with **no RPC URL and no private key**.
6. Supplying an RPC URL + funded key switches to Monad testnet with **no code change**.
7. Chain failure never breaks a goal run — proofs degrade to queued, never lost (outbox).
8. Self-heal is observable, deduplicated, loop-safe, tested, and demoable offline.

## Scope (in)

- Solidity: `AgentPassport`, `ProofOfWork`, `ReputationRegistry`, `AuditTrail` + minimal access control.
- Python chain layer: compiler, provider abstraction, client, deployment registry.
- Durable proof outbox + background submission worker (PRD §5.4).
- Verification API + CLI.
- Deploy script targeting local EVM or Monad testnet.
- Frontend: real tx/explorer links, chain status, verify action.
- Self-heal enhancement to a showcaseable feature.

## Scope (out)

- OpenZeppelin dependency (contracts are self-contained; OZ swap happens in `mergit-contracts`).
- Foundry/`forge` (not installed; tests run via `solcx` + `py-evm` in pytest).
- Merkle bundling, staking/slashing, `TaskEscrow` — PRD Phase 3+.
- Rust services, LangGraph, Postgres/Redis — separate repo, separate effort.
- Mainnet.

---

## Architecture

### 1. Contracts — `backend/contracts/src/`

Self-contained Solidity 0.8.24, no external imports (keeps `solcx` compilation dependency-free).

**`Roles.sol`** — minimal role-based access control. `DEFAULT_ADMIN`, `grantRole`, `hasRole`,
`onlyRole` modifier. Replaces OZ `AccessControl` for the prototype.

**`AgentPassport.sol`** — soulbound identity token.
- `mint(address owner, string did, bytes32 capabilityHash) returns (uint256 tokenId)` — `MINTER_ROLE`
- One token per address (`agentToTokenId` mapping); re-mint reverts
- Non-transferable: `transferFrom`/`safeTransferFrom` revert with `Soulbound()`
- Tracks `tasksCompleted`, `tasksAttempted`, `registeredAt`, `active`
- `recordTaskResult(uint256 tokenId, bool success)` — callable by `ProofOfWork`

**`ProofOfWork.sol`** — the core ledger.
- `recordProof(bytes32 taskId, uint256 agentTokenId, bytes32 resultHash)` — `RECORDER_ROLE`
- **Idempotent on `taskId`**: second write reverts `ProofAlreadyRecorded(taskId)`
- Emits `ProofRecorded(bytes32 indexed taskId, uint256 indexed agentTokenId, bytes32 resultHash, uint256 blockNumber)`
- `getProof(bytes32 taskId) returns (Proof)` — the verification read path
- Increments passport task counters

**`ReputationRegistry.sol`** — oracle-updated scores.
- `updateScore(uint256 agentTokenId, uint32 score, bytes32 componentHash)` — `ORACLE_ROLE`
- Score range `0..10000` (PRD §5.5 scale)
- **Enforces the PRD's 20% max-delta guard on-chain** — reverts `DeltaTooLarge` beyond it
- `componentHash` binds the on-chain integer to the off-chain breakdown JSON
- Emits `ScoreUpdated(agentTokenId, oldScore, newScore, componentHash)`

**`AuditTrail.sol`** — events only, zero `SSTORE`.
- `logAction(uint256 agentTokenId, string toolName, bytes32 argsHash, bytes32 resultHash)`
- Emits `ActionLogged(...)`. Cheapest possible audit surface.

### 2. Chain layer — `backend/chain/`

**`networks.py`** — target registry.
```
LOCAL         chain_id 31337  in-process py-evm    explorer: none
MONAD_TESTNET chain_id 10143  https://testnet-rpc.monad.xyz  explorer: testnet.monadexplorer.com
```
Selected by `CHAIN_TARGET` env (default `local`). Explorer URL templates for tx/address.

**`compiler.py`** — compiles `contracts/src/*.sol` via `solcx` (0.8.24), caches artifacts
(`abi` + `bin` + source hash) to `contracts/out/<Name>.json`. Recompiles only when source changes.

**`provider.py`** — one interface, two backends.
- `LocalEvmProvider` — `web3.EthereumTesterProvider` over py-evm. Funded accounts, instant blocks.
- `RpcProvider` — `HTTPProvider` + local `eth_account` signing, nonce management, EIP-1559 fees,
  exponential-backoff retry on transient RPC errors.

Both expose: `w3`, `sender_address`, `send(fn_call) -> receipt`, `chain_id`.

**`client.py`** — `ChainClient`, the only thing the app imports.
- `record_proof(task_id, agent_token_id, result_hash) -> {tx_hash, block_number, status}`
- `get_proof(task_id)`, `mint_passport(...)`, `update_score(...)`, `log_action(...)`
- Translates `task_id` strings → `bytes32` via keccak, hex hashes → `bytes32`
- Distinguishes **already-recorded revert** (benign, idempotent) from real failures

**`registry.py`** — reads/writes `backend/deployments/{chain_id}.json`. Same schema as today, so
the existing `/api/economy/chain` endpoint keeps working — it just serves real addresses now.

### 3. Durable outbox — `proof_outbox` table (PRD §5.4)

Chain submission must never block or break a goal run.

```sql
proof_outbox(
  task_id TEXT PRIMARY KEY, goal_id, agent_role, result_hash,
  status TEXT,          -- pending | submitting | submitted | confirmed | failed | dead_lettered
  attempts INTEGER, chain_id INTEGER,
  tx_hash TEXT, block_number INTEGER, last_error TEXT,
  created_at, updated_at
)
```

Flow: `economy.record_proof` mints the local proof (unchanged, instant) **and** enqueues an outbox
row. A `chain_submit_loop` in the worker drains `pending`, submits, and advances status. Retries
with exponential backoff; `dead_lettered` after 10 attempts. Restart-resumable — rows survive.

### 4. Events

New SSE events on the existing `economy` channel: `proof_pending`, `proof_submitted`,
`proof_confirmed`, `proof_failed`. The Proof Ledger shows a proof's lifecycle rather than a
single static row.

### 5. Verification — the credibility feature

`GET /api/economy/verify/{task_id}`:
1. Load the task's stored `output` from SQLite
2. Recompute `result_hash = sha256(canonical_json(output))`
3. Read `ProofOfWork.getProof(keccak(task_id))` from chain
4. Compare, and return every intermediate value so the check is auditable by hand

```json
{"task_id":"...","verified":true,"computed_hash":"...","onchain_hash":"...",
 "tx_hash":"0x...","block_number":42,"chain_id":10143,"explorer_url":"https://..."}
```

Any observer can redo step 2 themselves. This is the concrete answer to PRD Problem 1.

### 6. Self-heal enhancement (audited 2026-08-12)

Current state: mechanism works, showcase does not. `error_classifier` + `self_heal.trigger` are
wired into `worker._handle_goal_failure`, but there are **no tests**, no dedup (N failures → N
identical GitHub issues), no recursion guard (a failing fix-goal files another issue → loop), no
persistence, **no API or UI surface at all**, and it silently no-ops without `GITHUB_TOKEN`.

Additions:
- **`heal_attempts` table** — full history: fingerprint, error, classification, issue, fix goal, outcome.
- **Fingerprint dedup** — `sha256(normalized_error)`; a repeat within the dedup window links to the
  existing attempt instead of filing again. Recurrence count is itself a signal worth showing.
- **Recursion guard** — goals spawned by self-heal carry `source='self_heal'` + `heal_depth`.
  Depth ≥ 1 never triggers another heal. Hard stop on the loop.
- **Offline/simulated mode** — with no `GITHUB_TOKEN`, record a `simulated` attempt with the issue
  body it *would* have filed. The flow stays fully demoable with zero credentials.
- **Outcome tracking** — attempts settle to `fixed` / `failed` / `abandoned` when the fix goal ends.
- **API** `/api/heal/attempts`, `/api/heal/stats`; **UI** `/app/heal` timeline.
- **Tests** for the classifier, dedup, recursion guard, and offline mode.

---

## Error handling

- Chain unreachable → outbox rows stay `pending`, retried; goals complete normally.
- `ProofAlreadyRecorded` revert → treated as success (idempotent by design).
- Contract compile failure → startup logs a clear error; app runs with chain disabled.
- No deployment for the active chain → chain features report `not_deployed`, app still runs.
- `record_proof` retains its "never raise into the worker" contract.

## Testing

- **Contracts** (`test_contracts.py`) — deploy each to py-evm; assert soulbound revert, proof
  idempotency revert, 20% delta guard revert, audit event emission, role enforcement.
- **Chain client** (`test_chain_client.py`) — record → receipt → event decode → read-back;
  duplicate handled benignly; hash conversions round-trip.
- **Outbox** (`test_proof_outbox.py`) — enqueue, status transitions, retry/backoff, dead-letter,
  restart resumability.
- **Verification** (`test_verify.py`) — matching output verifies; tampered output fails.
- **Self-heal** (`test_self_heal.py`, `test_error_classifier.py`) — classification table, dedup,
  recursion guard, offline mode.
- All run with no network and no keys. Existing 38 tests must stay green.

## Update protocol (per repo CLAUDE.md)

On completion update `CLAUDE.md` (chain package, contracts, outbox, new endpoints, self-heal) and
append a dated session block to `progress.md`.
