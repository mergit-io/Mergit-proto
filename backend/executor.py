"""The interleaved executor: one goal, one context, decide the next step from the last result.

Why this exists
---------------
The DAG executor commits to a complete plan before any tool has run. It plans from the
goal text alone, knowing nothing about the repository it is about to change, and once the
plan is written nothing may revise it. Every real-world prompt shape therefore has to be
anticipated in the orchestrator's system prompt, which is why that prompt is eighty lines
of per-scenario recipes — "fix a GitHub issue" -> researcher/coder/integrator, "merge a
PR" -> integrator alone, "the segment after /tree/ is a branch name". Each line is a scar.
A prompt off that list gets a plan that is wrong in a way no rule covers yet.

Goal e6b9529c is the clean example. The plan ended with a coder task placed after the pull
request, told to prove the fix by running it. It read the file from the default branch
rather than the branch just pushed, so it reported the code as it was BEFORE the fix, and
being terminal that became the goal's answer. Nothing in the run could notice, because the
step had been decided before the first tool call.

The loop makes the plan an artifact of execution rather than a precondition for it. One
context accumulates every tool result, the model chooses each next action having seen the
last one, and `update_plan` lets it rewrite its own checklist as it learns. That is how
Claude Code and Codex work, and it is the difference between a system that follows a
recipe and one that follows the goal.

What is deliberately kept
-------------------------
The loop runs as an ordinary task row, so leases, the reclaim sweep, retries and
idempotency keys all apply unchanged — none of which a coding agent normally has. The
honesty guards run on `finish` exactly as they run on `submit_result`, so an agent still
cannot claim work it did not do. Writes are still capped per task, and approvals still
gate the irreversible ones.

Not yet here
------------
Proofs, and the subagent dispatch they depend on. `economy.ROLES` lists the six specialist
roles and `operator` is not one of them, so `record_proof` declines a loop run and it mints
NOTHING — no proof, no reputation movement, no ledger row. That is not an oversight to
paper over by adding `operator` to the list: a proof is meant to record a specialist doing
a unit of work, and "the whole goal" is not that. The fix is dispatching the specialists as
subagents so each of their steps mints its own proof, which is the next commit.

Until then a loop run is invisible to the agent economy, and that alone is reason enough
for EXECUTOR_MODE to default to "dag".
"""
import json
import logging
import time
from typing import Any

import db
from agent_runner import (
    WRITE_TOOL_CALL_CAP,
    _build_tool_defs,
    _collect_urls,
    _execute_tool_idempotent,
    _idempotency_key,
    _over_write_cap,
    _submission_problem,
)
from config import settings
from llm import acompletion
from tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)


UPDATE_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "update_plan",
        "description": (
            "Record or revise your checklist for this goal. Call it early with your first "
            "read of the work, and again whenever what you learn changes the plan — a step "
            "that turned out to be unnecessary, a step you did not know you needed, or one "
            "you have just completed. Revising is expected, not a sign of a bad first plan."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "The full checklist, in order. Send all items every time.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string", "description": "What this step does"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "done", "dropped"],
                            },
                            "note": {
                                "type": "string",
                                "description": "Why it changed, if it changed",
                            },
                        },
                        "required": ["step", "status"],
                    },
                }
            },
            "required": ["items"],
        },
    },
}

FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": (
            "End the run. Call this only when the goal is achieved, or when you are certain "
            "it cannot be — say which. Everything you claim here is checked against what "
            "your tools actually returned."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "What you did, in plain language, for the person who asked.",
                },
                "url": {
                    "type": "string",
                    "description": "The artifact this run produced, if it produced one.",
                },
                "succeeded": {
                    "type": "boolean",
                    "description": "False when the goal was not achieved. Say so plainly.",
                },
            },
            "required": ["summary"],
        },
    },
}

#: The loop ends on whichever comes first. Turns bound a model that keeps calling tools
#: without converging; the deadline bounds one whose tools are individually slow. Neither
#: alone is enough: 60 fast reads and one 15-minute wait are both runaway runs.
_DEFAULT_MAX_TURNS = 60
_DEFAULT_DEADLINE_SECONDS = 900


SYSTEM_PROMPT = """You are Mergit's executor. You are given one goal and the tools to achieve it.

How to work:
- Decide your next action from what the last one returned. Do not plan the whole run up front — you do not yet know what you will find.
- Call `update_plan` early with your first read of the work, and again whenever what you learn changes it. A plan that never changes usually means you stopped paying attention.
- Read before you write. Look at the actual file, issue or diff rather than assuming its shape from its name.
- Verify BEFORE you ship, never after. Anything you discover after opening a pull request arrives too late to change it.
- When a tool fails, read the error and adapt. A failure is information about the world, not a reason to stop.
- Call `finish` when the goal is achieved, or when you are certain it cannot be — and if it cannot be, say so plainly rather than submitting something adjacent and calling it done.

What is checked:
Everything you claim in `finish` is compared against what your tools actually returned. A URL you did not receive from a tool, a success you did not achieve, a failed tool result presented as an outcome — each is rejected and handed back to you. Claiming the work is a longer road than doing it.
"""


def _plan_block(plan_items: list[dict]) -> str:
    """The current checklist, as the model should see it on every turn."""
    if not plan_items:
        return ""
    mark = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "dropped": "[-]"}
    lines = [f"{mark.get(i.get('status'), '[ ]')} {i.get('step', '')}"
             + (f"  ({i['note']})" if i.get("note") else "")
             for i in plan_items]
    return "Your current plan:\n" + "\n".join(lines)


async def run_loop(task: Any, resolved_inputs: dict, emit=None) -> dict:
    """Run one goal to completion in a single accumulating context.

    Returns the `finish` payload. Raises on budget exhaustion, which the worker treats
    like any other task failure — retry, then replan, then fail the goal.
    """
    goal = await db.get_goal(task.goal_id)
    goal_text = goal.goal_text if goal else task.description

    # Every registered tool, which is the point — the loop is not told in advance which
    # ones this goal needs. Iterating the registry also respects demo_safe_mode, which
    # unregisters code_exec rather than filtering it downstream.
    tool_defs = [d for d in _build_tool_defs(list(TOOL_REGISTRY))
                 if d["function"]["name"] != "submit_result"]
    tool_defs.extend([UPDATE_PLAN_TOOL, FINISH_TOOL])

    model = settings.executor_model or "openrouter/openai/gpt-4.1"
    max_turns = settings.loop_max_turns or _DEFAULT_MAX_TURNS
    deadline = time.monotonic() + (settings.loop_deadline_seconds or _DEFAULT_DEADLINE_SECONDS)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Goal: {goal_text}"},
    ]
    if resolved_inputs:
        messages.append({"role": "user",
                         "content": "Context provided with the goal:\n"
                                    + json.dumps(resolved_inputs, indent=2)[:4000]})

    plan_items: list[dict] = []
    known_urls: set[str] = set(_collect_urls(resolved_inputs)) | set(_collect_urls(goal_text))
    write_calls: dict[str, int] = {}
    last_problem: str | None = None

    logger.info("[goal=%s] loop start (model=%s max_turns=%d)", task.goal_id, model, max_turns)

    for turn in range(max_turns):
        if time.monotonic() > deadline:
            raise RuntimeError(
                f"the run passed its {settings.loop_deadline_seconds or _DEFAULT_DEADLINE_SECONDS}s "
                f"deadline after {turn} turns")

        response = await acompletion(role="operator", model=model, messages=messages,
                                     tools=tool_defs, tool_choice="auto")
        msg = response.choices[0].message
        content = msg.content or ""
        if content:
            await db.save_message(task.id, "assistant", content, sequence=len(messages))
            if emit:
                emit("message", {"task_id": task.id, "role": "assistant", "content": content})

        if not msg.tool_calls:
            # Nothing called and nothing finished. Say what is missing rather than ending
            # the run — an empty turn is the model thinking out loud, not a conclusion.
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": (
                "That turn called no tool. Either take the next action, or call `finish` "
                "if the goal is achieved or cannot be.")})
            continue

        messages.append({"role": "assistant", "content": content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})

        for tc in msg.tool_calls:
            name = tc.function.name
            raw = tc.function.arguments
            try:
                args = json.loads(raw)
            except json.JSONDecodeError as exc:
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(
                    {"ok": False, "error": f"arguments were not valid JSON ({exc})"})})
                continue

            if name == "update_plan":
                plan_items = args.get("items") or []
                if emit:
                    emit("plan_update", {"task_id": task.id, "items": plan_items})
                logger.info("[goal=%s] plan: %d items", task.goal_id,
                            len(plan_items))
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps({"ok": True, "items": len(plan_items)})})
                continue

            if name == "finish":
                result = {k: v for k, v in args.items() if v is not None}
                problem = _submission_problem(result, ["summary"], goal_text, known_urls)
                if problem is None:
                    logger.info("[goal=%s] finished after %d turns", task.goal_id, turn + 1)
                    if plan_items:
                        result["plan"] = plan_items
                    return result
                last_problem = problem
                logger.warning("[goal=%s] finish rejected: %s", task.goal_id, problem[:160])
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps({"ok": False, "error": problem})})
                continue

            if name not in TOOL_REGISTRY:
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(
                    {"ok": False, "error": f"unknown tool {name!r}"})})
                continue

            capped = _over_write_cap(name, write_calls)
            if capped is not None:
                logger.warning("[goal=%s] %s refused — cap", task.goal_id, name)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps({"ok": False, "error": capped})})
                continue

            if emit:
                emit("tool_call", {"task_id": task.id, "tool": name, "args": args})
            ikey = _idempotency_key(task.id, name, raw)
            result = await _execute_tool_idempotent(task, name, raw, args, ikey)
            if name in WRITE_TOOL_CALL_CAP and not (isinstance(result, dict) and result.get("error")):
                write_calls[name] = write_calls.get(name, 0) + 1

            known_urls.update(_collect_urls(result))
            if emit:
                emit("tool_result", {"task_id": task.id, "tool": name,
                                     "status": "ERROR" if isinstance(result, dict) and result.get("error") else "SUCCESS"})
            body = json.dumps(result)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": body})
            await db.save_message(task.id, "tool", body, sequence=len(messages), tool_call_id=tc.id)

        if plan_items and turn % 5 == 4:
            # Re-showing the checklist keeps it in view on a long run, where the original
            # update_plan call has scrolled far up the context.
            messages.append({"role": "user", "content": _plan_block(plan_items)})

    raise RuntimeError(
        f"the run used all {max_turns} turns without finishing"
        + (f"; the last finish attempt was rejected because {last_problem}" if last_problem else "")
    )
