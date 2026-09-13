"""
Dynamic replanning: when a task fails at max_attempts, ask the orchestrator
to devise an alternative plan using what's already been completed.

This gives the system true autonomy — instead of giving up, it reasons
about the failure and finds a different path to the goal.
"""
import json
import logging

import db
import model_config
from llm import acompletion
from orchestrator import PlanSchema, PLAN_TOOL, _auto_fill_deps, _validate_plan, _rewrite_templates
from state import TaskStatus

logger = logging.getLogger(__name__)

_MAX_REPLAN_ATTEMPTS = 1  # replan at most once per goal to avoid infinite loops


async def should_replan(goal_id: str) -> bool:
    """Return True if this goal hasn't already been replanned."""
    goal = await db.get_goal(goal_id)
    if not goal:
        return False
    # Store replan count in goal error field prefix (lightweight flag)
    error = goal.error or ""
    return "[replanned]" not in error


async def attempt_replan(goal_id: str, failed_task_id: str, failure_error: str) -> bool:
    """
    Try to replan the goal around the failed task.
    Returns True if replanning succeeded and new tasks were inserted.
    """
    goal = await db.get_goal(goal_id)
    if not goal:
        return False

    all_tasks = await db.list_goal_tasks(goal_id)
    done_tasks = [t for t in all_tasks if t.status == TaskStatus.DONE]
    failed_task = next((t for t in all_tasks if t.id == failed_task_id), None)

    if not failed_task:
        return False

    # Summarise what has been completed so far
    completed_summary = ""
    for t in done_tasks:
        out = json.dumps(t.output)[:300] if t.output else "no output"
        completed_summary += f"- [{t.agent_name}] {t.description}: {out}\n"

    replan_prompt = (
        f"Original goal: {goal.goal_text}\n\n"
        f"Progress so far (already completed — do NOT redo these):\n"
        f"{completed_summary or 'Nothing completed yet.'}\n\n"
        f"Failed task: [{failed_task.agent_name}] {failed_task.description}\n"
        f"Failure reason: {failure_error[:500]}\n\n"
        "The above task failed. Create a NEW plan to complete the REMAINING work. "
        "Do not include tasks that already completed. "
        "Use a different approach if the same approach is likely to fail again. "
        "If the failure is unrecoverable, produce a single writer task that summarises "
        "what was accomplished and why the goal could not be fully completed."
    )

    orchestrator_model = model_config.get_model("orchestrator")
    messages = [
        {"role": "system", "content": (
            "You are the omniBox orchestrator. A task in the current plan has failed. "
            "Replan the remaining work to complete the goal. "
            "Output ONLY through the submit_plan function."
        )},
        {"role": "user", "content": replan_prompt},
    ]

    try:
        response = await acompletion(
            model=orchestrator_model,
            messages=messages,
            tools=[PLAN_TOOL],
            tool_choice={"type": "function", "function": {"name": "submit_plan"}},
            temperature=0.1,
            max_tokens=2048,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            return False

        import json as _json
        raw = _json.loads(msg.tool_calls[0].function.arguments)
        new_plan = PlanSchema.model_validate(raw)
        new_plan = _auto_fill_deps(new_plan)
        _validate_plan(new_plan)
    except Exception as e:
        logger.warning("Replanning failed for goal %s: %s", goal_id, e)
        return False

    # Prefix new task IDs so they don't clash with original IDs
    prefix = f"{goal_id[:8]}_r"
    id_map = {t.id: f"{prefix}_{t.id}" for t in new_plan.tasks}

    # Build completed task ID set for dependency resolution
    done_ids = {t.id for t in done_tasks}

    tasks_data = []
    for t in new_plan.tasks:
        td = t.model_dump()
        td["id"] = id_map[t.id]
        # Remap deps to new IDs; if dep refers to a done task, skip it (already done)
        td["depends_on"] = [id_map[dep] for dep in t.depends_on if dep in id_map]
        td["inputs"] = _rewrite_templates(td.get("inputs", {}), id_map)
        tasks_data.append(td)

    new_terminal = id_map[new_plan.terminal]

    # Insert new tasks and update the goal's terminal pointer
    await db.create_tasks(tasks_data, goal_id, goal.trace_id)
    await db.set_goal_plan(goal_id, goal.plan_json or "{}", new_terminal)

    # Mark goal as still running (not failed) and flag it as replanned
    await db.update_goal_status(goal_id, "RUNNING",
                                error=f"[replanned] Previous attempt failed: {failure_error[:200]}")

    logger.info(
        "Replanned goal %s: %d new tasks (terminal=%s)",
        goal_id, len(tasks_data), new_terminal,
    )
    return True
