"""
Three asyncio loops running inside the FastAPI process:
  goal_planner_loop  — picks up NEW goals, calls orchestrator, creates task rows
  task_executor_loop — picks up READY tasks, executes via agent_runner
  reclaim_loop       — reclaims stale RUNNING tasks with expired leases
"""
import asyncio
import logging
import uuid
from typing import Any

import db
import events
import orchestrator as orch
from agent_runner import WaitingCredentialSignal, WaitingWebhookSignal, run as agent_run
from config import settings
from interpolation import resolve_inputs
from state import GoalStatus, TaskStatus
from tracing import goal_trace_context, task_span, get_active_tracer

logger = logging.getLogger(__name__)

_running = False
_worker_id = str(uuid.uuid4())


def is_running() -> bool:
    return _running


def _is_rate_limit_error(error: Exception) -> bool:
    message = str(error).lower()
    return "rate_limit" in message or "rate limit" in message or "429" in message


async def start() -> None:
    global _running
    _running = True
    asyncio.create_task(_goal_planner_loop(), name="goal_planner")
    asyncio.create_task(_task_executor_loop(), name="task_executor")
    asyncio.create_task(_reclaim_loop(), name="reclaim")
    logger.info("Worker started (id=%s)", _worker_id)


async def stop() -> None:
    global _running
    _running = False


# ── Planner ─────────────────────────────────────────────────────────────────────

async def _goal_planner_loop() -> None:
    while _running:
        try:
            goal = await db.claim_new_goal()
            if goal:
                asyncio.create_task(_plan_goal(goal), name=f"plan-{goal.id}")
        except Exception as e:
            logger.error("Goal planner error: %s", e)
        await asyncio.sleep(settings.poll_interval_seconds)


async def _plan_goal(goal: Any) -> None:
    events.emit(goal.id, "goal_status", {"status": GoalStatus.PLANNING, "goal_id": goal.id})
    # Open the root Omium trace for this entire goal.
    # All child spans (orchestrator + tasks + tools) inherit this context.
    with goal_trace_context(execution_id=goal.trace_id, goal_title=goal.title):
        try:
            await orch.run_plan(goal)
            events.emit(goal.id, "goal_status", {"status": GoalStatus.RUNNING, "goal_id": goal.id})
            logger.info("Goal %s planned successfully", goal.id)
        except Exception as e:
            logger.error("Planning failed for goal %s: %s", goal.id, e)
            await db.update_goal_status(goal.id, GoalStatus.FAILED, error=str(e))
            events.emit(goal.id, "goal_status", {"status": GoalStatus.FAILED, "goal_id": goal.id, "error": str(e)})


# ── Executor ─────────────────────────────────────────────────────────────────────

async def _task_executor_loop() -> None:
    semaphore = asyncio.Semaphore(settings.max_concurrent_tasks)
    while _running:
        try:
            task = await db.claim_ready_task(_worker_id, settings.lease_seconds)
            if task:
                asyncio.create_task(
                    _execute_with_semaphore(semaphore, task),
                    name=f"exec-{task.id}",
                )
        except Exception as e:
            logger.error("Task executor error: %s", e)
        await asyncio.sleep(settings.poll_interval_seconds)


async def _execute_with_semaphore(semaphore: asyncio.Semaphore, task: Any) -> None:
    async with semaphore:
        await _execute_task(task)


async def _execute_task(task: Any) -> None:
    goal_id = task.goal_id

    events.emit(goal_id, "task_update", {
        "task_id": task.id, "status": TaskStatus.RUNNING, "agent": task.agent_name,
    })

    def emit(event_name: str, data: dict) -> None:
        events.emit(goal_id, event_name, data)

    try:
        done_tasks = await db.list_goal_tasks(goal_id)
        task_outputs = {
            t.id: t.output
            for t in done_tasks
            if t.status == TaskStatus.DONE and t.output is not None
        }
        resolved = resolve_inputs(task.inputs, task_outputs)
    except KeyError as e:
        error_msg = f"Interpolation error: {e}"
        logger.error("Interpolation failed for task %s: %s", task.id, e)
        await db.settle_task(task.id, TaskStatus.FAILED, error=error_msg)
        events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.FAILED, "error": error_msg})
        await _handle_goal_failure(goal_id, task.id, error_msg)
        return

    # Re-enter the goal's Omium trace context so this task's spans are
    # causally linked to the same goal_run root span.
    tracer = get_active_tracer()
    if tracer is None:
        # Tracer not in context (e.g. task picked up after restart).
        # Create a fresh one scoped to this execution_id.
        goal = await db.get_goal(goal_id)
        if goal:
            _ctx = goal_trace_context(execution_id=goal.trace_id, goal_title=goal.title)
            _ctx.__enter__()
            tracer = get_active_tracer()

    try:
        with task_span(tracer, task.id, task.agent_name, task.description) as tspan:
            output = await agent_run(task, resolved, emit=emit, tracer=tracer)
            if tspan:
                tspan.set_output({"task_id": task.id, "status": "DONE"})
        await db.settle_task(task.id, TaskStatus.DONE, output=output)
        events.emit(goal_id, "task_done", {"task_id": task.id, "output": output})
        logger.info("Task %s DONE (goal=%s)", task.id, goal_id)
        await _after_task_done(task, output)

    except WaitingWebhookSignal:
        events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.WAITING_WEBHOOK})

    except WaitingCredentialSignal as e:
        events.emit(goal_id, "task_update", {
            "task_id": task.id,
            "status": TaskStatus.WAITING_CREDENTIAL,
            "credential": e.credential_var,
            "provider": e.provider,
        })

    except Exception as e:
        if _is_rate_limit_error(e):
            delay = min(2 ** max(task.attempt_count, 0), 30)
            logger.warning("Task %s rate limited; requeueing in %ds: %s", task.id, delay, e)
            await db.settle_task(task.id, TaskStatus.PENDING, error=f"Rate limited; retrying in {delay}s")
            events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.PENDING, "error": f"Rate limited; retrying in {delay}s"})
            asyncio.create_task(_requeue_task_later(task.id, goal_id, delay), name=f"rate-limit-{task.id}")
            return

        logger.error("Task %s FAILED: %s", task.id, e)
        fresh = await db.get_task(task.id)
        if fresh and fresh.attempt_count >= fresh.max_attempts:
            await db.settle_task(task.id, TaskStatus.FAILED, error=str(e))
            events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.FAILED, "error": str(e)})
            await _handle_goal_failure(goal_id, task.id, str(e))
        else:
            await db.settle_task(task.id, TaskStatus.READY, error=str(e))
            events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.READY})


async def _requeue_task_later(task_id: str, goal_id: str, delay: int) -> None:
    await asyncio.sleep(delay)
    task = await db.get_task(task_id)
    if not task or task.status != TaskStatus.PENDING:
        return
    await db.settle_task(task_id, TaskStatus.READY, error=None)
    events.emit(goal_id, "task_update", {"task_id": task_id, "status": TaskStatus.READY})


async def _after_task_done(task: Any, output: dict) -> None:
    goal = await db.get_goal(task.goal_id)
    if not goal:
        return

    promoted = await db.promote_ready_tasks(task.goal_id)
    for tid in promoted:
        events.emit(task.goal_id, "task_update", {"task_id": tid, "status": TaskStatus.READY})

    if goal.terminal_task_id == task.id:
        await db.update_goal_status(task.goal_id, GoalStatus.COMPLETED, output=output)
        events.emit(task.goal_id, "goal_done", {
            "status": GoalStatus.COMPLETED, "goal_id": task.goal_id, "output": output,
        })
        logger.info("Goal %s COMPLETED", task.goal_id)


async def _handle_goal_failure(goal_id: str, failed_task_id: str, error: str) -> None:
    await db.update_goal_status(goal_id, GoalStatus.FAILED, error=f"Task {failed_task_id} failed: {error}")
    events.emit(goal_id, "goal_status", {
        "status": GoalStatus.FAILED, "goal_id": goal_id, "error": error,
    })


# ── Reclaim ─────────────────────────────────────────────────────────────────────

async def _reclaim_loop() -> None:
    while _running:
        try:
            reclaimed = await db.reclaim_expired_leases()
            if reclaimed:
                logger.info("Reclaimed %d stale task leases", reclaimed)
            await _reclaim_orphaned_goals()
        except Exception as e:
            logger.error("Reclaim error: %s", e)
        await asyncio.sleep(30)


async def _reclaim_orphaned_goals() -> None:
    """Resolve goals stuck in RUNNING/PLANNING whose tasks are all terminal (no progress possible)."""
    orphans = await db.find_orphaned_goals()
    for row in orphans:
        gid, terminal_id, terminal_status = row["id"], row["terminal_task_id"], row["terminal_status"]
        if terminal_status == TaskStatus.DONE:
            output = row["terminal_output"]
            await db.update_goal_status(gid, GoalStatus.COMPLETED, output=output)
            events.emit(gid, "goal_done", {"status": GoalStatus.COMPLETED, "goal_id": gid, "output": output})
            logger.info("Reclaimed orphaned COMPLETED goal %s", gid)
        else:
            error = row["error"] or "All tasks failed — no progress possible"
            await db.update_goal_status(gid, GoalStatus.FAILED, error=error)
            events.emit(gid, "goal_status", {"status": GoalStatus.FAILED, "goal_id": gid, "error": error})
            logger.info("Reclaimed orphaned FAILED goal %s", gid)
