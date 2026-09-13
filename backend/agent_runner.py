"""
Generic LLM tool-call loop. Works for any agent config from AGENT_REGISTRY.
Handles idempotent tool execution and SSE event emission.
"""
import hashlib
import json
import logging
import re
import uuid
from typing import Any, Callable

import db
from agent_registry import get_agent_config
from llm import acompletion
from state import TaskRow
from tools import TOOL_REGISTRY
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL
from tools.wait_webhook import WAITING_WEBHOOK_SENTINEL
from tracing import set_execution_context, trace, tool_span

logger = logging.getLogger(__name__)

FAILED_GENERATION_RE = re.compile(r"<function=(.+?)>(.*?)</function>", re.DOTALL)

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


def _recover_failed_tool_call(error: Exception) -> tuple[str, str, dict] | None:
    message = str(error)
    if "failed_generation" not in message and "<function=" not in message:
        return None

    failed_generation = message
    marker = "GroqException - "
    if marker in message:
        try:
            payload = json.loads(message.split(marker, 1)[1])
            failed_generation = payload["error"]["failed_generation"]
        except (json.JSONDecodeError, KeyError, IndexError):
            failed_generation = message

    match = FAILED_GENERATION_RE.search(failed_generation.strip())
    if not match:
        return None

    raw_head, raw_body = match.groups()
    raw_head = raw_head.strip()
    raw_body = raw_body.strip()

    if " " in raw_head:
        tool_name, head_rest = raw_head.split(" ", 1)
        args_json = (head_rest + raw_body).strip()
    elif "{" in raw_head:
        tool_name, head_rest = raw_head.split("{", 1)
        args_json = ("{" + head_rest + raw_body).strip()
    else:
        tool_name = raw_head
        args_json = raw_body

    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return None
    return tool_name.strip(), args_json, args


def _tool_allowed(tool_name: str, allowed_tools: list[str]) -> bool:
    return tool_name == "submit_result" or tool_name in allowed_tools


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

    import context as ctx_store
    ctx_prompt = ctx_store.get_context_prompt()
    user_content = f"Task: {task.description}\n\nInputs:\n{json.dumps(resolved_inputs, indent=2)}"
    if ctx_prompt:
        user_content = f"Background context about the project:{ctx_prompt}\n\n{user_content}"

    messages: list[dict] = [
        {"role": "system", "content": config["system_prompt"]},
        {"role": "user", "content": user_content},
    ]

    if emit:
        emit("message", {"task_id": task.id, "role": "user", "content": user_content})

    await db.save_message(task.id, "user", user_content, sequence=0)

    logger.info("[task=%s agent=%s] Starting agent loop (model=%s max_iter=%d)",
                task.id, task.agent_name, model, max_iter)

    consecutive_errors = 0  # consecutive tool-call errors; triggers forced submit
    _failing_tools: set[str] = set()  # tools that have failed — used in nudge messages

    for iteration in range(max_iter):
        logger.debug("[task=%s] Iteration %d/%d — calling %s", task.id, iteration + 1, max_iter, model)

        try:
            response = await acompletion(model=model, messages=messages, tools=tools, temperature=0.1)
        except Exception as exc:
            err_str = str(exc)
            # Rate limits are handled by the task worker so this coroutine does
            # not hold a concurrency slot while sleeping.
            if "rate_limit" in err_str.lower() or "rate limit" in err_str.lower() or "429" in err_str:
                raise
            recovered = _recover_failed_tool_call(exc)
            if recovered:
                tool_name, args_str, args = recovered
                if not _tool_allowed(tool_name, config["allowed_tools"]):
                    raise RuntimeError(f"Recovered disallowed tool call: {tool_name}")
                tc_id = f"recovered_{uuid.uuid4().hex}"
                logger.warning("[task=%s] Recovered malformed Groq tool call: %s", task.id, tool_name)

                if tool_name == "submit_result":
                    result = args.get("result", args)
                    logger.info("[task=%s agent=%s] recovered submit_result — task done", task.id, task.agent_name)
                    return result

                ikey = _idempotency_key(task.id, tool_name, args_str, task.attempt_count)
                if emit:
                    emit("tool_call", {"task_id": task.id, "tool": tool_name, "args": args})

                existing = await db.get_tool_call_by_idempotency(ikey)
                is_cached = bool(existing and existing.status == "SUCCESS" and existing.result_json)
                with tool_span(tracer, task.id, tool_name, args, cached=is_cached) as tspan:
                    result = await _execute_tool_idempotent(task, tool_name, args_str, args, ikey)
                    if isinstance(result, dict) and result.get(WAITING_WEBHOOK_SENTINEL):
                        wait_token = result["wait_token"]
                        await db.set_task_waiting_webhook(task.id, wait_token)
                        if tspan:
                            tspan.set_attribute("wait_token", wait_token)
                            tspan.add_event("task_suspended_for_webhook")
                        if emit:
                            emit("task_waiting", {"task_id": task.id, "wait_token": wait_token, "webhook_url": result.get("webhook_url", "")})
                        raise WaitingWebhookSignal(wait_token)
                    if isinstance(result, dict) and result.get(WAITING_CREDENTIAL_SENTINEL):
                        cred_var = result["credential"]
                        provider = result.get("provider", "")
                        await db.set_task_waiting_credential(task.id, cred_var)
                        if emit:
                            emit("credential_request", {
                                "task_id": task.id,
                                "credential": cred_var,
                                "provider": provider,
                                "message": result.get("message", f"{cred_var} is required"),
                            })
                        raise WaitingCredentialSignal(cred_var, provider)
                    if tspan and "error" not in result:
                        tspan.set_output(result)

                if emit:
                    emit("tool_result", {"task_id": task.id, "tool": tool_name,
                                         "status": "ERROR" if "error" in result else "SUCCESS"})

                result_str = json.dumps(result)
                await db.save_message(task.id, "tool", result_str, sequence=len(messages) + iteration + 1, tool_call_id=tc_id)
                messages.append({"role": "assistant", "content": "", "tool_calls": [
                    {"id": tc_id, "type": "function", "function": {"name": tool_name, "arguments": args_str}}
                ]})
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": result_str})
                continue
            # Groq sometimes fails to generate a valid function call.
            if (
                "failed to call a function" in err_str.lower()
                or "tool_use_failed" in err_str.lower()
                or "tool call validation failed" in err_str.lower()
            ):
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
                    "content": (
                        "You must call submit_result with your final answer NOW. "
                        "Do not call any other tools. Use submit_result immediately."
                    ),
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
                # Validate required keys for agents that have strict output schemas
                schema_required = config.get("output_schema", {}).get("required", [])
                missing = [k for k in schema_required if k not in result]
                if missing:
                    feedback = (
                        f"submit_result rejected — missing required keys: {missing}. "
                        f"Your result had keys: {list(result.keys())}. "
                        f"You MUST include ALL of: {schema_required}. "
                        "Call submit_result again with the correct keys."
                    )
                    logger.warning("[task=%s agent=%s] submit_result missing keys %s — rejecting and retrying",
                                   task.id, task.agent_name, missing)
                    tool_results.append({"role": "tool", "tool_call_id": tc_id, "content": feedback})
                    messages = messages + tool_results
                    tool_results = []
                    continue
                logger.info("[task=%s agent=%s] submit_result called — task done ✓", task.id, task.agent_name)
                return result

            if not _tool_allowed(tool_name, config["allowed_tools"]):
                result = {"error": f"Tool {tool_name} is not allowed for agent {task.agent_name}"}
                result_str = json.dumps(result)
                logger.warning("[task=%s] Disallowed tool call blocked: %s", task.id, tool_name)
                tool_results.append({"role": "tool", "tool_call_id": tc_id, "content": result_str})
                await db.save_message(task.id, "tool", result_str, sequence=len(messages) + iteration + 1, tool_call_id=tc_id)
                if emit:
                    emit("tool_result", {"task_id": task.id, "tool": tool_name, "status": "ERROR"})
                consecutive_errors += 1
                _failing_tools.add(tool_name)
                continue

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

                if isinstance(result, dict) and result.get(WAITING_CREDENTIAL_SENTINEL):
                    cred_var = result["credential"]
                    provider = result.get("provider", "")
                    await db.set_task_waiting_credential(task.id, cred_var)
                    logger.info("[task=%s] Task suspended — waiting for credential %s", task.id, cred_var)
                    if emit:
                        emit("credential_request", {
                            "task_id": task.id,
                            "credential": cred_var,
                            "provider": provider,
                            "message": result.get("message", f"{cred_var} is required"),
                        })
                    raise WaitingCredentialSignal(cred_var, provider)

                if "error" in result:
                    logger.warning("[task=%s] Tool %s returned error: %s", task.id, tool_name, result["error"])
                    consecutive_errors += 1
                    _failing_tools.add(tool_name)
                    if tspan:
                        tspan.set_attribute("error", result["error"])
                else:
                    consecutive_errors = 0
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

        # ── Force submit when tools keep failing ────────────────────────────
        if consecutive_errors >= 3:
            failing_list = ", ".join(sorted(_failing_tools))
            logger.warning("[task=%s] %d consecutive tool errors (%s) — forcing submit_result",
                           task.id, consecutive_errors, failing_list)
            messages.append({
                "role": "user",
                "content": (
                    f"The following tools are unavailable or failing: {failing_list}. "
                    "Stop calling them. "
                    "Use your training knowledge to complete the task as best you can. "
                    "Call submit_result NOW with your best answer based on what you know."
                ),
            })
            consecutive_errors = 0  # reset so we don't spam this message

        # ── Early warning at last 2 iterations ──────────────────────────────
        if iteration == max_iter - 3:
            messages.append({
                "role": "user",
                "content": (
                    "You are running low on iterations. "
                    "Wrap up and call submit_result with your final answer on the next turn."
                ),
            })

    # ── Forced final submit: don't face-plant after exhausting iterations ──
    # The agent explored but never converged. Make ONE last call that can only
    # call submit_result, so a long-running task degrades to a usable result
    # instead of failing the whole goal.
    logger.warning("[task=%s] Hit iteration cap without submit — forcing final submit_result", task.id)
    messages.append({
        "role": "user",
        "content": (
            "STOP. You are out of iterations. Do NOT call any other tool. "
            "Call submit_result NOW with your best answer based on everything gathered so far. "
            "Partial but structured output is required — empty/no answer is a failure."
        ),
    })
    try:
        final = await acompletion(
            model=model,
            messages=messages,
            tools=[SUBMIT_RESULT_TOOL],
            tool_choice={"type": "function", "function": {"name": "submit_result"}},
            temperature=0.1,
        )
        fmsg = final.choices[0].message
        if fmsg.tool_calls:
            fargs = json.loads(fmsg.tool_calls[0].function.arguments)
            result = fargs.get("result", fargs)
            logger.info("[task=%s agent=%s] forced final submit_result succeeded", task.id, task.agent_name)
            return result
        parsed = _try_parse_json_result(fmsg.content or "")
        if parsed is not None:
            logger.info("[task=%s agent=%s] forced final: parsed JSON from content", task.id, task.agent_name)
            return parsed
    except Exception as exc:
        logger.warning("[task=%s] forced final submit attempt failed: %s", task.id, exc)

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


class WaitingCredentialSignal(Exception):
    def __init__(self, credential_var: str, provider: str = ""):
        self.credential_var = credential_var
        self.provider = provider
        super().__init__(f"Task waiting for credential: {credential_var}")
