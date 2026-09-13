# Mergit Showcase Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the working omniBox multi-agent engine to **Mergit** and layer a simulated Monad agent-economy (passports, live reputation, proof-of-work ledger, leaderboard) computed from real task runs, so it can be showcased to gauge preference for the Mergit vision.

**Architecture:** Keep the real orchestrator→DAG→agent engine untouched. Add one backend module (`economy.py`) + three SQLite tables + one API router + a global SSE channel. A worker hook records a proof and recomputes reputation on every completed task. Frontend gains an Economy hub (Leaderboard / Passports / Proof Ledger), an agent-detail page, a mock wallet button, and a full visual rebrand. A scripted replay mode is the safety net.

**Tech Stack:** Python 3 / FastAPI / aiosqlite (backend); React + TypeScript + Vite + Tailwind + Framer Motion + SWR (frontend); sse-starlette for streaming.

## Global Constraints

- **No git operations by the assistant.** The user runs all `git add`/`commit`/`push`. Every task ends at a **CHECKPOINT** — stop and tell the user it is ready to commit. Do NOT run git.
- Backend venv is at `backend/.venv/`; always use `backend/.venv/bin/python`.
- Persistence stays SQLite/aiosqlite — no Postgres/Redis.
- Economy is **deterministic** — no `random`/RNG. Scores derive from real `tasks` history.
- `economy.record_proof` must NEVER raise into the worker — wrap all its effects so a failure cannot break a real task run.
- Six agent roles exactly: `orchestrator`, `researcher`, `writer`, `coder`, `integrator`, `notifier`.
- Simulated chain only: mock tx hashes/blocks/addresses/contracts. No real Monad calls. Monad testnet chain id is `10143`.
- Reputation composite range `0..1000`; badge tiers Gold ≥ 800, Silver ≥ 600, else Bronze.
- No "omniBox" string may remain visible in shipped UI after Task 12.
- Run backend tests with: `cd backend && .venv/bin/python -m pytest <file> -v`.

---

## File Structure

**Backend (create):**
- `backend/economy.py` — passports/reputation/proofs logic + `record_proof` orchestration
- `backend/api/economy.py` — economy REST + SSE router
- `backend/deployments/10143.json` — mock Monad contract addresses
- `backend/test_economy.py` — unit tests for hashing + reputation math + idempotency
- `backend/scripts/replay_demo.py` — deterministic offline demo run

**Backend (modify):**
- `backend/db.py` — add 3 tables to `SCHEMA`; add economy accessors; seed+backfill in `init_db`
- `backend/worker.py` — call `economy.record_proof` in `_after_task_done`
- `backend/main.py` — register `economy` router

**Frontend (create):**
- `frontend/src/pages/Economy.tsx` — tabbed hub (Leaderboard / Passports / Proof Ledger)
- `frontend/src/pages/AgentDetail.tsx` — passport + score breakdown + proofs
- `frontend/src/components/economy/Leaderboard.tsx`
- `frontend/src/components/economy/PassportCard.tsx`
- `frontend/src/components/economy/ProofLedger.tsx`
- `frontend/src/components/WalletConnect.tsx` — mock Monad wallet

**Frontend (modify):**
- `frontend/src/lib/api.ts` — economy fetchers
- `frontend/src/App.tsx` — economy routes
- `frontend/src/components/AppNav.tsx` — Economy link + wallet button
- `frontend/src/components/ProtectedRoute.tsx` — `VITE_DEMO_MODE` bypass
- `frontend/src/pages/Landing.tsx` + `frontend/src/components/landing/*` — rebrand
- Global brand: `index.html`, wordmark/logo usages, color tokens

**Docs (modify):** `CLAUDE.md`, `progress.md`, `pitch/DEMO_VIDEO_SCRIPT.md`

---

### Task 1: Economy DB schema + accessors

**Files:**
- Modify: `backend/db.py` (append to `SCHEMA` string; add accessor functions)
- Test: `backend/test_economy_db.py`

**Interfaces:**
- Produces:
  - `async def upsert_passport(role, did, token_id, soulbound, capabilities: list[str], owner_address, minted_at: int, mint_block: int) -> None`
  - `async def get_passport(role) -> dict | None`
  - `async def list_passports() -> list[dict]`
  - `async def upsert_reputation(role, composite: int, success_rate: float, speed: float, volume: float, badge: str, updated_at: int) -> None`
  - `async def get_reputation(role) -> dict | None`
  - `async def list_reputation() -> list[dict]`
  - `async def insert_proof(task_id, goal_id, agent_role, result_hash, tx_hash, block_number: int, recorded_at: int) -> bool` (returns False if task_id already had a proof — idempotent)
  - `async def get_proof(task_id) -> dict | None`
  - `async def list_proofs(limit: int = 50, before_block: int | None = None) -> list[dict]` (newest first)
  - `async def list_proofs_for_role(role, limit: int = 20) -> list[dict]`
  - `async def max_proof_block() -> int` (0 if none)
  - `async def list_completed_tasks_by_role() -> dict[str, dict]` — per role: `{done, failed, avg_duration_sec, completed_task_rows: list[{id, goal_id, output, created_at, updated_at}]}` derived from `tasks`

- [ ] **Step 1: Add tables to SCHEMA**

In `backend/db.py`, append inside the `SCHEMA` triple-quoted string (after the `tool_calls` block, before the closing `"""`):

```sql

CREATE TABLE IF NOT EXISTS agent_passports (
    role            TEXT PRIMARY KEY,
    did             TEXT NOT NULL,
    token_id        INTEGER NOT NULL,
    soulbound       INTEGER NOT NULL DEFAULT 1,
    capabilities    TEXT NOT NULL DEFAULT '[]',
    owner_address   TEXT NOT NULL,
    minted_at       INTEGER NOT NULL,
    mint_block      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_reputation (
    role            TEXT PRIMARY KEY,
    composite       INTEGER NOT NULL DEFAULT 0,
    success_rate    REAL NOT NULL DEFAULT 0,
    speed           REAL NOT NULL DEFAULT 0,
    volume          REAL NOT NULL DEFAULT 0,
    badge           TEXT NOT NULL DEFAULT 'Bronze',
    updated_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS proofs (
    task_id         TEXT PRIMARY KEY,
    goal_id         TEXT NOT NULL,
    agent_role      TEXT NOT NULL,
    result_hash     TEXT NOT NULL,
    tx_hash         TEXT NOT NULL,
    block_number    INTEGER NOT NULL,
    recorded_at     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proofs_block ON proofs(block_number DESC);
CREATE INDEX IF NOT EXISTS idx_proofs_role ON proofs(agent_role);
```

- [ ] **Step 2: Write the failing test**

Create `backend/test_economy_db.py`:

```python
import asyncio
import os
import tempfile

import pytest


@pytest.fixture()
def fresh_db(monkeypatch):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "test.db")
    import config
    monkeypatch.setattr(config.settings, "db_path", path)
    import importlib
    import db as _db
    importlib.reload(_db)
    asyncio.get_event_loop().run_until_complete(_db.init_db())
    return _db


def test_passport_roundtrip(fresh_db):
    db = fresh_db
    async def go():
        await db.upsert_passport("coder", "did:mergit:agent:coder", 3, 1,
                                 ["code_exec", "file_ops"], "0xabc", 1000, 42)
        p = await db.get_passport("coder")
        assert p["role"] == "coder"
        assert p["token_id"] == 3
        assert p["capabilities"] == ["code_exec", "file_ops"]
    asyncio.get_event_loop().run_until_complete(go())


def test_proof_idempotent(fresh_db):
    db = fresh_db
    async def go():
        first = await db.insert_proof("t1", "g1", "coder", "hh", "0xtx", 100, 111)
        second = await db.insert_proof("t1", "g1", "coder", "hh", "0xtx", 100, 111)
        assert first is True
        assert second is False
        assert await db.max_proof_block() == 100
    asyncio.get_event_loop().run_until_complete(go())
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest test_economy_db.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'upsert_passport'`

- [ ] **Step 4: Implement the accessors**

Add to `backend/db.py` (end of file). Follow the existing `get_conn()` / `_now()` patterns already in the file:

```python
import json as _json  # already imported at top as `json`; reuse existing `json`


async def upsert_passport(role, did, token_id, soulbound, capabilities, owner_address, minted_at, mint_block):
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO agent_passports
               (role, did, token_id, soulbound, capabilities, owner_address, minted_at, mint_block)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(role) DO UPDATE SET
                 did=excluded.did, token_id=excluded.token_id, soulbound=excluded.soulbound,
                 capabilities=excluded.capabilities, owner_address=excluded.owner_address,
                 minted_at=excluded.minted_at, mint_block=excluded.mint_block""",
            (role, did, token_id, 1 if soulbound else 0, json.dumps(capabilities),
             owner_address, minted_at, mint_block),
        )
        await conn.commit()


def _passport_row(row):
    return {
        "role": row["role"], "did": row["did"], "token_id": row["token_id"],
        "soulbound": bool(row["soulbound"]), "capabilities": json.loads(row["capabilities"]),
        "owner_address": row["owner_address"], "minted_at": row["minted_at"],
        "mint_block": row["mint_block"],
    }


async def get_passport(role):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM agent_passports WHERE role=?", (role,))
        row = await cur.fetchone()
        return _passport_row(row) if row else None


async def list_passports():
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM agent_passports ORDER BY token_id")
        return [_passport_row(r) for r in await cur.fetchall()]


async def upsert_reputation(role, composite, success_rate, speed, volume, badge, updated_at):
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO agent_reputation
               (role, composite, success_rate, speed, volume, badge, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(role) DO UPDATE SET
                 composite=excluded.composite, success_rate=excluded.success_rate,
                 speed=excluded.speed, volume=excluded.volume, badge=excluded.badge,
                 updated_at=excluded.updated_at""",
            (role, composite, success_rate, speed, volume, badge, updated_at),
        )
        await conn.commit()


def _rep_row(row):
    return {
        "role": row["role"], "composite": row["composite"], "success_rate": row["success_rate"],
        "speed": row["speed"], "volume": row["volume"], "badge": row["badge"],
        "updated_at": row["updated_at"],
    }


async def get_reputation(role):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM agent_reputation WHERE role=?", (role,))
        row = await cur.fetchone()
        return _rep_row(row) if row else None


async def list_reputation():
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM agent_reputation ORDER BY composite DESC")
        return [_rep_row(r) for r in await cur.fetchall()]


def _proof_row(row):
    return {
        "task_id": row["task_id"], "goal_id": row["goal_id"], "agent_role": row["agent_role"],
        "result_hash": row["result_hash"], "tx_hash": row["tx_hash"],
        "block_number": row["block_number"], "recorded_at": row["recorded_at"],
    }


async def insert_proof(task_id, goal_id, agent_role, result_hash, tx_hash, block_number, recorded_at):
    async with get_conn() as conn:
        try:
            await conn.execute(
                """INSERT INTO proofs
                   (task_id, goal_id, agent_role, result_hash, tx_hash, block_number, recorded_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (task_id, goal_id, agent_role, result_hash, tx_hash, block_number, recorded_at),
            )
            await conn.commit()
            return True
        except Exception:
            return False


async def get_proof(task_id):
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM proofs WHERE task_id=?", (task_id,))
        row = await cur.fetchone()
        return _proof_row(row) if row else None


async def list_proofs(limit=50, before_block=None):
    async with get_conn() as conn:
        if before_block is not None:
            cur = await conn.execute(
                "SELECT * FROM proofs WHERE block_number < ? ORDER BY block_number DESC LIMIT ?",
                (before_block, limit))
        else:
            cur = await conn.execute(
                "SELECT * FROM proofs ORDER BY block_number DESC LIMIT ?", (limit,))
        return [_proof_row(r) for r in await cur.fetchall()]


async def list_proofs_for_role(role, limit=20):
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM proofs WHERE agent_role=? ORDER BY block_number DESC LIMIT ?",
            (role, limit))
        return [_proof_row(r) for r in await cur.fetchall()]


async def max_proof_block():
    async with get_conn() as conn:
        cur = await conn.execute("SELECT COALESCE(MAX(block_number), 0) AS m FROM proofs")
        row = await cur.fetchone()
        return row["m"]


async def list_completed_tasks_by_role():
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT id, goal_id, agent_name, status, output, created_at, updated_at FROM tasks")
        rows = await cur.fetchall()
    agg: dict[str, dict] = {}
    for r in rows:
        role = r["agent_name"]
        a = agg.setdefault(role, {"done": 0, "failed": 0, "_durations": [], "completed_task_rows": []})
        if r["status"] == "DONE":
            a["done"] += 1
            dur = max(1, (r["updated_at"] or r["created_at"]) - r["created_at"])
            a["_durations"].append(dur)
            a["completed_task_rows"].append({
                "id": r["id"], "goal_id": r["goal_id"],
                "output": json.loads(r["output"]) if r["output"] else {},
                "created_at": r["created_at"], "updated_at": r["updated_at"],
            })
        elif r["status"] == "FAILED":
            a["failed"] += 1
    for role, a in agg.items():
        durs = a.pop("_durations")
        a["avg_duration_sec"] = (sum(durs) / len(durs)) if durs else 0.0
    return agg
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest test_economy_db.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: CHECKPOINT** — stop; tell the user Task 1 is ready to commit (files: `backend/db.py`, `backend/test_economy_db.py`).

---

### Task 2: Economy pure logic — hashing + reputation math

**Files:**
- Create: `backend/economy.py` (logic functions only in this task)
- Test: `backend/test_economy.py`

**Interfaces:**
- Produces:
  - `ROLES: list[str]` = `["orchestrator", "researcher", "writer", "coder", "integrator", "notifier"]`
  - `CAPABILITIES: dict[str, list[str]]` — per role, from `agent_registry.AGENT_REGISTRY[role]["allowed_tools"]`; orchestrator → `["decompose_goal", "plan_task_dag", "route_agents"]`
  - `def canonical_json(obj) -> str`
  - `def result_hash(output: dict) -> str` (sha256 hex)
  - `def tx_hash(task_id: str, result_hash: str) -> str` (`0x` + 64 hex)
  - `def owner_address(role: str) -> str` (`0x` + 40 hex)
  - `def did_for(role: str) -> str`
  - `def compute_scores(done: int, failed: int, avg_duration_sec: float) -> dict` → `{success_rate, speed, volume, composite}` where composite is int 0..1000
  - `def badge_for(composite: int) -> str`
  - `def apply_delta_cap(prev_composite: int, new_composite: int) -> int` — clamp to ±20% of prev when prev>0

- [ ] **Step 1: Write the failing test**

Create `backend/test_economy.py`:

```python
import economy


def test_result_hash_stable():
    a = economy.result_hash({"b": 1, "a": 2})
    b = economy.result_hash({"a": 2, "b": 1})
    assert a == b
    assert len(a) == 64


def test_tx_hash_format():
    h = economy.result_hash({"x": 1})
    tx = economy.tx_hash("task-123", h)
    assert tx.startswith("0x")
    assert len(tx) == 66


def test_owner_address_deterministic():
    assert economy.owner_address("coder") == economy.owner_address("coder")
    assert economy.owner_address("coder").startswith("0x")
    assert len(economy.owner_address("coder")) == 42


def test_compute_scores_bounds_and_badge():
    s = economy.compute_scores(done=40, failed=0, avg_duration_sec=5.0)
    assert 0 <= s["composite"] <= 1000
    assert s["success_rate"] == 1.0
    assert economy.badge_for(850) == "Gold"
    assert economy.badge_for(650) == "Silver"
    assert economy.badge_for(100) == "Bronze"


def test_compute_scores_no_history_is_neutral():
    s = economy.compute_scores(done=0, failed=0, avg_duration_sec=0.0)
    assert 0 <= s["composite"] <= 1000


def test_delta_cap():
    assert economy.apply_delta_cap(500, 1000) == 600   # +20% max
    assert economy.apply_delta_cap(500, 100) == 400    # -20% max
    assert economy.apply_delta_cap(0, 800) == 800      # no cap when prev==0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest test_economy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'economy'`

- [ ] **Step 3: Implement `backend/economy.py` logic**

```python
"""Simulated Monad agent-economy: passports, reputation, proof-of-work.

Deterministic — no RNG. Scores derive from real task history. This module never
raises into the worker: record_proof (Task 3) swallows its own errors.
"""
import hashlib
import json
import math
import time

import agent_registry

ROLES = ["orchestrator", "researcher", "writer", "coder", "integrator", "notifier"]

_ORCH_CAPS = ["decompose_goal", "plan_task_dag", "route_agents"]

CAPABILITIES = {
    role: (_ORCH_CAPS if role == "orchestrator"
           else agent_registry.AGENT_REGISTRY.get(role, {}).get("allowed_tools", []))
    for role in ROLES
}

# Score weights and baselines
_W_SUCCESS = 0.5
_W_SPEED = 0.2
_W_VOLUME = 0.3
_BASELINE_SEC = 20.0           # a task at/under this is "fast"
_VOLUME_SATURATION = 50.0      # tasks needed to max the volume component
_MINT_BASE_BLOCK = 18_000_000
_PROOF_BASE_BLOCK = 18_100_000


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def result_hash(output) -> str:
    return hashlib.sha256(canonical_json(output).encode()).hexdigest()


def tx_hash(task_id: str, rhash: str) -> str:
    return "0x" + hashlib.sha256((task_id + rhash).encode()).hexdigest()[:64]


def owner_address(role: str) -> str:
    return "0x" + hashlib.sha256(role.encode()).hexdigest()[:40]


def did_for(role: str) -> str:
    return f"did:mergit:agent:{role}"


def mint_block_for(role: str) -> int:
    return _MINT_BASE_BLOCK + ROLES.index(role)


def compute_scores(done: int, failed: int, avg_duration_sec: float) -> dict:
    total = done + failed
    success_rate = (done / total) if total else 0.75  # neutral prior
    if avg_duration_sec <= 0:
        speed = 0.6
    else:
        speed = max(0.0, min(1.0, _BASELINE_SEC / avg_duration_sec))
    volume = min(1.0, math.log10(done + 1) / math.log10(_VOLUME_SATURATION + 1)) if done else 0.0
    raw = _W_SUCCESS * success_rate + _W_SPEED * speed + _W_VOLUME * volume
    composite = int(round(1000 * raw))
    composite = max(0, min(1000, composite))
    return {"success_rate": round(success_rate, 4), "speed": round(speed, 4),
            "volume": round(volume, 4), "composite": composite}


def badge_for(composite: int) -> str:
    if composite >= 800:
        return "Gold"
    if composite >= 600:
        return "Silver"
    return "Bronze"


def apply_delta_cap(prev_composite: int, new_composite: int) -> int:
    if prev_composite <= 0:
        return new_composite
    lo = int(prev_composite * 0.8)
    hi = int(prev_composite * 1.2)
    return max(lo, min(hi, new_composite))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest test_economy.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: CHECKPOINT** — tell the user Task 2 is ready to commit (`backend/economy.py`, `backend/test_economy.py`).

---

### Task 3: Economy orchestration — seed, backfill, record_proof

**Files:**
- Modify: `backend/economy.py` (add async orchestration functions)
- Modify: `backend/db.py` — nothing new; uses Task 1 accessors
- Test: `backend/test_economy_flow.py`

**Interfaces:**
- Consumes: all Task 1 db accessors; all Task 2 logic; `events.emit`
- Produces:
  - `async def seed_passports() -> None` — upsert a passport for every role (idempotent)
  - `async def recompute_role(role: str) -> dict` — recompute+persist reputation for role from history, returns rep dict
  - `async def backfill() -> None` — if `proofs` empty, create proofs for all historical DONE tasks and recompute all roles
  - `async def record_proof(task, output: dict) -> dict | None` — mint proof for a completed task (idempotent), recompute the role, emit `proof_recorded` + `reputation_update` on the `"economy"` SSE channel; returns the proof dict or None
  - `ECONOMY_CHANNEL = "economy"`

- [ ] **Step 1: Write the failing test**

Create `backend/test_economy_flow.py`:

```python
import asyncio
import os
import tempfile
import types

import pytest


@pytest.fixture()
def env(monkeypatch):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "test.db")
    import config
    monkeypatch.setattr(config.settings, "db_path", path)
    import importlib
    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)
    asyncio.get_event_loop().run_until_complete(_db.init_db())
    return _db, _ec


def test_seed_passports_creates_all_roles(env):
    db, ec = env
    async def go():
        await ec.seed_passports()
        ps = await db.list_passports()
        roles = {p["role"] for p in ps}
        assert roles == set(ec.ROLES)
    asyncio.get_event_loop().run_until_complete(go())


def test_record_proof_idempotent_and_updates_rep(env):
    db, ec = env
    async def go():
        await ec.seed_passports()
        task = types.SimpleNamespace(id="tX", goal_id="gX", agent_name="coder")
        p1 = await ec.record_proof(task, {"result": "ok"})
        p2 = await ec.record_proof(task, {"result": "ok"})
        assert p1 is not None
        assert p2 is None  # idempotent — already minted
        rep = await db.get_reputation("coder")
        assert rep is not None
        assert 0 <= rep["composite"] <= 1000
        proofs = await db.list_proofs_for_role("coder")
        assert len(proofs) == 1
    asyncio.get_event_loop().run_until_complete(go())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest test_economy_flow.py -v`
Expected: FAIL — `AttributeError: module 'economy' has no attribute 'seed_passports'`

- [ ] **Step 3: Implement orchestration in `backend/economy.py`**

Append to `backend/economy.py`:

```python
import logging

import db
import events

logger = logging.getLogger(__name__)

ECONOMY_CHANNEL = "economy"


async def seed_passports() -> None:
    now = int(time.time())
    for idx, role in enumerate(ROLES, start=1):
        existing = await db.get_passport(role)
        if existing:
            continue
        await db.upsert_passport(
            role=role, did=did_for(role), token_id=idx, soulbound=True,
            capabilities=CAPABILITIES.get(role, []), owner_address=owner_address(role),
            minted_at=now, mint_block=mint_block_for(role),
        )


async def recompute_role(role: str) -> dict:
    agg = (await db.list_completed_tasks_by_role()).get(
        role, {"done": 0, "failed": 0, "avg_duration_sec": 0.0})
    scores = compute_scores(agg["done"], agg["failed"], agg["avg_duration_sec"])
    prev = await db.get_reputation(role)
    composite = apply_delta_cap(prev["composite"] if prev else 0, scores["composite"])
    badge = badge_for(composite)
    await db.upsert_reputation(role, composite, scores["success_rate"], scores["speed"],
                               scores["volume"], badge, int(time.time()))
    return {"role": role, "composite": composite, "badge": badge, **scores}


async def _next_block() -> int:
    top = await db.max_proof_block()
    base = max(top, _PROOF_BASE_BLOCK - 1)
    return base + 1


async def record_proof(task, output) -> dict | None:
    """Mint a proof for a completed task and refresh its agent's reputation.
    Never raises — logs and returns None on any failure."""
    try:
        role = task.agent_name
        if role not in ROLES:
            return None
        if await db.get_proof(task.id):
            return None  # idempotent
        rhash = result_hash(output or {})
        tx = tx_hash(task.id, rhash)
        block = await _next_block()
        now = int(time.time())
        inserted = await db.insert_proof(task.id, task.goal_id, role, rhash, tx, block, now)
        if not inserted:
            return None
        proof = {"task_id": task.id, "goal_id": task.goal_id, "agent_role": role,
                 "result_hash": rhash, "tx_hash": tx, "block_number": block, "recorded_at": now}
        rep = await recompute_role(role)
        events.emit(ECONOMY_CHANNEL, "proof_recorded", dict(proof))
        events.emit(ECONOMY_CHANNEL, "reputation_update", dict(rep))
        return proof
    except Exception as e:  # never break the worker
        logger.warning("economy.record_proof failed for task %s: %s", getattr(task, "id", "?"), e)
        return None


async def backfill() -> None:
    """One-time: mint proofs for historical DONE tasks so pages are populated."""
    if await db.max_proof_block() > 0:
        return
    by_role = await db.list_completed_tasks_by_role()
    block = _PROOF_BASE_BLOCK
    for role, agg in by_role.items():
        if role not in ROLES:
            continue
        for row in sorted(agg["completed_task_rows"], key=lambda r: r["created_at"]):
            rhash = result_hash(row["output"])
            tx = tx_hash(row["id"], rhash)
            block += 1
            await db.insert_proof(row["id"], row["goal_id"], role, rhash, tx, block,
                                  row["updated_at"] or row["created_at"])
    for role in ROLES:
        await recompute_role(role)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest test_economy_flow.py test_economy.py test_economy_db.py -v`
Expected: PASS (all)

- [ ] **Step 5: Wire seed+backfill into init**

In `backend/db.py`, `init_db()` currently ends at `await conn.executescript(SCHEMA)`. Leave `db.py` as-is and instead call the economy seed from `main.py` lifespan (Task 5 registers the router; seeding belongs with startup). Add to `backend/main.py` lifespan startup, AFTER `await db.init_db()`:

```python
    import economy
    await economy.seed_passports()
    await economy.backfill()
```

(Locate the existing `await db.init_db()` call inside the lifespan `asynccontextmanager` in `main.py` and add the three lines directly after it.)

- [ ] **Step 6: CHECKPOINT** — tell the user Task 3 is ready to commit (`backend/economy.py`, `backend/main.py`, `backend/test_economy_flow.py`).

---

### Task 4: Worker hook — mint proof on task completion

**Files:**
- Modify: `backend/worker.py` (`_after_task_done`)

**Interfaces:**
- Consumes: `economy.record_proof(task, output)`

- [ ] **Step 1: Import economy in worker**

In `backend/worker.py`, add to the import block (near `import events`):

```python
import economy
```

- [ ] **Step 2: Call record_proof after task DONE**

In `backend/worker.py`, `_after_task_done(self...)` begins:

```python
async def _after_task_done(task: Any, output: dict) -> None:
    goal = await db.get_goal(task.goal_id)
    if not goal:
        return
```

Insert immediately after the `if not goal: return` block:

```python
    # Simulated on-chain proof-of-work + reputation update (never breaks the run)
    await economy.record_proof(task, output)
```

- [ ] **Step 3: Manual verification**

Run: `cd backend && .venv/bin/python -c "import worker, economy; print('import ok')"`
Expected: prints `import ok` (no import cycle).

- [ ] **Step 4: CHECKPOINT** — tell the user Task 4 is ready to commit (`backend/worker.py`). Note: end-to-end proof emission is verified in Task 11.

---

### Task 5: Economy API router + mock chain file

**Files:**
- Create: `backend/api/economy.py`
- Create: `backend/deployments/10143.json`
- Modify: `backend/main.py` (register router)
- Test: `backend/test_economy_api.py`

**Interfaces:**
- Consumes: Task 1 db accessors; `events.subscribe/unsubscribe`; `economy.ECONOMY_CHANNEL`
- Produces routes: `GET /api/economy/passports|leaderboard|proofs|agents/{role}|chain|stream`

- [ ] **Step 1: Create mock chain deployments file**

Create `backend/deployments/10143.json`:

```json
{
  "chainId": 10143,
  "network": "Monad Testnet",
  "explorer": "https://testnet.monadexplorer.com",
  "contracts": {
    "AgentPassport": "0x5f2e4a9c1b7d3e08f6a2c9b1d4e7f0a3c6b9d2e5",
    "ProofOfWork": "0x8a1c4d7e0b3f6a9c2d5e8b1f4a7d0c3e6b9f2a5d",
    "ReputationRegistry": "0xd3e6b9f2a5c8d1e4b7f0a3c6d9e2b5f8a1c4d7e0",
    "AuditTrail": "0xa7d0c3e6b9f2a5d8c1e4b7f0a3c6d9e2b5f8a1c4"
  }
}
```

- [ ] **Step 2: Write the failing test**

Create `backend/test_economy_api.py`:

```python
import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("config.settings.db_path", os.path.join(tmp, "t.db"))
    import importlib
    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)
    from api import economy as _api
    importlib.reload(_api)
    asyncio.get_event_loop().run_until_complete(_db.init_db())
    asyncio.get_event_loop().run_until_complete(_ec.seed_passports())
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(_api.router)
    return TestClient(app)


def test_passports_endpoint(client):
    r = client.get("/api/economy/passports")
    assert r.status_code == 200
    assert len(r.json()) == 6


def test_leaderboard_endpoint(client):
    r = client.get("/api/economy/leaderboard")
    assert r.status_code == 200


def test_chain_endpoint(client):
    r = client.get("/api/economy/chain")
    assert r.json()["chainId"] == 10143
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest test_economy_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.economy'`

- [ ] **Step 4: Implement `backend/api/economy.py`**

```python
import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

import db
import economy
import events

router = APIRouter(prefix="/api/economy", tags=["economy"])

_CHAIN_FILE = Path(__file__).resolve().parent.parent / "deployments" / "10143.json"


@router.get("/passports")
async def passports():
    return await db.list_passports()


@router.get("/leaderboard")
async def leaderboard():
    reps = await db.list_reputation()
    passports_by_role = {p["role"]: p for p in await db.list_passports()}
    out = []
    for rank, rep in enumerate(reps, start=1):
        p = passports_by_role.get(rep["role"], {})
        out.append({**rep, "rank": rank, "token_id": p.get("token_id"),
                    "did": p.get("did")})
    return out


@router.get("/proofs")
async def proofs(limit: int = 50, before: int | None = None):
    return await db.list_proofs(limit=limit, before_block=before)


@router.get("/agents/{role}")
async def agent_detail(role: str):
    passport = await db.get_passport(role)
    if not passport:
        raise HTTPException(status_code=404, detail="Unknown agent")
    rep = await db.get_reputation(role)
    role_proofs = await db.list_proofs_for_role(role, limit=25)
    return {"passport": passport, "reputation": rep, "proofs": role_proofs}


@router.get("/chain")
async def chain():
    return json.loads(_CHAIN_FILE.read_text())


@router.get("/stream")
async def stream():
    q = events.subscribe(economy.ECONOMY_CHANNEL)

    async def generator():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=30)
                    yield {"event": item["event"], "data": json.dumps(item["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            events.unsubscribe(economy.ECONOMY_CHANNEL, q)

    return EventSourceResponse(generator())
```

- [ ] **Step 5: Register the router in `main.py`**

In `backend/main.py` line 14, add `economy` to the `from api import ...` list (it will collide with the top-level `economy` module name — import the API module with an alias). Change the import line to add:

```python
from api import economy as economy_api
```

(Add as a separate import line below the existing `from api import ...` line to avoid shadowing the top-level `economy` module.) Then near the other `app.include_router(...)` calls add:

```python
app.include_router(economy_api.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest test_economy_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: CHECKPOINT** — tell the user Task 5 is ready to commit (`backend/api/economy.py`, `backend/deployments/10143.json`, `backend/main.py`, `backend/test_economy_api.py`).

---

### Task 6: Frontend economy API + SSE client

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces (TypeScript):
  - types `Passport`, `RepEntry`, `Proof`, `AgentDetail`, `ChainInfo`
  - `getPassports(): Promise<Passport[]>`
  - `getLeaderboard(): Promise<RepEntry[]>`
  - `getProofs(limit?, before?): Promise<Proof[]>`
  - `getAgentDetail(role): Promise<AgentDetail>`
  - `getChain(): Promise<ChainInfo>`

- [ ] **Step 1: Inspect the existing fetch pattern**

Read `frontend/src/lib/api.ts` to match its base-URL/fetch helper convention (e.g. an existing `api()` or `fetchJson()` wrapper). Reuse that helper — do not introduce a new fetch style.

- [ ] **Step 2: Add economy types + fetchers**

Append to `frontend/src/lib/api.ts` (adapt `<HELPER>` to the file's existing fetch helper found in Step 1):

```typescript
export interface Passport {
  role: string; did: string; token_id: number; soulbound: boolean;
  capabilities: string[]; owner_address: string; minted_at: number; mint_block: number;
}
export interface RepEntry {
  role: string; composite: number; success_rate: number; speed: number; volume: number;
  badge: string; updated_at: number; rank?: number; token_id?: number; did?: string;
}
export interface Proof {
  task_id: string; goal_id: string; agent_role: string; result_hash: string;
  tx_hash: string; block_number: number; recorded_at: number;
}
export interface AgentDetail { passport: Passport; reputation: RepEntry | null; proofs: Proof[]; }
export interface ChainInfo {
  chainId: number; network: string; explorer: string; contracts: Record<string, string>;
}

export const getPassports = () => <HELPER>("/api/economy/passports");
export const getLeaderboard = () => <HELPER>("/api/economy/leaderboard");
export const getProofs = (limit = 50, before?: number) =>
  <HELPER>(`/api/economy/proofs?limit=${limit}${before ? `&before=${before}` : ""}`);
export const getAgentDetail = (role: string) => <HELPER>(`/api/economy/agents/${role}`);
export const getChain = () => <HELPER>("/api/economy/chain");
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 4: CHECKPOINT** — tell the user Task 6 is ready to commit (`frontend/src/lib/api.ts`).

---

### Task 7: DEMO_MODE auth bypass

**Files:**
- Modify: `frontend/src/components/ProtectedRoute.tsx`
- Modify: `frontend/.env` (create if absent) — document `VITE_DEMO_MODE`

**Interfaces:**
- Behavior: when `import.meta.env.VITE_DEMO_MODE === "true"`, `ProtectedRoute` renders children without Firebase.

- [ ] **Step 1: Add the bypass**

In `frontend/src/components/ProtectedRoute.tsx`, at the very top of the component body (before the `useState`/`useEffect`), add:

```typescript
  if (import.meta.env.VITE_DEMO_MODE === "true") {
    return <>{children}</>;
  }
```

- [ ] **Step 2: Add env flag**

Create/append `frontend/.env`:

```
VITE_DEMO_MODE=true
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors. (Manual: with the flag set, visiting `/app` must not redirect to `/login` — confirmed in Task 11.)

- [ ] **Step 4: CHECKPOINT** — tell the user Task 7 is ready to commit (`frontend/src/components/ProtectedRoute.tsx`, `frontend/.env`).

---

### Task 8: Economy UI — Leaderboard, Passports, Proof Ledger, hub

**Files:**
- Create: `frontend/src/components/economy/Leaderboard.tsx`
- Create: `frontend/src/components/economy/PassportCard.tsx`
- Create: `frontend/src/components/economy/ProofLedger.tsx`
- Create: `frontend/src/pages/Economy.tsx`
- Create: `frontend/src/pages/AgentDetail.tsx`
- Modify: `frontend/src/App.tsx` (routes)
- Modify: `frontend/src/components/AppNav.tsx` (Economy link)

This task is build-and-verify (React UI), not TDD. **REQUIRED SUB-SKILL when executing this task: `frontend-design`** — apply it for the on-chain visual identity (see Task 12 for the palette/tokens; use them here too).

- [ ] **Step 1: Leaderboard component**

`frontend/src/components/economy/Leaderboard.tsx` — fetch `getLeaderboard()` via SWR (match existing SWR usage in the codebase), render ranked rows: rank, role, composite (mono numerals), badge chip (Gold/Silver/Bronze color), a thin score bar. Subscribe to the economy SSE stream (`useSSE("/api/economy/stream")` — reuse `frontend/src/lib/sse.ts`) and on `reputation_update` mutate the SWR cache so scores animate (Framer Motion `layout` + number transition).

- [ ] **Step 2: PassportCard + gallery**

`frontend/src/components/economy/PassportCard.tsx` — an NFT-style card: role name, `AgentPassport #{token_id}`, "SOULBOUND" tag, DID (mono, truncated), owner address (mono, truncated), capabilities as chips, mint block. Card has the on-chain gradient border. Export a `PassportGallery` that fetches `getPassports()` and grids the cards.

- [ ] **Step 3: ProofLedger component**

`frontend/src/components/economy/ProofLedger.tsx` — fetch initial `getProofs(50)`; subscribe to `/api/economy/stream`; on `proof_recorded`, prepend the new row with a Framer Motion enter animation + a brief highlight. Each row: block number (mono), agent role, `tx_hash` (truncated, mono), `result_hash` (truncated, mono), relative time. Header shows "Monad Testnet · chainId 10143" from `getChain()`.

- [ ] **Step 4: Economy hub page**

`frontend/src/pages/Economy.tsx` — renders `AppNav`, a page header ("Agent Economy"), and a tab switcher (local state) between **Leaderboard**, **Passports**, **Proof Ledger**. Match the layout/spacing conventions of `pages/Dashboard.tsx`.

- [ ] **Step 5: Agent detail page**

`frontend/src/pages/AgentDetail.tsx` — reads `:role` route param, fetches `getAgentDetail(role)`, shows the PassportCard, a score breakdown (success_rate / speed / volume bars + composite + badge), and that agent's recent proofs (reuse a compact ProofLedger row).

- [ ] **Step 6: Wire routes**

In `frontend/src/App.tsx`, add inside `<Routes>` (wrapped in `ProtectedRoute` like the others):

```tsx
        <Route path="/app/economy" element={<ProtectedRoute><Economy /></ProtectedRoute>} />
        <Route path="/app/economy/agents/:role" element={<ProtectedRoute><AgentDetail /></ProtectedRoute>} />
```

Add the imports:

```tsx
import { Economy } from "./pages/Economy";
import { AgentDetail } from "./pages/AgentDetail";
```

- [ ] **Step 7: Nav link**

In `frontend/src/components/AppNav.tsx`, add an "Economy" nav item (route `/app/economy`, a coin/trophy icon from the icon set already used) with the same active-route highlighting pattern as the existing links.

- [ ] **Step 8: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 0 TS errors, build succeeds.

- [ ] **Step 9: CHECKPOINT** — tell the user Task 8 is ready to commit (all files above).

---

### Task 9: Mock wallet connect

**Files:**
- Create: `frontend/src/components/WalletConnect.tsx`
- Modify: `frontend/src/components/AppNav.tsx` (mount the button)

- [ ] **Step 1: WalletConnect component**

`frontend/src/components/WalletConnect.tsx` — a button "Connect Wallet". On click, set local state to a deterministic fake Monad address (`0x` + a fixed/derived 40-hex string) and switch the label to the truncated address + a green "Monad Testnet" dot. No real wallet APIs. Persist the connected state in `localStorage` so it survives navigation.

- [ ] **Step 2: Mount in nav**

In `frontend/src/components/AppNav.tsx`, render `<WalletConnect />` at the right end of the nav bar.

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 0 TS errors, build succeeds.

- [ ] **Step 4: CHECKPOINT** — tell the user Task 9 is ready to commit.

---

### Task 10: Replay mode (offline demo safety net)

**Files:**
- Create: `backend/scripts/replay_demo.py`

**Interfaces:**
- CLI: `python backend/scripts/replay_demo.py` — inserts a canned goal + 3 DONE tasks (researcher→coder→integrator) into the DB and calls `economy.record_proof` for each with a short delay, so the ledger/leaderboard animate live without any LLM calls.

- [ ] **Step 1: Implement the script**

`backend/scripts/replay_demo.py`:

```python
"""Deterministic offline demo: seeds a goal + 3 completed tasks and mints their proofs
with a short delay so the Economy pages animate live — no LLM keys required.

Run from backend/:  .venv/bin/python scripts/replay_demo.py
"""
import asyncio
import sys
import time
import types
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import economy  # noqa: E402
from state import GoalStatus, TaskStatus  # noqa: E402


CANNED = [
    ("researcher", {"summary": "Located the null-pointer in auth.py:88", "key_points": ["bug in token refresh"], "sources": ["auth.py"]}),
    ("coder", {"text": "Patched auth.py to guard None token", "title": "Fix"}),
    ("integrator", {"pr_url": "https://github.com/mergit-io/demo/pull/42", "comment": "PR opened"}),
]


async def main():
    await db.init_db()
    await economy.seed_passports()
    gid = "replay_" + uuid.uuid4().hex[:8]
    now = int(time.time())
    await db.create_goal(types.SimpleNamespace(
        id=gid, title="[Replay] Fix auth bug and open PR", goal_text="demo",
        trace_id=uuid.uuid4().hex)) if hasattr(db, "create_goal") else None
    print(f"Replay goal {gid} — open /app/economy to watch the ledger.")
    for i, (role, output) in enumerate(CANNED, start=1):
        task = types.SimpleNamespace(id=f"{gid}_t{i}", goal_id=gid, agent_name=role)
        proof = await economy.record_proof(task, output)
        print(f"  minted proof for {role}: block={proof['block_number'] if proof else 'skip'}")
        await asyncio.sleep(2)
    print("Replay complete.")


if __name__ == "__main__":
    asyncio.run(main())
```

Note: the `create_goal` call is guarded — the replay only needs `record_proof`, which does not require a goal row. If `db.create_goal` has a different signature, drop that line entirely; proofs reference `goal_id` as a plain string with no FK on `proofs`.

- [ ] **Step 2: Verify it runs**

Run: `cd backend && .venv/bin/python scripts/replay_demo.py`
Expected: prints three "minted proof" lines with increasing block numbers, then "Replay complete."

- [ ] **Step 3: CHECKPOINT** — tell the user Task 10 is ready to commit (`backend/scripts/replay_demo.py`).

---

### Task 11: Runnability + end-to-end verification

**Files:** none new — this task installs, runs, and verifies the whole stack.

- [ ] **Step 1: Backend env + deps**

```bash
cd backend
cp -n .env.example .env   # then fill GROQ_API_KEY, ANTHROPIC_API_KEY, TAVILY_API_KEY, GITHUB_TOKEN
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest
```

Run the full backend test suite:
`cd backend && .venv/bin/python -m pytest test_economy.py test_economy_db.py test_economy_flow.py test_economy_api.py -v`
Expected: all pass.

- [ ] **Step 2: Frontend deps + build**

```bash
cd frontend && npm install && npm run build
```
Expected: build succeeds, 0 TS errors.

- [ ] **Step 3: Start the stack**

Run backend: `cd backend && .venv/bin/python main.py` (serves API on :8000).
In another terminal: `cd frontend && npm run dev` (or use the built `dist` served by FastAPI).

- [ ] **Step 4: Verify economy endpoints live**

```bash
curl -s localhost:8000/api/economy/passports | head
curl -s localhost:8000/api/economy/leaderboard | head
curl -s localhost:8000/api/economy/chain
```
Expected: 6 passports, a leaderboard array, chainId 10143.

- [ ] **Step 5: Verify the live loop**

Option A (live keys): submit a goal from the Dashboard and confirm on `/app/economy` that new proofs stream into the ledger and a role's composite score changes.
Option B (safety net): run `cd backend && .venv/bin/python scripts/replay_demo.py` while `/app/economy` is open; confirm the Proof Ledger animates new rows and the Leaderboard updates.

- [ ] **Step 6: Verify auth bypass + no omniBox**

With `VITE_DEMO_MODE=true`, visit `/app` — must load without redirect to `/login`. Grep the built output:
`cd frontend && grep -ri "omnibox" dist/ || echo "clean"`
Expected: `clean` (Task 12 finishes the rebrand; run this again after Task 12).

- [ ] **Step 7: CHECKPOINT** — report verification results to the user (paste command outputs). Nothing to commit unless fixes were made.

---

### Task 12: Full rebrand omniBox → Mergit + visual identity

**Files (modify):**
- `frontend/index.html` (title/meta)
- `frontend/src/pages/Landing.tsx` + `frontend/src/components/landing/*` (hero copy, wordmark, sections)
- `frontend/src/components/AppNav.tsx` (wordmark)
- Any component with the string "omniBox"
- `frontend/src/index.css` / Tailwind config (brand color tokens)
- `README.md`, `CLAUDE.md`, `progress.md`, `pitch/DEMO_VIDEO_SCRIPT.md`

**REQUIRED SUB-SKILL when executing this task: `frontend-design`** — establish the Mergit identity (on-chain aesthetic: deep indigo/violet base, electric cyan/green accents, monospace for hashes/scores/blocks; a distinct Mergit wordmark). Apply the same tokens retroactively to Task 8/9 components.

- [ ] **Step 1: Find every brand string**

Run: `cd frontend && grep -rin "omnibox" src index.html`
List every hit — each must be replaced with "Mergit" (or updated copy).

- [ ] **Step 2: Rebrand the app shell + nav wordmark**

Replace the wordmark/logo text in `AppNav.tsx` and any header with a "Mergit" wordmark styled per the frontend-design identity. Update `frontend/index.html` `<title>` to "Mergit — The AI Agent Economy".

- [ ] **Step 3: Rewrite the Landing narrative**

Update `pages/Landing.tsx` + `components/landing/*` hero/features/how-it-works copy to pitch the **agent economy**: agents with on-chain identities (passports), earning verifiable reputation, every unit of work recorded as proof-of-work on Monad. Keep the existing section structure; swap copy + add an economy/leaderboard teaser section linking to `/app/economy`.

- [ ] **Step 4: Apply brand tokens**

Add the Mergit color tokens to `frontend/src/index.css` (CSS variables) / Tailwind theme, and apply across the new economy components (Task 8/9) and landing so the whole app reads as one system.

- [ ] **Step 5: Rebrand docs**

Update `README.md` (title/description → Mergit), and per repo protocol update `CLAUDE.md` (add: `economy.py`, the 3 tables, `/api/economy/*`, economy pages, DEMO_MODE, replay script, rebrand) and append a dated session block to `progress.md`. Update `pitch/DEMO_VIDEO_SCRIPT.md` to the Mergit agent-economy narrative.

- [ ] **Step 6: Verify no brand leakage + build**

Run:
```bash
cd frontend && grep -rin "omnibox" src index.html || echo "src clean"
npm run build && grep -ri "omnibox" dist/ || echo "dist clean"
```
Expected: `src clean` and `dist clean`, build succeeds.

- [ ] **Step 7: CHECKPOINT** — tell the user Task 12 (and the prototype) is ready to commit; summarize what changed.

---

## Self-Review

**Spec coverage:**
- Economy engine (§1) → Tasks 2, 3. Persistence (§2) → Task 1 + seed/backfill in Task 3. Live channel (§3) → Task 3 (`record_proof` emits) + Task 5 (`/stream`). API (§4) → Task 5. Worker hook (§5) → Task 4. Frontend pages + rebrand (§6) → Tasks 6, 8, 9, 12. Runnability/DEMO_MODE/seed/replay/demo script (§7) → Tasks 3, 7, 10, 11, 12. All spec sections mapped.
- Success criteria: (1) runs end-to-end → Task 11; (2) branded Mergit → Task 12; (3) live proofs/reputation → Tasks 3/4/8 + verified Task 11; (4) populated on first load → backfill Task 3; (5) replay mode → Task 10; (6) auth bypass → Task 7.

**Placeholder scan:** No "TBD/TODO/handle appropriately". `<HELPER>`/`<...>` in Task 6 is an explicit instruction to match the file's existing fetch helper discovered in that task's Step 1, not a placeholder to leave in code.

**Type consistency:** `record_proof(task, output)`, `recompute_role(role)`, `seed_passports()`, `backfill()`, `ECONOMY_CHANNEL="economy"` used identically across Tasks 3/4/5/10. DB accessor names in Task 1 match their calls in Tasks 3/5. Proof dict keys (`task_id, goal_id, agent_role, result_hash, tx_hash, block_number, recorded_at`) consistent across backend and the frontend `Proof` type (Task 6). Reputation keys (`composite, success_rate, speed, volume, badge`) consistent across Task 2/3 output, Task 1 storage, and Task 6 `RepEntry`.
