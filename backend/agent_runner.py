"""
Generic LLM tool-call loop. Works for any agent config from AGENT_REGISTRY.
Handles idempotent tool execution and SSE event emission.
"""
import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any, Callable

import db
from agent_registry import AGENT_REGISTRY, get_agent_config
from llm import acompletion
from state import TaskRow
from tools import TOOL_REGISTRY
from tools.wait_webhook import WAITING_WEBHOOK_SENTINEL
from tracing import set_execution_context, trace, tool_span

logger = logging.getLogger(__name__)

SUBMIT_RESULT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_result",
        "description": "Submit your final structured result. Call this when you have completed the task.",
        "parameters": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "object",
                    "description": "The structured result matching the expected output schema.",
                }
            },
            "required": ["result"],
        },
    },
}


def _build_tool_defs(allowed_tools: list[str]) -> list[dict]:
    defs = []
    for name in allowed_tools:
        if name not in TOOL_REGISTRY:
            continue
        entry = TOOL_REGISTRY[name]
        defs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": entry.schema.get("description", name),
                "parameters": {k: v for k, v in entry.schema.items() if k != "description"},
            },
        })
    defs.append(SUBMIT_RESULT_TOOL)
    return defs


def _idempotency_key(task_id: str, tool_name: str, args_json: str, attempt: int) -> str:
    raw = f"{task_id}:{tool_name}:{args_json}:{attempt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _args_hash(args_json: str) -> str:
    return hashlib.sha256(args_json.encode()).hexdigest()


@trace("agent_run")
async def run(
    task: TaskRow,
    resolved_inputs: dict,
    emit: Callable[[str, dict], None] | None = None,
    tracer: Any | None = None,
) -> dict[str, Any]:
    """
    Execute an agent task. Returns the structured output dict.
    Raises RuntimeError on failure (caller handles retry logic).
    Raises WaitingWebhookSignal when the agent calls wait_webhook.
    """
    config = get_agent_config(task.agent_name)
    set_execution_context(execution_id=task.trace_id, agent_id=f"{task.agent_name}/{task.id}")

    tools = _build_tool_defs(config["allowed_tools"])
    model = config["model"]
    max_iter = config["max_iterations"]

    user_content = f"Task: {task.description}\n\nInputs:\n{json.dumps(resolved_inputs, indent=2)}"

    messages: list[dict] = [
        {"role": "system", "content": config["system_prompt"]},
        {"role": "user", "content": user_content},
    ]

    if emit:
        emit("message", {"task_id": task.id, "role": "user", "content": user_content})

    await db.save_message(task.id, "user", user_content, sequence=0)

    logger.info("[task=%s agent=%s] Starting agent loop (model=%s max_iter=%d)",
                task.id, task.agent_name, model, max_iter)

    for iteration in range(max_iter):
        logger.debug("[task=%s] Iteration %d/%d — calling %s", task.id, iteration + 1, max_iter, model)

        try:
            response = await acompletion(model=model, messages=messages, tools=tools, temperature=0.1)
        except Exception as exc:
            err_str = str(exc)
            # Rate limit — back off and retry
            if "rate_limit" in err_str.lower() or "rate limit" in err_str.lower() or "429" in err_str:
                wait = min(2 ** iteration, 30)
                logger.warning("[task=%s] Rate limited on iter %d — retrying in %ds", task.id, iteration + 1, wait)
                await asyncio.sleep(wait)
                continue
            # Groq sometimes fails to generate a valid function call.
            if "failed to call a function" in err_str.lower() or "tool_use_failed" in err_str.lower():
                logger.warning("[task=%s] Groq function-call failure (iter %d) — injecting retry hint",
                               task.id, iteration + 1)
                messages.append({
                    "role": "user",
                    "content": (
                        "You MUST call one of the available tools in your response. "
                        "Do not write plain text — use a tool call. "
                        "If you have enough information, call submit_result with your findings."
                    ),
                })
                continue
            logger.error("[task=%s] LLM call failed on iteration %d: %s", task.id, iteration + 1, exc)
            raise

        msg = response.choices[0].message

        assistant_content = msg.content or ""
        if assistant_content:
            logger.debug("[task=%s] Assistant message: %s…", task.id, assistant_content[:120])
            await db.save_message(task.id, "assistant", assistant_content, sequence=len(messages))
            if emit:
                emit("message", {"task_id": task.id, "role": "assistant", "content": assistant_content})

        if not msg.tool_calls:
            # Try to parse a JSON result directly from the assistant message
            result = _try_parse_json_result(assistant_content)
            if result is not None:
                logger.info("[task=%s agent=%s] Parsed JSON result from assistant text (no tool call)",
                            task.id, task.agent_name)
                return result
            # Nudge the model to call submit_result
            if iteration < max_iter - 1:
                logger.warning("[task=%s] No tool call on iter %d — nudging agent to call submit_result",
                               task.id, iteration + 1)
                messages.append({
                    "role": "user",
                    "content": "You must call submit_result with your final result. Use the submit_result tool now.",
                })
                continue
            break

        tool_results = []
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            args_str = tc.function.arguments
            args = json.loads(args_str)
            tc_id = tc.id

            if tool_name == "submit_result":
                result = args.get("result", args)
                logger.info("[task=%s agent=%s] submit_result called — task done ✓", task.id, task.agent_name)
                return result

            ikey = _idempotency_key(task.id, tool_name, args_str, task.attempt_count)
            logger.debug("[task=%s] Tool call: %s(%s…) ikey=%s…",
                         task.id, tool_name, args_str[:80], ikey[:12])

            if emit:
                emit("tool_call", {"task_id": task.id, "tool": tool_name, "args": args})

            # Check for cached result before opening a span so we can tag it
            existing = await db.get_tool_call_by_idempotency(ikey)
            is_cached = bool(existing and existing.status == "SUCCESS" and existing.result_json)

            with tool_span(tracer, task.id, tool_name, args, cached=is_cached) as tspan:
                result = await _execute_tool_idempotent(task, tool_name, args_str, args, ikey)

                if isinstance(result, dict) and result.get(WAITING_WEBHOOK_SENTINEL):
                    wait_token = result["wait_token"]
                    await db.set_task_waiting_webhook(task.id, wait_token)
                    logger.info("[task=%s] Task suspended — waiting for webhook (token=%s)", task.id, wait_token)
                    if tspan:
                        tspan.set_attribute("wait_token", wait_token)
                        tspan.add_event("task_suspended_for_webhook")
                    if emit:
                        emit("task_waiting", {"task_id": task.id, "wait_token": wait_token, "webhook_url": result.get("webhook_url", "")})
                    raise WaitingWebhookSignal(wait_token)

                if "error" in result:
                    logger.warning("[task=%s] Tool %s returned error: %s", task.id, tool_name, result["error"])
                    if tspan:
                        tspan.set_attribute("error", result["error"])
                else:
                    logger.debug("[task=%s] Tool %s succeeded", task.id, tool_name)
                    if tspan:
                        tspan.set_output(result)

            if emit:
                emit("tool_result", {"task_id": task.id, "tool": tool_name,
                                     "status": "ERROR" if "error" in result else "SUCCESS"})

            result_str = json.dumps(result)
            tool_results.append({"role": "tool", "tool_call_id": tc_id, "content": result_str})
            await db.save_message(task.id, "tool", result_str, sequence=len(messages) + iteration + 1, tool_call_id=tc_id)

        messages.append({"role": "assistant", "content": assistant_content, "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})
        messages.extend(tool_results)

    raise RuntimeError(f"Agent {task.agent_name} did not call submit_result within {max_iter} iterations")


async def _execute_tool_idempotent(
    task: TaskRow,
    tool_name: str,
    args_str: str,
    args: dict,
    ikey: str,
) -> dict:
    existing = await db.get_tool_call_by_idempotency(ikey)
    if existing and existing.status == "SUCCESS" and existing.result_json:
        logger.info("[task=%s] Tool %s: replaying cached result (idempotent) — no side-effect fired", task.id, tool_name)
        return json.loads(existing.result_json)

    await db.create_tool_call(
        task_id=task.id,
        tool_name=tool_name,
        args_json=args_str,
        args_hash=_args_hash(args_str),
        ikey=ikey,
    )

    entry = TOOL_REGISTRY.get(tool_name)
    if not entry:
        result = {"error": f"Unknown tool: {tool_name}"}
        await db.settle_tool_call(ikey, json.dumps(result), "FAILED", error=result["error"])
        return result

    enriched_args = {**args, "_goal_id": task.goal_id}
    try:
        result = await entry.fn(enriched_args)
        await db.settle_tool_call(ikey, json.dumps(result), "SUCCESS")
        return result
    except Exception as e:
        error_str = str(e)
        logger.error("Tool %s failed: %s", tool_name, error_str)
        await db.settle_tool_call(ikey, None, "FAILED", error=error_str)
        return {"error": error_str}


def _try_parse_json_result(text: str) -> dict | None:
    """
    Attempt to extract a JSON object from the assistant's text response.
    Used as a fallback when the model doesn't call submit_result but returns
    JSON in its message body (common with Groq llama models).
    """
    if not text:
        return None
    # Try to find a JSON block in the text
    import re
    # Look for ```json ... ``` blocks first
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass
    # Try to find a raw JSON object (largest {...} block)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return None


class WaitingWebhookSignal(Exception):
    def __init__(self, wait_token: str):
        self.wait_token = wait_token
        super().__init__(f"Task waiting for webhook: {wait_token}")
