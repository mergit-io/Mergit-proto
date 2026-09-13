import asyncio
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError

import db
import model_config
from llm import acompletion
from state import GoalRow
from tracing import set_execution_context, trace

logger = logging.getLogger(__name__)

AGENT_DESCRIPTIONS = """
Available agents (choose from these only):

- researcher: Searches the web, reads URLs, gathers facts.
  Tools: web_search, http_request
  Output: {"summary": str, "key_points": [str], "sources": [str]}

- writer: Synthesizes research into polished text (reports, emails, docs).
  Tools: file_ops
  Output: {"text": str, "title": str}

- notifier: Sends messages to Slack or any HTTP endpoint.
  Tools: slack_notify, http_request
  Output: {"sent": bool, "destination": str}

- coder: Writes and executes Python code, saves results to files.
  Tools: code_exec, file_ops, web_search
  Output: {"code": str, "output": str, "success": bool}

- integrator: Interacts with external APIs, creates GitHub PRs, waits for inbound webhooks.
  Tools: github_pr, http_request, wait_webhook
  Output: {"action": str, "result": any, "url": str|null}
"""

SYSTEM_PROMPT = f"""You are the omniBox orchestrator. Given a user goal, decompose it into the minimum set of tasks that achieves the goal, expressed as a directed acyclic graph (DAG).

{AGENT_DESCRIPTIONS}

Rules:
1. Output ONLY through the submit_plan function — no prose.
2. Tasks must form a valid DAG (no cycles, no self-references in depends_on).
3. Reference a prior task's output field as: {{{{task_id.output.field_name}}}}
   Example: if task t1 outputs {{summary: "...", key_points: [...]}}, then t2's input can be {{{{t1.output.summary}}}}
4. Assign task IDs as t1, t2, t3... in topological order (t1 has no dependencies).
5. terminal = the task whose output IS the final answer to the goal.
6. Use the fewest tasks possible. A single-agent task is fine for simple goals.
7. Do not invent agent names — only use the agents listed above.
"""


class TaskSpec(BaseModel):
    id: str
    agent: str
    description: str
    inputs: dict[str, Any] = {}
    depends_on: list[str] = []


class PlanSchema(BaseModel):
    tasks: list[TaskSpec]
    terminal: str
    reasoning: str


PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": "Submit the decomposed task execution plan as a DAG.",
        "parameters": PlanSchema.model_json_schema(),
    },
}


@trace("orchestrator_plan")
async def plan(goal: GoalRow) -> PlanSchema:
    set_execution_context(execution_id=goal.trace_id, agent_id="orchestrator")

    orchestrator_model = model_config.get_model("orchestrator")
    logger.info("Orchestrator using model: %s", orchestrator_model)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Goal: {goal.goal_text}"},
    ]

    last_error: str | None = None
    max_attempts = 5
    for attempt in range(max_attempts):
        if last_error and "invalid" in last_error.lower():
            messages.append({"role": "user", "content": f"Your previous plan was invalid: {last_error}. Please fix it."})

        # Use forced tool_choice on early attempts; fall back to auto on later retries
        # (Groq sometimes fails forced tool_choice with tool_use_failed)
        tc = (
            {"type": "function", "function": {"name": "submit_plan"}}
            if attempt < 2
            else "auto"
        )
        try:
            response = await acompletion(
                model=orchestrator_model,
                messages=messages,
                tools=[PLAN_TOOL],
                tool_choice=tc,
                temperature=0.1,
                max_tokens=2048,
            )
            msg = response.choices[0].message
            if msg.tool_calls:
                raw = json.loads(msg.tool_calls[0].function.arguments)
            elif msg.content:
                # Groq may return JSON in message body instead of a tool call
                m = re.search(r"\{.*\}", msg.content, re.DOTALL)
                if not m:
                    raise ValueError("No tool call and no JSON in orchestrator response")
                raw = json.loads(m.group(0))
                logger.warning("Orchestrator (attempt %d): parsed plan from message body (no tool call)", attempt + 1)
            else:
                raise ValueError("Empty orchestrator response")
            plan_obj = PlanSchema.model_validate(raw)
            _validate_plan(plan_obj)
            logger.info("Orchestrator produced plan for goal=%s: %d tasks (model=%s)",
                        goal.id, len(plan_obj.tasks), orchestrator_model)
            return plan_obj
        except (ValidationError, ValueError, KeyError) as e:
            last_error = str(e)
            logger.warning("Plan attempt %d/%d validation error: %s", attempt + 1, max_attempts, e)
        except Exception as e:
            err_str = str(e).lower()
            if "rate_limit" in err_str or "429" in err_str or "rate limit" in err_str:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                logger.warning("Orchestrator rate limited (attempt %d/%d) — retrying in %ds",
                               attempt + 1, max_attempts, wait)
                await asyncio.sleep(wait)
                last_error = str(e)
                continue
            # Groq tool_use_failed: model generated plan in XML-function format.
            # The actual JSON is in failed_generation — try to salvage it.
            if "tool_use_failed" in err_str or "failed_generation" in str(e):
                salvaged = _salvage_failed_generation(str(e))
                if salvaged:
                    try:
                        plan_obj = PlanSchema.model_validate(salvaged)
                        _validate_plan(plan_obj)
                        logger.warning(
                            "Orchestrator (attempt %d): salvaged plan from failed_generation", attempt + 1
                        )
                        return plan_obj
                    except (ValidationError, ValueError, KeyError) as pe:
                        last_error = f"tool_use_failed + salvage parse error: {pe}"
                        logger.warning("Salvage parse failed: %s", pe)
                        continue
                last_error = str(e)
                logger.warning("Orchestrator tool_use_failed (attempt %d/%d), retrying with tool_choice=auto",
                               attempt + 1, max_attempts)
                continue
            logger.error("Orchestrator error on attempt %d: %s", attempt + 1, e)
            raise

    raise RuntimeError(f"Orchestrator failed after {max_attempts} attempts. Last error: {last_error}")


def _rewrite_templates(inputs: dict, id_map: dict[str, str]) -> dict:
    """Replace {{old_id.output.field}} with {{new_id.output.field}} in all string values."""
    TMPL = re.compile(r"\{\{(\w+)(\.output\.[\w\[\]\.0-9]+)\}\}")

    def rewrite(v: Any) -> Any:
        if isinstance(v, str):
            return TMPL.sub(lambda m: "{{" + id_map.get(m.group(1), m.group(1)) + m.group(2) + "}}", v)
        if isinstance(v, dict):
            return {k: rewrite(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [rewrite(item) for item in v]
        return v

    return {k: rewrite(v) for k, v in inputs.items()}


def _salvage_failed_generation(error_str: str) -> dict | None:
    """Extract plan JSON from Groq's failed_generation XML-function format."""
    # Groq embeds the generation as: <function=submit_plan> {...} </function>
    m = re.search(r"<function=\w+>\s*(\{.*\})\s*</function>", error_str, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Also try extracting from the failed_generation JSON field value
    m = re.search(r'"failed_generation"\s*:\s*"(.*?)"(?:,|\})', error_str, re.DOTALL)
    if m:
        try:
            unescaped = m.group(1).encode("utf-8").decode("unicode_escape")
            inner = re.search(r"<function=\w+>\s*(\{.*\})\s*</function>", unescaped, re.DOTALL)
            if inner:
                return json.loads(inner.group(1))
        except Exception:
            pass
    return None


def _validate_plan(p: PlanSchema) -> None:
    ids = {t.id for t in p.tasks}
    if p.terminal not in ids:
        raise ValueError(f"terminal '{p.terminal}' not in task ids {ids}")
    for t in p.tasks:
        for dep in t.depends_on:
            if dep not in ids:
                raise ValueError(f"task '{t.id}' depends on unknown task '{dep}'")
        if t.id in t.depends_on:
            raise ValueError(f"task '{t.id}' depends on itself")
    known_agents = {"researcher", "writer", "notifier", "coder", "integrator"}
    for t in p.tasks:
        if t.agent not in known_agents:
            raise ValueError(f"unknown agent '{t.agent}' in task '{t.id}'")


async def run_plan(goal: GoalRow) -> None:
    """Plan a goal and persist the tasks to the database."""
    plan_obj = await plan(goal)

    # Make task IDs globally unique: prefix with first 8 chars of goal_id.
    # The orchestrator uses short IDs like t1, t2 internally; they clash across goals.
    prefix = goal.id[:8]
    id_map = {t.id: f"{prefix}_{t.id}" for t in plan_obj.tasks}

    tasks_data = []
    for t in plan_obj.tasks:
        td = t.model_dump()
        td["id"] = id_map[t.id]
        td["depends_on"] = [id_map[dep] for dep in t.depends_on]
        # Rewrite {{t1.output.field}} → {{prefix_t1.output.field}} in all input strings
        td["inputs"] = _rewrite_templates(td.get("inputs", {}), id_map)
        tasks_data.append(td)

    terminal_global = id_map[plan_obj.terminal]

    plan_json = plan_obj.model_dump_json()
    await db.create_tasks(tasks_data, goal.id, goal.trace_id)
    await db.set_goal_plan(goal.id, plan_json, terminal_global)
