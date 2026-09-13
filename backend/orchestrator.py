import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

import db
from llm import acompletion
from state import GoalRow
from tracing import set_execution_context, trace

logger = logging.getLogger(__name__)

ORCHESTRATOR_MODEL = "anthropic/claude-sonnet-4-20250514"

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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Goal: {goal.goal_text}"},
    ]

    last_error: str | None = None
    for attempt in range(3):
        if last_error:
            messages.append({"role": "user", "content": f"Your previous plan was invalid: {last_error}. Please fix it."})

        try:
            response = await acompletion(
                model=ORCHESTRATOR_MODEL,
                messages=messages,
                tools=[PLAN_TOOL],
                tool_choice={"type": "function", "name": "submit_plan"},
                temperature=0.1,
                max_tokens=2048,
            )
            tool_call = response.choices[0].message.tool_calls[0]
            raw = json.loads(tool_call.function.arguments)
            plan_obj = PlanSchema.model_validate(raw)
            _validate_plan(plan_obj)
            logger.info("Orchestrator produced plan for goal=%s: %d tasks", goal.id, len(plan_obj.tasks))
            return plan_obj
        except (ValidationError, ValueError, KeyError) as e:
            last_error = str(e)
            logger.warning("Plan attempt %d failed: %s", attempt + 1, e)
        except Exception as e:
            logger.error("Orchestrator error on attempt %d: %s", attempt + 1, e)
            raise

    raise RuntimeError(f"Orchestrator failed after 3 attempts. Last error: {last_error}")


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
    plan_json = plan_obj.model_dump_json()
    tasks_data = [t.model_dump() for t in plan_obj.tasks]
    await db.create_tasks(tasks_data, goal.id, goal.trace_id)
    await db.set_goal_plan(goal.id, plan_json, plan_obj.terminal)
