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
from agent_runner import WaitingWebhookSignal, run as agent_run
from config import settings
from interpolation import resolve_inputs
from state import GoalStatus, TaskStatus

logger = logging.getLogger(__name__)

_running = False
_worker_id = str(uuid.uuid4())


def is_running() -> bool:
    return _running


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
        logger.error("Interpolation failed for task %s: %s", task.id, e)
        await db.settle_task(task.id, TaskStatus.FAILED, error=f"Interpolation error: {e}")
        events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.FAILED})
        return

    try:
        output = await agent_run(task, resolved, emit=emit)
        await db.settle_task(task.id, TaskStatus.DONE, output=output)
        events.emit(goal_id, "task_done", {"task_id": task.id, "output": output})
        logger.info("Task %s DONE (goal=%s)", task.id, goal_id)
        await _after_task_done(task, output)

    except WaitingWebhookSignal:
        # Already handled inside agent_run (status set to WAITING_WEBHOOK in DB)
        events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.WAITING_WEBHOOK})

    except Exception as e:
        logger.error("Task %s FAILED: %s", task.id, e)
        fresh = await db.get_task(task.id)
        if fresh and fresh.attempt_count >= fresh.max_attempts:
            await db.settle_task(task.id, TaskStatus.FAILED, error=str(e))
            events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.FAILED, "error": str(e)})
            await _handle_goal_failure(goal_id, task.id, str(e))
        else:
            await db.settle_task(task.id, TaskStatus.READY, error=str(e))
            events.emit(goal_id, "task_update", {"task_id": task.id, "status": TaskStatus.READY})


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
        except Exception as e:
            logger.error("Reclaim error: %s", e)
        await asyncio.sleep(30)
