from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoalRow:
    id: str
    title: str
    goal_text: str
    status: str
    output: Any
    error: str | None
    plan_json: str | None
    terminal_task_id: str | None
    trace_id: str
    created_at: int
    updated_at: int
    # Provenance — "user" or "self_heal". heal_depth guards against heal loops.
    source: str = "user"
    heal_depth: int = 0
    #: The owner. Every read path that serves an HTTP request must filter on it.
    #: Defaults to the legacy sentinel so a row predating the migration has an owner
    #: rather than a None that a forgotten filter would happily match.
    user_id: str = "usr_legacy_demo"
    #: Demo-seeded goals are synthetic and visible to everyone, so the proof ledger is
    #: never empty for a new user. Nothing a real user creates sets this.
    is_public: bool = False


@dataclass
class TaskRow:
    id: str
    goal_id: str
    agent_name: str
    description: str
    inputs: dict
    depends_on: list[str]
    status: str
    output: Any
    error: str | None
    attempt_count: int
    #: Claims that ended in a real exception. The retry budget checked against
    #: `max_attempts` — unlike `attempt_count`, parking on a credential or a webhook does
    #: not move it.
    failure_count: int
    max_attempts: int
    worker_id: str | None
    lease_expires_at: int | None
    wait_token: str | None
    wait_payload: Any
    idempotency_key: str
    trace_id: str
    parent_span_id: str | None
    created_at: int
    updated_at: int


@dataclass
class ToolCallRow:
    id: str
    task_id: str
    tool_name: str
    args_json: str
    args_hash: str
    result_json: str | None
    status: str
    error: str | None
    idempotency_key: str
    created_at: int
    completed_at: int | None


@dataclass
class MessageRow:
    id: str
    task_id: str
    role: str
    content: str
    tool_call_id: str | None
    sequence: int
    created_at: int


# Goal status constants
class GoalStatus:
    NEW = "NEW"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Task status constants
class TaskStatus:
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    WAITING_WEBHOOK = "WAITING_WEBHOOK"
    WAITING_CREDENTIAL = "WAITING_CREDENTIAL"
