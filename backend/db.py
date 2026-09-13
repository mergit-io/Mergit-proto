import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite

from config import settings
from state import GoalRow, GoalStatus, MessageRow, TaskRow, TaskStatus, ToolCallRow

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


# ── Goals ──────────────────────────────────────────────────────────────────────

async def create_goal(goal_text: str) -> GoalRow:
    now = _now()
    goal_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    title = goal_text[:80] + ("…" if len(goal_text) > 80 else "")
    async with get_conn() as conn:
        await conn.execute(
            """INSERT INTO goals (id, title, goal_text, status, trace_id, created_at, updated_at)
               VALUES (?, ?, ?, 'NEW', ?, ?, ?)""",
            (goal_id, title, goal_text, trace_id, now, now),
        )
        await conn.commit()
        row = await (await conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,))).fetchone()
    return _row_to_goal(row)


async def get_goal(goal_id: str) -> GoalRow | None:
    async with get_conn() as conn:
        row = await (await conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,))).fetchone()
    return _row_to_goal(row) if row else None


async def list_goals(status: str | None = None, limit: int = 20, offset: int = 0) -> list[GoalRow]:
    async with get_conn() as conn:
        if status:
            rows = await (
                await conn.execute(
                    "SELECT * FROM goals WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                )
            ).fetchall()
        else:
            rows = await (
                await conn.execute(
                    "SELECT * FROM goals ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
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


async def settle_task(task_id: str, status: str, output: dict | None = None, error: str | None = None) -> None:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE tasks SET status=?, output=?, error=?, worker_id=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?",
            (status, json.dumps(output) if output is not None else None, error, now, task_id),
        )
        await conn.commit()


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


# ── Messages ───────────────────────────────────────────────────────────────────

async def save_message(task_id: str, role: str, content: str, sequence: int, tool_call_id: str | None = None) -> None:
    now = _now()
    msg_id = str(uuid.uuid4())
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (id, task_id, role, content, tool_call_id, sequence, created_at) VALUES (?,?,?,?,?,?,?)",
            (msg_id, task_id, role, content if isinstance(content, str) else json.dumps(content), tool_call_id, sequence, now),
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


async def settle_tool_call(ikey: str, result_json: str | None, status: str, error: str | None = None) -> None:
    now = _now()
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE tool_calls SET result_json=?, status=?, error=?, completed_at=? WHERE idempotency_key=?",
            (result_json, status, error, now, ikey),
        )
        await conn.commit()
