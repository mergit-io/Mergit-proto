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

logger = logging.getLogger(__name__)

AGENT_DESCRIPTIONS = """
Available agents (choose from these only):

- researcher: Searches the web, reads GitHub repos, reads PR diffs, gathers facts.
  Tools: web_search, http_request, github_read_file, github_list_dir, github_get_issue, github_search_code, github_get_pr, github_get_pr_files, github_list_prs
  Output: {{"summary": str, "key_points": [str], "sources": [str], "code_context": str}}
  NOTE: outputs raw structured data — NOT a human-readable report on its own.
  Use for: web research, reading GitHub repos/files/issues, reading the DIFF of a pull request
  (github_get_pr_files) before anyone reviews or merges it, understanding codebases.

- writer: Synthesizes research or API data into polished, human-readable text (profiles, reports, emails, docs, code reviews).
  Tools: file_ops
  Output: {{"text": str, "title": str}}
  NOTE: use this as the terminal agent whenever the goal is to produce a report or readable summary.

- coder: Writes and executes Python code, reads GitHub files for context, saves results to files.
  Tools: code_exec, file_ops, web_search, github_read_file
  Output: {{"code": str, "output": str, "success": bool}}
  Use for: writing code fixes, running scripts, generating patches.

- integrator: Performs every WRITE action on GitHub — opens/updates/reviews/merges PRs, opens/closes/labels issues, creates repos, manages Actions workflows and branch protection — plus other external APIs and webhooks.
  Tools: github_pr, github_merge_pr, github_review_pr, github_request_review, github_update_pr, github_get_pr, github_get_pr_files, github_list_prs, github_create_issue, github_close_issue, github_add_labels, github_post_comment, github_read_file, github_create_repo, github_list_workflows, github_get_branch_protection, github_set_branch_protection, http_request, wait_webhook
  Output: {{"action": str, "result": any, "url": str|null}}
  NOTE: outputs raw API data — NOT a human-readable report on its own.
  Use for: shipping a new project as its own repo (github_create_repo), creating PRs, MERGING PRs, submitting PR reviews, opening/closing/labelling issues, posting comments, adding/updating CI workflows, setting branch protection rules.
  For "build X and ship it as a new repo" goals use the pattern: coder writes+tests the app -> integrator calls github_create_repo with all files.
  For "add a CI workflow" goals: researcher reads existing workflows -> coder writes the YAML -> integrator creates PR with the new .github/workflows/file.yml.
  For "set branch protection" goals: integrator calls github_set_branch_protection directly (no coder needed).
  For "merge PR #N" goals: integrator calls github_get_pr then github_merge_pr directly (no coder needed).
  MERGE SAFETY: github_merge_pr refuses to merge a PR with conflicts, failing/pending CI checks,
  requested changes, an unmet required review, or draft status, and returns the blocking reason.
  A refusal is a legitimate final outcome — plan for it being reported, never for it being retried
  or worked around.
  NOTE: All agents have access to spawn_goal — they can autonomously create new goals when they discover
  work beyond their current task scope.
"""

SYSTEM_PROMPT = f"""You are the Mergit orchestrator. Given a user goal, decompose it into the minimum set of tasks that achieves the goal, expressed as a directed acyclic graph (DAG).

CRITICAL: You MUST always call submit_plan with a valid tasks list and terminal field. Even if the goal is a long document or problem statement, extract the core actionable intent and build a plan around it. Never return reasoning only — always produce tasks + terminal.

{AGENT_DESCRIPTIONS}

Rules:
1. Output ONLY through the submit_plan function — no prose.
1b. PRESERVE THE USER'S CONSTRAINTS. The user's wording often carries requirements that are
   not part of the subject matter — carry every one of them into the task that must satisfy it,
   restated explicitly in that task's `description` or `inputs`. Never drop or paraphrase them away.
   Watch for:
   - format constraints — "as bullet points", "a table", "JSON", "one paragraph"
   - length constraints — "4 bullets", "under 200 words", "keep it short"
   - scope constraints — a specific angle such as "…and why a SERVER would enable it"
   - exclusions — "no web search", "don't use library X", "don't touch file Y"
   - tone/audience — "for a beginner", "formal"
   A format or length constraint belongs on the TERMINAL task, because that is the output the
   user actually reads. A scope constraint belongs on the task that gathers the material.
   Example — goal: "Explain X and why a server would use it. 4 short bullet points, no web search."
     researcher: "Research X, focusing specifically on why a server application would enable it.
                  Use your own knowledge — do not call web_search."
     writer:     "Write the explanation as EXACTLY 4 short bullet points, covering what X is and
                  why a server application would enable it." (terminal)
2. Tasks must form a valid DAG (no cycles, no self-references in depends_on).
3. Reference prior task output in downstream inputs:
   - Whole output object: {{{{task_id.output}}}}  ← use this when handing raw API/research data to a writer
   - Specific field:      {{{{task_id.output.field_name}}}}
   - Example: researcher produces {{summary, key_points, sources, code_context}}; coder input can be {{{{t1.output.code_context}}}} for the code snippets.
   - For integrator → writer handoff, ALWAYS use {{{{t1.output}}}} (whole object).
   - For researcher → coder handoff, use {{{{t1.output.code_context}}}} for the code snippets and {{{{t1.output.summary}}}} for context.
4. Assign task IDs as t1, t2, t3... in topological order (t1 has no dependencies).
5. terminal = the task whose output IS the final answer to the goal.
6. Use the fewest tasks possible. A single-agent task is fine for simple goals.
7. Do not invent agent names — only use the agents listed above.
8. CRITICAL — terminal task MUST produce human-readable output:
   - researcher and integrator produce raw structured data, not readable reports.
   - Whenever the goal involves fetching data, looking something up, or producing a report/summary,
     ALWAYS add a writer task after researcher/integrator to present findings as polished text.
   - Only make researcher or integrator terminal if the user explicitly asks for raw data or JSON.
   - Decision guide: "fetch/get/look up X" → integrator/researcher then writer.
     "summarise/report on X" → researcher then writer. "run a script" → coder is fine as terminal.
     "send a Slack message" → notifier is fine as terminal.
     "fix a GitHub issue" → researcher (reads code) → coder (writes fix) → integrator (creates PR + posts comment).
     "review a GitHub PR" → researcher (github_get_pr_files — reads the REAL diff) → writer (writes the review) → integrator (github_review_pr submits it).
     "merge a GitHub PR" → integrator alone (github_get_pr then github_merge_pr). No researcher, no coder.
     "open an issue about X" → integrator alone (github_create_issue), or researcher → integrator when the issue needs investigation first.
9. Task inputs MUST be self-contained — include every parameter the agent needs:
   - GitHub tasks: inputs must include "repo" (owner/repo format) and relevant issue/PR numbers.
   - researcher reading GitHub: inputs must include {{"repo": "owner/repo", "issue_number": N, "task": "read the repo structure and find files related to the issue"}}.
   - coder fixing a bug: inputs must include {{"code_context": "{{{{t1.output.code_context}}}}", "issue_summary": "{{{{t1.output.summary}}}}", "repo": "owner/repo", "file_to_fix": "path/to/file.py"}}.
   - integrator creating PR: inputs must include {{"repo": "owner/repo", "issue_number": N, "fixed_code": "{{{{t2.output.code}}}}"}}.
   - integrator merging a PR: inputs must include {{"repo": "owner/repo", "pr_number": N}}.
   - researcher reading a PR: inputs must include {{"repo": "owner/repo", "pr_number": N, "task": "read the full diff of the pull request"}}.
   - web researcher: inputs must include "search_query".
   - writer: inputs must reference prior task output e.g. {{"data": "{{{{t1.output}}}}"}}.
   - A task with empty inputs {{{{}}}} has no information to act on and will fail.
10. FOR GITHUB AUTOMATION GOALS: When the goal mentions fixing an issue or reviewing a PR:
    - t1: researcher — reads repo structure, issue details, relevant files
    - t2: coder — writes the fix using the code context from t1
    - t3: integrator — creates PR with the fix AND posts a comment on the original issue/PR
    This 3-task pattern is the correct approach. The integrator is the terminal task for GitHub automation.
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


async def plan(goal: GoalRow) -> PlanSchema:

    orchestrator_model = model_config.get_model("orchestrator")
    logger.info("Orchestrator using model: %s", orchestrator_model)

    import context as ctx_store
    ctx_prompt = ctx_store.get_context_prompt()
    system_content = SYSTEM_PROMPT + ctx_prompt if ctx_prompt else SYSTEM_PROMPT

    # Truncate very long goal texts to avoid saturating the token budget before tasks are emitted
    goal_text = goal.goal_text
    if len(goal_text) > 3000:
        goal_text = goal_text[:3000] + "\n\n[...truncated for planning. Identify the core actionable goal above and build a plan for it.]"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"Goal: {goal_text}"},
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
                max_tokens=4096,
            )
            if not response.choices:
                raise ValueError("LLM returned empty response (no choices)")
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
            plan_obj = _auto_fill_deps(plan_obj)  # ensure depends_on reflects inputs templates
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
                        plan_obj = _auto_fill_deps(plan_obj)
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


_TMPL_DEP = re.compile(r"\{\{(\w+)\.output")


def _extract_template_deps(inputs: dict) -> set[str]:
    """Return task IDs referenced in {{task_id.output...}} templates anywhere in inputs."""
    deps: set[str] = set()

    def scan(v: Any) -> None:
        if isinstance(v, str):
            for m in _TMPL_DEP.finditer(v):
                deps.add(m.group(1))
        elif isinstance(v, dict):
            for vv in v.values():
                scan(vv)
        elif isinstance(v, list):
            for item in v:
                scan(item)

    scan(inputs)
    return deps


def _auto_fill_deps(plan: PlanSchema) -> PlanSchema:
    """Ensure depends_on includes every task ID referenced in inputs templates.
    The LLM sometimes forgets to list deps even when inputs clearly reference prior outputs."""
    id_set = {t.id for t in plan.tasks}
    for task in plan.tasks:
        from_templates = _extract_template_deps(task.inputs) & id_set - {task.id}
        if from_templates - set(task.depends_on):
            task.depends_on = list(set(task.depends_on) | from_templates)
            logger.debug("Auto-added deps for %s: %s", task.id, task.depends_on)
    return plan


def _rewrite_templates(inputs: dict, id_map: dict[str, str]) -> dict:
    """Replace {{old_id.output[.field]}} with {{new_id.output[.field]}} in all string values."""
    TMPL = re.compile(r"\{\{(\w+)(\.output(?:\.[\w\[\]\.0-9]+)?)\}\}")

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


_RAW_OUTPUT_AGENTS = {"researcher", "integrator"}

# A terminal integrator whose job is to CHANGE something on GitHub — merge, comment,
# review, label, close — is answering the goal, not gathering data for a writer. Wording
# the model uses for those actions, checked against the terminal task only.
_GITHUB_WRITE_VERBS = ("merge", "comment", "review", "label", "close", "reopen",
                       "approve", "pull request", "issue")


def _integrator_terminal_is_an_action(p: "PlanSchema") -> bool:
    """Return True when a terminal integrator IS the answer rather than raw data.

    Two shapes qualify:

    1. The issue-fix workflow (researcher→coder→integrator), where the integrator opens
       the PR and comments as the final act.
    2. A direct GitHub action on a named pull request or issue — "merge PR #7", "close
       issue #12". These need no coder, so shape 1 alone rejected them: the orchestrator
       burned all five attempts on a plan that was correct and the goal failed without
       ever reaching GitHub.
    """
    agent_names = {t.agent for t in p.tasks}
    if "coder" in agent_names and "integrator" in agent_names:
        return True

    terminal = next(t for t in p.tasks if t.id == p.terminal)
    if terminal.agent != "integrator":
        return False
    # Structural signal first: acting on a specific PR/issue is a side effect, not a lookup.
    if any(k in ("pr_number", "issue_number", "pull_number") for k in (terminal.inputs or {})):
        return True
    return any(v in (terminal.description or "").lower() for v in _GITHUB_WRITE_VERBS)


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
    known_agents = {"researcher", "writer", "coder", "integrator"}
    for t in p.tasks:
        if t.agent not in known_agents:
            raise ValueError(f"unknown agent '{t.agent}' in task '{t.id}'")
    # Enforce: researcher/integrator must not be terminal unless they are the only task,
    # OR it's a GitHub automation workflow (researcher → coder → integrator) where the
    # integrator creates real side-effects (PR + comment) as the final action.
    terminal_task = next(t for t in p.tasks if t.id == p.terminal)
    if terminal_task.agent in _RAW_OUTPUT_AGENTS and len(p.tasks) > 1:
        if terminal_task.agent == "integrator" and _integrator_terminal_is_an_action(p):
            return  # automation pattern: integrator is the correct terminal
        raise ValueError(
            f"terminal task '{p.terminal}' uses agent '{terminal_task.agent}' which produces raw data. "
            "Add a writer task after it to present the findings in human-readable form."
        )


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
