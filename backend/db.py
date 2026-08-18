import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

import migrations
import redaction
from config import settings
from state import GoalRow, GoalStatus, MessageRow, TaskRow, TaskStatus, ToolCallRow

logger = logging.getLogger(__name__)

_db_path = settings.db_path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS goals (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    goal_text       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'NEW',
    output          TEXT,
    error           TEXT,
    plan_json       TEXT,
    terminal_task_id TEXT,
    trace_id        TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    goal_id         TEXT NOT NULL REFERENCES goals(id),
    agent_name      TEXT NOT NULL,
    description     TEXT NOT NULL,
    inputs          TEXT NOT NULL DEFAULT '{}',
    depends_on      TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'PENDING',
    output          TEXT,
    error           TEXT,
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    worker_id       TEXT,
    lease_expires_at INTEGER,
    wait_token      TEXT UNIQUE,
    wait_payload    TEXT,
    idempotency_key TEXT UNIQUE,
    trace_id        TEXT NOT NULL,
    parent_span_id  TEXT,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_goal_id ON tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_tasks_wait_token ON tasks(wait_token);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    tool_call_id    TEXT,
    sequence        INTEGER NOT NULL,
    created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_task_id ON messages(task_id);

CREATE TABLE IF NOT EXISTS tool_calls (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    tool_name       TEXT NOT NULL,
    args_json       TEXT NOT NULL,
    args_hash       TEXT NOT NULL,
    result_json     TEXT,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    error           TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at      INTEGER NOT NULL,
    completed_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_task_id ON tool_calls(task_id);

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

-- Durable queue for on-chain proof submission (PRD §5.4 outbox pattern).
-- Chain submission is asynchronous and retryable so it can never block or break a goal run.
CREATE TABLE IF NOT EXISTS proof_outbox (
    task_id         TEXT PRIMARY KEY,
    goal_id         TEXT NOT NULL,
    agent_role      TEXT NOT NULL,
    result_hash     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    chain_id        INTEGER,
    tx_hash         TEXT,
    block_number    INTEGER,
    last_error      TEXT,
    next_attempt_at INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outbox_claim ON proof_outbox(status, next_attempt_at);

-- Self-heal history: every auto-detected developer bug, deduplicated by fingerprint.
CREATE TABLE IF NOT EXISTS heal_attempts (
    id               TEXT PRIMARY KEY,
    fingerprint      TEXT NOT NULL,
    goal_id          TEXT NOT NULL,
    task_id          TEXT,
    agent_name       TEXT NOT NULL,
    error            TEXT NOT NULL,
    error_summary    TEXT NOT NULL,
    classification   TEXT NOT NULL DEFAULT 'bug',
    status           TEXT NOT NULL,
    issue_number     INTEGER,
    issue_url        TEXT,
    issue_body       TEXT,
    fix_goal_id      TEXT,
    outcome          TEXT,
    recurrence_count INTEGER NOT NULL DEFAULT 1,
    created_at       INTEGER NOT NULL,
    updated_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_heal_fingerprint ON heal_attempts(fingerprint);
CREATE INDEX IF NOT EXISTS idx_heal_fix_goal ON heal_attempts(fix_goal_id);
"""


def _now() -> int:
    return int(time.time())


def _row_to_goal(row: aiosqlite.Row) -> GoalRow:
    return GoalRow(
        id=row["id"],
        title=row["title"],
        goal_text=row["goal_text"],
        status=row["status"],
        output=json.loads(row["output"]) if row["output"] else None,
        error=row["error"],
        plan_json=row["plan_json"],
        terminal_task_id=row["terminal_task_id"],
        trace_id=row["trace_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        source=row["source"] if "source" in row.keys() else "user",
        heal_depth=row["heal_depth"] if "heal_depth" in row.keys() else 0,
        # Defensive `.keys()` probes, matching the existing pattern: a row selected before
        # the migration ran (or by a test fixture on an older file) has no such column.
        user_id=row["user_id"] if "user_id" in row.keys() else LEGACY_USER_ID,
        is_public=bool(row["is_public"]) if "is_public" in row.keys() else False,
    )


def _row_to_task(row: aiosqlite.Row) -> TaskRow:
    return TaskRow(
        id=row["id"],
        goal_id=row["goal_id"],
        agent_name=row["agent_name"],
        description=row["description"],
        inputs=json.loads(row["inputs"]),
        depends_on=json.loads(row["depends_on"]),
        status=row["status"],
        output=json.loads(row["output"]) if row["output"] else None,
        error=row["error"],
        attempt_count=row["attempt_count"],
        failure_count=row["failure_count"] if "failure_count" in row.keys() else 0,
        max_attempts=row["max_attempts"],
        worker_id=row["worker_id"],
        lease_expires_at=row["lease_expires_at"],
        wait_token=row["wait_token"],
        wait_payload=json.loads(row["wait_payload"]) if row["wait_payload"] else None,
        idempotency_key=row["idempotency_key"],
        trace_id=row["trace_id"],
        parent_span_id=row["parent_span_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_tool_call(row: aiosqlite.Row) -> ToolCallRow:
    return ToolCallRow(
        id=row["id"],
        task_id=row["task_id"],
        tool_name=row["tool_name"],
        args_json=row["args_json"],
        args_hash=row["args_hash"],
        result_json=row["result_json"],
        status=row["status"],
        error=row["error"],
        idempotency_key=row["idempotency_key"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


@asynccontextmanager
async def get_conn() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(_db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn


async def init_db() -> None:
    async with get_conn() as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()
        # Migrate: add waiting_credential column if not present
        try:
            await conn.execute("ALTER TABLE tasks ADD COLUMN waiting_credential TEXT")
            await conn.commit()
        except Exception:
            pass  # column already exists

        # Migrate: goal provenance, so a self-heal fix goal can be told apart from a user
        # goal and never trigger another heal cycle.
        #
        # These two predate the migration runner and are left in place: deployments that
        # already ran them have no `schema_migrations` row to prove it, so moving them
        # would make the runner try to re-add a column that exists.
        for ddl in (
            "ALTER TABLE goals ADD COLUMN source TEXT NOT NULL DEFAULT 'user'",
            "ALTER TABLE goals ADD COLUMN heal_depth INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                await conn.execute(ddl)
                await conn.commit()
            except Exception:
                pass  # column already exists

        # Everything from `failure_count` onward is ordered and recorded. See migrations.py
        # for why the try/except-ALTER pattern could not carry the auth work.
        await migrations.run_migrations(conn)


# ── Goals ──────────────────────────────────────────────────────────────────────

async def create_goal(
    goal_text: str,
    user_id: str,
    source: str = "user",
    heal_depth: int = 0,
    is_public: bool = False,
    connection_hint: dict | None = None,
) -> GoalRow:
    """Create a goal owned by `user_id`.

    `user_id` is a **required positional argument** on purpose. There are seven call sites
    — the API, both webhook branches, the actions route, `spawn_goal`, `self_heal` and
    `demo_seed` — and a goal created without an owner is not merely untidy: after the
    broker lands it resolves to no connection, parks on the credential key `conn:github:`
    with an empty user, and no callback will ever release it. It is unresumable *and*
    invisible, because `list_goals` filters by owner. Making it required turns every
    missed call site into an import-time TypeError instead.

    Sentinel owners exist for the callers that have no human: `usr_mergit_system` for
    self-heal, `usr_legacy_demo` for seeded demo data.
    """
    now = _now()
    goal_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    title = goal_text[:80] + ("…" if len(goal_text) > 80 else "")
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO goals
               (id, title, goal_text, status, trace_id, source, heal_depth,
                user_id, is_public, connection_hint, created_at, updated_at)
               VALUES (?, ?, ?, 'NEW', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (goal_id, title, goal_text, trace_id, source, heal_depth,
             user_id, 1 if is_public else 0, json.dumps(connection_hint or {}), now, now),
        )
        await conn.commit()
        row = await (await conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,))).fetchone()
    return _row_to_goal(row)


async def get_goal(goal_id: str, user_id: str | None = None) -> GoalRow | None:
    """Fetch a goal, optionally constrained to its owner.

    `user_id=None` means "no ownership check" and is for internal callers — the worker,
    the economy, self-heal — which operate on behalf of the system rather than a request.
    Every HTTP handler must pass one. A caller that omits it on a request path turns a
    404 into a cross-tenant read.
    """
    async with get_conn() as conn:
        if user_id is None:
            row = await (await conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,))).fetchone()
        else:
            row = await (
                await conn.execute(
                    "SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, user_id)
                )
            ).fetchone()
    return _row_to_goal(row) if row else None


async def goal_owner(goal_id: str) -> str | None:
    """The user a goal belongs to. One indexed read, used by the credential broker."""
    async with get_conn() as conn:
        row = await (
            await conn.execute("SELECT user_id FROM goals WHERE id=?", (goal_id,))
        ).fetchone()
    return row["user_id"] if row else None


async def list_goals(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    user_id: str | None = None,
) -> list[GoalRow]:
    """List goals, optionally scoped to one owner.

    `user_id=None` returns everything and is for internal callers only. `GET /api/goals`
    used to be exactly this query with no filter, which is why every visitor could read
    every other visitor's goals — including their goal text and outputs.
    """
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    if user_id is not None:
        clauses.append("user_id=?")
        params.append(user_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])

    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                f"SELECT * FROM goals {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                tuple(params),
            )
        ).fetchall()
    return [_row_to_goal(r) for r in rows]


async def update_goal_status(goal_id: str, status: str, output: dict | None = None, error: str | None = None) -> None:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE goals SET status=?, output=?, error=?, updated_at=? WHERE id=?",
            (status, json.dumps(output) if output else None, error, now, goal_id),
        )
        await conn.commit()


async def set_goal_plan(goal_id: str, plan_json: str, terminal_task_id: str) -> None:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE goals SET plan_json=?, terminal_task_id=?, status='RUNNING', updated_at=? WHERE id=?",
            (plan_json, terminal_task_id, now, goal_id),
        )
        await conn.commit()


async def claim_new_goal() -> GoalRow | None:
    now = _now()
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                """UPDATE goals SET status='PLANNING', updated_at=?
                   WHERE id=(SELECT id FROM goals WHERE status='NEW' ORDER BY created_at LIMIT 1)
                   RETURNING *""",
                (now,),
            )
        ).fetchone()
        await conn.commit()
    return _row_to_goal(row) if row else None


# ── Tasks ──────────────────────────────────────────────────────────────────────

async def create_tasks(tasks: list[dict], goal_id: str, trace_id: str) -> list[TaskRow]:
    now = _now()
    created = []
    async with get_conn() as conn:
        for t in tasks:
            ikey = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO tasks
                   (id, goal_id, agent_name, description, inputs, depends_on, status,
                    idempotency_key, trace_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    t["id"], goal_id, t["agent"], t["description"],
                    json.dumps(t.get("inputs", {})),
                    json.dumps(t.get("depends_on", [])),
                    TaskStatus.READY if not t.get("depends_on") else TaskStatus.PENDING,
                    ikey, trace_id, now, now,
                ),
            )
        await conn.commit()
        rows = await (
            await conn.execute("SELECT * FROM tasks WHERE goal_id=?", (goal_id,))
        ).fetchall()
    return [_row_to_task(r) for r in rows]


async def get_task(task_id: str) -> TaskRow | None:
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,))).fetchone()
    return _row_to_task(row) if row else None


async def list_goal_tasks(goal_id: str) -> list[TaskRow]:
    async with get_conn() as conn:
        rows = await (
            await conn.execute("SELECT * FROM tasks WHERE goal_id=? ORDER BY created_at", (goal_id,))
        ).fetchall()
    return [_row_to_task(r) for r in rows]


async def claim_ready_task(worker_id: str, lease_secs: int) -> TaskRow | None:
    now = _now()
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                """UPDATE tasks SET status='RUNNING', worker_id=?, lease_expires_at=?,
                   attempt_count=attempt_count+1, updated_at=?
                   WHERE id=(
                       SELECT candidate.id
                       FROM tasks candidate
                       WHERE candidate.status='READY'
                         AND NOT EXISTS (
                           SELECT 1
                           FROM json_each(candidate.depends_on) dep
                           LEFT JOIN tasks dependency
                             ON dependency.id=dep.value
                            AND dependency.goal_id=candidate.goal_id
                           WHERE dependency.id IS NULL
                              OR dependency.status != 'DONE'
                         )
                       ORDER BY candidate.created_at
                       LIMIT 1
                   )
                   RETURNING *""",
                (worker_id, now + lease_secs, now),
            )
        ).fetchone()
        await conn.commit()
    return _row_to_task(row) if row else None


async def settle_task(task_id: str, status: str, output: dict | None = None,
                      error: str | None = None, worker_id: str | None = None) -> bool:
    """Record a task's outcome. Returns False when the write was refused.

    `worker_id` fences the write against a lost lease. `reclaim_expired_leases` hands a
    still-RUNNING task back to the pool after `lease_seconds`, without knowing whether the
    original coroutine is still going — so a slow task gets executed twice, and this used
    to write by id alone, letting whoever finished last win.

    Goal 60d42a5f recorded an impossible result that way: coder t2 FAILED while the
    integrator t3 that depends on it ran and opened PR #40. t2 was DONE when t3 was
    promoted, and a straggling duplicate overwrote it with FAILED afterwards. The same
    race is why goal 00605510's coder output changed between two reads of a goal that had
    already completed.

    Passing no worker_id is an administrative settle — a retry, a requeue, a reclaim — and
    still applies unconditionally, because those callers are the scheduler itself rather
    than a competing lease holder.
    """
    now = _now()
    payload = json.dumps(output) if output is not None else None
    async with get_conn() as conn:
        if worker_id is None:
            cur = await conn.execute(
                "UPDATE tasks SET status=?, output=?, error=?, worker_id=NULL, "
                "lease_expires_at=NULL, updated_at=? WHERE id=?",
                (status, payload, error, now, task_id),
            )
        else:
            cur = await conn.execute(
                "UPDATE tasks SET status=?, output=?, error=?, worker_id=NULL, "
                "lease_expires_at=NULL, updated_at=? WHERE id=? AND worker_id=?",
                (status, payload, error, now, task_id, worker_id),
            )
        await conn.commit()
        if cur.rowcount == 0:
            logger.warning("settle_task refused for task=%s by worker=%s — the lease is no "
                           "longer theirs; discarding this result", task_id, worker_id)
            return False
    return True


async def promote_ready_tasks(goal_id: str) -> list[str]:
    now = _now()
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                """UPDATE tasks SET status='READY', updated_at=?
                   WHERE status='PENDING' AND goal_id=?
                     AND (error IS NULL OR error NOT LIKE 'Rate limited;%')
                     AND NOT EXISTS (
                       SELECT 1
                       FROM json_each(tasks.depends_on) dep
                       LEFT JOIN tasks dependency
                         ON dependency.id=dep.value
                        AND dependency.goal_id=tasks.goal_id
                       WHERE dependency.id IS NULL
                          OR dependency.status != 'DONE'
                     )
                   RETURNING id""",
                (now, goal_id),
            )
        ).fetchall()
        await conn.commit()
    return [r["id"] for r in rows]


async def reclaim_expired_leases() -> int:
    now = _now()
    async with get_conn() as conn:
        result = await conn.execute(
            """UPDATE tasks SET status='READY', worker_id=NULL, lease_expires_at=NULL, updated_at=?
               WHERE status='RUNNING' AND lease_expires_at < ?""",
            (now, now),
        )
        await conn.commit()
    return result.rowcount


async def resume_webhook_task(wait_token: str, payload: dict) -> TaskRow | None:
    now = _now()
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                """UPDATE tasks SET status='READY', wait_payload=?, updated_at=?
                   WHERE wait_token=? AND status='WAITING_WEBHOOK'
                   RETURNING *""",
                (json.dumps(payload), now, wait_token),
            )
        ).fetchone()
        await conn.commit()
    return _row_to_task(row) if row else None


async def set_task_waiting_webhook(task_id: str, wait_token: str) -> None:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE tasks SET status='WAITING_WEBHOOK', wait_token=?, worker_id=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?",
            (wait_token, now, task_id),
        )
        await conn.commit()


async def set_task_waiting_credential(task_id: str, credential_var: str) -> None:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE tasks SET status='WAITING_CREDENTIAL', waiting_credential=?, "
            "worker_id=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?",
            (credential_var, now, task_id),
        )
        await conn.commit()


async def find_orphaned_goals() -> list[dict]:
    """
    Return goals in RUNNING/PLANNING state where no task can make further progress
    (every task is DONE or FAILED) so the goal will never self-resolve.

    `WAITING_WEBHOOK` and `WAITING_CREDENTIAL` count as progress. They used to count as
    stalled, which meant a task parked for something the world still owed it — an inbound
    callback, or a user who had been asked to connect their GitHub account — had its goal
    swept to FAILED with "All tasks failed — no progress possible" while the person was
    still reading the prompt. A parked task resumes by design; the only thing it is
    waiting on is time.
    """
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                """
                SELECT g.id, g.terminal_task_id, g.error,
                       t.status  AS terminal_status,
                       t.output  AS terminal_output_json
                FROM goals g
                LEFT JOIN tasks t ON t.id = g.terminal_task_id
                WHERE g.status IN ('RUNNING', 'PLANNING')
                  AND g.terminal_task_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM tasks sub
                    WHERE sub.goal_id = g.id
                      AND sub.status IN ('PENDING', 'READY', 'RUNNING',
                                         'WAITING_WEBHOOK', 'WAITING_CREDENTIAL')
                  )
                """
            )
        ).fetchall()
    result = []
    for r in rows:
        out = None
        if r["terminal_output_json"]:
            try:
                out = json.loads(r["terminal_output_json"])
            except Exception:
                pass
        result.append({
            "id": r["id"],
            "terminal_task_id": r["terminal_task_id"],
            "terminal_status": r["terminal_status"],
            "terminal_output": out,
            "error": r["error"],
        })
    return result


async def resume_credential_tasks(env_var: str) -> list[dict]:
    now = _now()
    async with get_conn() as conn:
        rows = await (
            await conn.execute(
                """UPDATE tasks SET status='READY', waiting_credential=NULL, updated_at=?
                   WHERE status='WAITING_CREDENTIAL' AND waiting_credential=?
                   RETURNING id, goal_id, agent_name""",
                (now, env_var),
            )
        ).fetchall()
        await conn.commit()
    return [{"id": r["id"], "goal_id": r["goal_id"], "agent_name": r["agent_name"]} for r in rows]


# ── Messages ───────────────────────────────────────────────────────────────────

async def save_message(task_id: str, role: str, content: str, sequence: int, tool_call_id: str | None = None) -> None:
    now = _now()
    msg_id = str(uuid.uuid4())
    body = content if isinstance(content, str) else json.dumps(content)
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (id, task_id, role, content, tool_call_id, sequence, created_at) VALUES (?,?,?,?,?,?,?)",
            # The conversation is replayed and displayed. A credential that reaches it is
            # in model context and on the goal page for as long as the row lives.
            (msg_id, task_id, role, redaction.scrub(body), tool_call_id, sequence, now),
        )
        await conn.commit()


async def get_task_messages(task_id: str) -> list[MessageRow]:
    async with get_conn() as conn:
        rows = await (
            await conn.execute("SELECT * FROM messages WHERE task_id=? ORDER BY sequence", (task_id,))
        ).fetchall()
    return [
        MessageRow(
            id=r["id"], task_id=r["task_id"], role=r["role"], content=r["content"],
            tool_call_id=r["tool_call_id"], sequence=r["sequence"], created_at=r["created_at"],
        )
        for r in rows
    ]


# ── Tool Calls ─────────────────────────────────────────────────────────────────

async def get_tool_call_by_idempotency(ikey: str) -> ToolCallRow | None:
    async with get_conn() as conn:
        row = await (
            await conn.execute("SELECT * FROM tool_calls WHERE idempotency_key=?", (ikey,))
        ).fetchone()
    return _row_to_tool_call(row) if row else None


async def create_tool_call(task_id: str, tool_name: str, args_json: str, args_hash: str, ikey: str) -> str:
    now = _now()
    tc_id = str(uuid.uuid4())
    async with get_conn() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO tool_calls (id, task_id, tool_name, args_json, args_hash, status, idempotency_key, created_at) VALUES (?,?,?,?,?,'PENDING',?,?)",
            (tc_id, task_id, tool_name, args_json, args_hash, ikey, now),
        )
        await conn.commit()
    return tc_id


async def record_failure(task_id: str) -> int:
    """Spend one retry. Called only when a task raised — never when it parks.

    Returns the new count so the caller can decide without a re-read.
    """
    now = _now()
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                "UPDATE tasks SET failure_count=failure_count+1, updated_at=? WHERE id=? "
                "RETURNING failure_count",
                (now, task_id),
            )
        ).fetchone()
        await conn.commit()
    return row["failure_count"] if row else 0


async def delete_tool_call(ikey: str) -> None:
    """Forget an invocation entirely, so the next attempt re-executes it.

    Used when a tool parks the task instead of doing its work. The row exists only because
    `create_tool_call` runs before dispatch; leaving it behind would let the idempotency
    cache replay a "waiting for a credential" answer after the credential arrived.
    """
    async with get_conn() as conn:
        await conn.execute("DELETE FROM tool_calls WHERE idempotency_key=?", (ikey,))
        await conn.commit()


async def settle_tool_call(ikey: str, result_json: str | None, status: str, error: str | None = None) -> None:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE tool_calls SET result_json=?, status=?, error=?, completed_at=? WHERE idempotency_key=?",
            (result_json, status, error, now, ikey),
        )
        await conn.commit()


# ── Economy: passports, reputation, proofs ──────────────────────────────────────

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


#: The ledger is a two-tier view, not a filter.
#:
#: Filtering strictly to the caller looked like the obvious privacy fix and would have
#: broken the product's most visible page: `demo_seed` mints the only proofs a fresh
#: instance has, so a newly signed-in user would see an EMPTY Proof Ledger while the
#: Leaderboard showed non-zero reputation computed from proofs they could not see. The
#: showcase would render as a bug.
#:
#: So: your own proofs, plus anything whose goal is flagged public. Demo-seeded goals are
#: synthetic by construction and carry `is_public=1`; nothing a real user creates does.
#: The rule is a column rather than a hardcoded user id, so it stays true if the seeding
#: strategy changes.
_VISIBLE_GOALS = """
    p.goal_id IN (SELECT id FROM goals WHERE user_id = ? OR is_public = 1)
"""


async def list_proofs(limit=50, before_block=None, user_id=None):
    async with get_conn() as conn:
        if user_id is None:
            # Internal callers (backfill, verification) see everything.
            if before_block is not None:
                cur = await conn.execute(
                    "SELECT * FROM proofs WHERE block_number < ? ORDER BY block_number DESC LIMIT ?",
                    (before_block, limit))
            else:
                cur = await conn.execute(
                    "SELECT * FROM proofs ORDER BY block_number DESC LIMIT ?", (limit,))
        elif before_block is not None:
            cur = await conn.execute(
                f"SELECT p.* FROM proofs p WHERE {_VISIBLE_GOALS} AND p.block_number < ? "
                "ORDER BY p.block_number DESC LIMIT ?",
                (user_id, before_block, limit))
        else:
            cur = await conn.execute(
                f"SELECT p.* FROM proofs p WHERE {_VISIBLE_GOALS} "
                "ORDER BY p.block_number DESC LIMIT ?",
                (user_id, limit))
        return [_proof_row(r) for r in await cur.fetchall()]


async def list_proofs_for_role(role, limit=20, user_id=None):
    async with get_conn() as conn:
        if user_id is None:
            cur = await conn.execute(
                "SELECT * FROM proofs WHERE agent_role=? ORDER BY block_number DESC LIMIT ?",
                (role, limit))
        else:
            cur = await conn.execute(
                f"SELECT p.* FROM proofs p WHERE p.agent_role=? AND {_VISIBLE_GOALS} "
                "ORDER BY p.block_number DESC LIMIT ?",
                (role, user_id, limit))
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


# ── Proof outbox (durable on-chain submission queue) ────────────────────────────

MAX_PROOF_ATTEMPTS = 10
_MAX_BACKOFF_SECONDS = 300


def _outbox_row(row) -> dict:
    return {
        "task_id": row["task_id"], "goal_id": row["goal_id"],
        "agent_role": row["agent_role"], "result_hash": row["result_hash"],
        "status": row["status"], "attempts": row["attempts"],
        "chain_id": row["chain_id"], "tx_hash": row["tx_hash"],
        "block_number": row["block_number"], "last_error": row["last_error"],
        "next_attempt_at": row["next_attempt_at"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


async def enqueue_proof(task_id: str, goal_id: str, agent_role: str, result_hash: str) -> bool:
    """Queue a proof for chain submission. False when this task was already queued."""
    now = _now()
    async with get_conn() as conn:
        try:
            await conn.execute(
                """INSERT INTO proof_outbox
                   (task_id, goal_id, agent_role, result_hash, status, attempts,
                    next_attempt_at, created_at, updated_at)
                   VALUES (?,?,?,?, 'pending', 0, 0, ?, ?)""",
                (task_id, goal_id, agent_role, result_hash, now, now),
            )
            await conn.commit()
            return True
        except Exception:
            return False


async def claim_pending_proofs(limit: int = 10, now: int | None = None) -> list[dict]:
    """Atomically claim due entries, moving them to 'submitting'."""
    ts = _now() if now is None else now
    async with get_conn() as conn:
        cur = await conn.execute(
            """UPDATE proof_outbox SET status='submitting', updated_at=?
               WHERE task_id IN (
                   SELECT task_id FROM proof_outbox
                   WHERE status='pending' AND next_attempt_at <= ?
                   ORDER BY created_at LIMIT ?
               )
               RETURNING *""",
            (ts, ts, limit),
        )
        rows = await cur.fetchall()
        await conn.commit()
        return [_outbox_row(r) for r in rows]


async def mark_proof_confirmed(task_id: str, tx_hash: str, block_number: int,
                               chain_id: int) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """UPDATE proof_outbox
               SET status='confirmed', tx_hash=?, block_number=?, chain_id=?,
                   last_error=NULL, updated_at=?
               WHERE task_id=?""",
            (tx_hash, block_number, chain_id, _now(), task_id),
        )
        await conn.commit()


async def mark_proof_failed(task_id: str, error: str, now: int | None = None) -> str:
    """Record a failed attempt with exponential backoff; dead-letter at the attempt cap.

    Returns the resulting status.
    """
    ts = _now() if now is None else now
    async with get_conn() as conn:
        cur = await conn.execute("SELECT attempts FROM proof_outbox WHERE task_id=?", (task_id,))
        row = await cur.fetchone()
        if not row:
            return "unknown"

        attempts = row["attempts"] + 1
        if attempts >= MAX_PROOF_ATTEMPTS:
            status, next_at = "dead_lettered", 0
        else:
            status = "pending"
            next_at = ts + min(2 ** attempts, _MAX_BACKOFF_SECONDS)

        await conn.execute(
            """UPDATE proof_outbox
               SET status=?, attempts=?, last_error=?, next_attempt_at=?, updated_at=?
               WHERE task_id=?""",
            (status, attempts, (error or "")[:500], next_at, ts, task_id),
        )
        await conn.commit()
        return status


async def reclaim_stuck_proofs(older_than_seconds: int = 300) -> int:
    """Return entries stranded in 'submitting' by a crash back to 'pending'."""
    cutoff = _now() - older_than_seconds
    async with get_conn() as conn:
        cur = await conn.execute(
            """UPDATE proof_outbox SET status='pending', next_attempt_at=0, updated_at=?
               WHERE status='submitting' AND updated_at <= ?
               RETURNING task_id""",
            (_now(), cutoff),
        )
        rows = await cur.fetchall()
        await conn.commit()
        return len(rows)


async def get_outbox_entry(task_id: str) -> dict | None:
    async with get_conn() as conn:
        cur = await conn.execute("SELECT * FROM proof_outbox WHERE task_id=?", (task_id,))
        row = await cur.fetchone()
        return _outbox_row(row) if row else None


async def list_outbox(status: str | None = None, limit: int = 100) -> list[dict]:
    async with get_conn() as conn:
        if status:
            cur = await conn.execute(
                "SELECT * FROM proof_outbox WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit))
        else:
            cur = await conn.execute(
                "SELECT * FROM proof_outbox ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_outbox_row(r) for r in await cur.fetchall()]


async def outbox_stats() -> dict[str, int]:
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT status, COUNT(*) AS n FROM proof_outbox GROUP BY status")
        return {r["status"]: r["n"] for r in await cur.fetchall()}


# ── Self-heal attempts ──────────────────────────────────────────────────────────

def _heal_row(row) -> dict:
    return {
        "id": row["id"], "fingerprint": row["fingerprint"], "goal_id": row["goal_id"],
        "task_id": row["task_id"], "agent_name": row["agent_name"],
        "error": row["error"], "error_summary": row["error_summary"],
        "classification": row["classification"], "status": row["status"],
        "issue_number": row["issue_number"], "issue_url": row["issue_url"],
        "issue_body": row["issue_body"], "fix_goal_id": row["fix_goal_id"],
        "outcome": row["outcome"], "recurrence_count": row["recurrence_count"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


async def create_heal_attempt(attempt_id: str, fingerprint: str, goal_id: str, task_id: str | None,
                              agent_name: str, error: str, error_summary: str,
                              classification: str, status: str, issue_body: str = "") -> dict:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO heal_attempts
               (id, fingerprint, goal_id, task_id, agent_name, error, error_summary,
                classification, status, issue_body, recurrence_count, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            (attempt_id, fingerprint, goal_id, task_id, agent_name, error[:4000],
             error_summary[:500], classification, status, issue_body, now, now),
        )
        await conn.commit()
        row = await (await conn.execute(
            "SELECT * FROM heal_attempts WHERE id=?", (attempt_id,))).fetchone()
    return _heal_row(row)


async def get_heal_attempt(attempt_id: str) -> dict | None:
    async with get_conn() as conn:
        row = await (await conn.execute(
            "SELECT * FROM heal_attempts WHERE id=?", (attempt_id,))).fetchone()
        return _heal_row(row) if row else None


async def find_heal_attempt_by_fingerprint(fingerprint: str) -> dict | None:
    """Most recent live attempt for this fingerprint — the dedup lookup."""
    async with get_conn() as conn:
        row = await (await conn.execute(
            """SELECT * FROM heal_attempts
               WHERE fingerprint=? AND status IN ('filed','simulated')
               ORDER BY created_at DESC LIMIT 1""", (fingerprint,))).fetchone()
        return _heal_row(row) if row else None


async def bump_heal_recurrence(attempt_id: str) -> int:
    async with get_conn() as conn:
        cur = await conn.execute(
            """UPDATE heal_attempts
               SET recurrence_count = recurrence_count + 1, updated_at = ?
               WHERE id = ? RETURNING recurrence_count""", (_now(), attempt_id))
        row = await cur.fetchone()
        await conn.commit()
        return row["recurrence_count"] if row else 0


async def update_heal_attempt(attempt_id: str, **fields) -> None:
    allowed = {"status", "issue_number", "issue_url", "issue_body", "fix_goal_id", "outcome"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{k}=?" for k in updates)
    async with get_conn() as conn:
        await conn.execute(
            f"UPDATE heal_attempts SET {assignments}, updated_at=? WHERE id=?",
            (*updates.values(), _now(), attempt_id))
        await conn.commit()


async def find_heal_attempt_by_fix_goal(fix_goal_id: str) -> dict | None:
    async with get_conn() as conn:
        row = await (await conn.execute(
            "SELECT * FROM heal_attempts WHERE fix_goal_id=? LIMIT 1", (fix_goal_id,))).fetchone()
        return _heal_row(row) if row else None


async def list_heal_attempts(limit: int = 100) -> list[dict]:
    async with get_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM heal_attempts ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_heal_row(r) for r in await cur.fetchall()]


async def heal_stats() -> dict:
    async with get_conn() as conn:
        cur = await conn.execute(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(recurrence_count), 0) AS recurrences
               FROM heal_attempts""")
        totals = await cur.fetchone()
        by_status = {r["status"]: r["n"] for r in await (await conn.execute(
            "SELECT status, COUNT(*) AS n FROM heal_attempts GROUP BY status")).fetchall()}
        by_outcome = {r["outcome"]: r["n"] for r in await (await conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM heal_attempts "
            "WHERE outcome IS NOT NULL GROUP BY outcome")).fetchall()}
    return {
        "total": totals["total"],
        "recurrences": totals["recurrences"],
        "by_status": by_status,
        "by_outcome": by_outcome,
        "fixed": by_outcome.get("fixed", 0),
    }


async def requeue_proofs_for_chain(chain_id: int) -> int:
    """Return confirmed proofs for an ephemeral chain to 'pending' so they can be re-submitted.

    The in-process EVM is wiped on every restart while these rows survive, so without this
    a previously confirmed proof would silently stop verifying. Attempts reset to 0 — a
    chain reset is not the proof's fault and must not eat its retry budget. Dead-lettered
    entries are left alone.
    """
    async with get_conn() as conn:
        cur = await conn.execute(
            """UPDATE proof_outbox
               SET status='pending', attempts=0, next_attempt_at=0,
                   tx_hash=NULL, block_number=NULL, last_error=NULL, updated_at=?
               WHERE status='confirmed' AND chain_id=?
               RETURNING task_id""",
            (_now(), chain_id),
        )
        rows = await cur.fetchall()
        await conn.commit()
        return len(rows)


# ── Identity: users and sessions ────────────────────────────────────────────────

#: Owns goals that existed before authentication did, and everything `demo_seed` mints.
LEGACY_USER_ID = "usr_legacy_demo"
#: Owns Mergit's own self-heal goals. Its GitHub identity is a configured token, not a
#: broker connection — self-heal files issues on Mergit's repo as Mergit, not as a user.
SYSTEM_USER_ID = "usr_mergit_system"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:26]}"


async def upsert_user(
    google_sub: str,
    email: str,
    email_verified: bool,
    name: str = "",
    picture: str = "",
    is_admin: bool = False,
) -> dict:
    """Find or create the user behind an OIDC `sub`, and refresh their profile.

    Keyed on `google_sub`, never on email. Emails get reassigned inside an organisation
    and people change theirs; `sub` is the stable, immutable identifier Google promises.
    Keying on email would let a reassigned address inherit the previous holder's stored
    GitHub and Slack tokens.

    `is_admin` is recomputed from config on **every** login, so removing an address from
    ADMIN_EMAILS revokes it at the next sign-in rather than requiring a DB edit.
    """
    now = _now()
    async with get_conn() as conn:
        row = await (
            await conn.execute("SELECT * FROM users WHERE google_sub=?", (google_sub,))
        ).fetchone()
        if row:
            await conn.execute(
                """UPDATE users SET email=?, email_verified=?, name=?, picture=?,
                                    is_admin=?, last_seen_at=?
                   WHERE google_sub=?""",
                (email, int(email_verified), name, picture, int(is_admin), now, google_sub),
            )
            await conn.commit()
            user_id = row["id"]
        else:
            user_id = _new_id("usr")
            await conn.execute(
                """INSERT INTO users
                   (id, google_sub, email, email_verified, name, picture, is_admin,
                    created_at, last_seen_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (user_id, google_sub, email, int(email_verified), name, picture,
                 int(is_admin), now, now),
            )
            await conn.commit()
        fresh = await (
            await conn.execute("SELECT * FROM users WHERE id=?", (user_id,))
        ).fetchone()
    return _row_to_user(fresh)


def _row_to_user(row) -> dict:
    return {
        "id": row["id"],
        "google_sub": row["google_sub"],
        "email": row["email"],
        "email_verified": bool(row["email_verified"]),
        "name": row["name"] or "",
        "picture": row["picture"] or "",
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
        "last_seen_at": row["last_seen_at"],
    }


async def get_user(user_id: str) -> dict | None:
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT * FROM users WHERE id=?", (user_id,))).fetchone()
    return _row_to_user(row) if row else None


async def create_session(user_id: str, ttl_seconds: int, user_agent: str = "",
                         ip_hash: str = "") -> tuple[str, str]:
    """Mint an opaque session. Returns (session_id, csrf_token).

    The session id IS the cookie value — 32 bytes of `secrets.token_urlsafe`, meaningless
    on its own and only resolvable against this table. That is the point: a stolen cookie
    stops working the moment the row is revoked, which a self-contained JWT cannot offer.

    The CSRF token is minted with it and handed to the SPA by `GET /api/auth/me`, never
    set as a readable cookie.
    """
    import secrets
    now = _now()
    session_id = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO sessions
               (id, user_id, csrf_token, user_agent, ip_hash, created_at, expires_at)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, user_id, csrf, user_agent[:200], ip_hash, now, now + ttl_seconds),
        )
        await conn.commit()
    return session_id, csrf


async def load_session(session_id: str) -> dict | None:
    """Resolve a cookie to its user, or None. Expired and revoked both read as absent."""
    now = _now()
    async with get_conn() as conn:
        row = await (
            await conn.execute(
                """SELECT s.id AS sid, s.csrf_token, s.expires_at, s.revoked_at, u.*
                   FROM sessions s JOIN users u ON u.id = s.user_id
                   WHERE s.id=?""",
                (session_id,),
            )
        ).fetchone()
    if not row or row["revoked_at"] is not None or row["expires_at"] < now:
        return None
    user = _row_to_user(row)
    user["session_id"] = row["sid"]
    user["csrf_token"] = row["csrf_token"]
    return user


async def revoke_session(session_id: str) -> None:
    """Logout, server-side. Deleting the client cookie alone leaves a captured copy valid."""
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
            (_now(), session_id),
        )
        await conn.commit()


async def revoke_user_sessions(user_id: str) -> int:
    """Sign a user out everywhere — used when a connection is revoked under suspicion."""
    async with get_conn() as conn:
        cur = await conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (_now(), user_id),
        )
        await conn.commit()
        return cur.rowcount


async def purge_expired_sessions() -> int:
    """Housekeeping. Rows are kept until expiry so `revoked_at` stays meaningful."""
    async with get_conn() as conn:
        cur = await conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
        await conn.commit()
        return cur.rowcount
