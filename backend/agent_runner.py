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
import language
from agent_registry import get_agent_config
from llm import acompletion
from state import TaskRow
from tools import TOOL_REGISTRY
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL
from tools.wait_webhook import WAITING_WEBHOOK_SENTINEL

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


def _self_reported_failure(result: dict, schema_required: list[str]) -> str | None:
    """Describe how a submit_result contradicts itself, or None when it is coherent.

    Presence of the required keys was never enough. A coder handed a path that does not
    exist submitted `{code: "", path: "main/mergesort.py", output: "404 Not Found",
    success: False}` — every required key present, so it was accepted as DONE, and the
    integrator interpolated that empty `code` into a pull request that added an empty
    file. The agent said it failed and the pipeline recorded success.

    Two contradictions are caught, both about the result the agent itself declared:

    * `success: False` — it is telling us the work did not happen.
    * a required string that is empty — there is no content to hand downstream, and
      every required field exists precisely because something needs to consume it.

    Deliberately narrow. Only REQUIRED keys are checked, so an optional field like the
    researcher's `code_context` may still be empty, and only `success` is read for its
    truth value — no other field's meaning is assumed.
    """
    if not isinstance(result, dict):
        return (f"the result must be a JSON object with the keys {schema_required}, "
                f"but you sent a bare {type(result).__name__}.")
    if "success" in result and not isinstance(result["success"], bool):
        # Goal 00605510: the coder put a paragraph explaining why the task could not be
        # done into `success`. It is not the literal False, so the check below could not
        # see it — an admission of failure recorded as a pass. "true"/"false" are
        # tolerated because models write JSON by hand and bouncing a spelling of True
        # costs a turn and teaches nothing.
        spelled = str(result["success"]).strip().lower()
        if spelled == "false":
            return "you set success=false."
        if spelled != "true":
            return (f"success must be true or false, but you sent "
                    f"{str(result['success'])[:80]!r}.")
    elif result.get("success") is False:
        return "you set success=False."
    empty = [
        k for k in schema_required
        if isinstance(result.get(k), str) and not result[k].strip()
    ]
    if empty:
        return f"these required fields are empty: {empty}."
    return None


def _wrong_language_for_task(result: dict, task_text: str) -> str | None:
    """Describe a `code` field written in a language the task did not ask for.

    Live failure, goal 4ad14cf1. The task was "Migrate the auth.py file to Rust". The
    coder's only execution tool is `code_exec`, a Python interpreter, so it cannot run
    Rust and cannot prove Rust works. It submitted PYTHON, ran that successfully, and set
    `success: True`.

    `_self_reported_failure` catches an agent that ADMITS failure. This is the inverse and
    the worse shape — claiming success for work not done. PR #32 at least told the truth
    about itself.

    `_language_mismatches` in `github_pr` asks a related question, but only on the commit
    path, and this goal never reached an integrator. The claim has to be checked where it
    is made.
    """
    wanted = language.requested_language(task_text)
    if not wanted:
        return None
    code = result.get("code")
    if not isinstance(code, str) or not code.strip():
        return None
    actual = language.detect_language(code, expected=wanted)
    if actual is None:
        return None  # corroborated, or too small to identify — no opinion
    return (f"the task asks for {wanted}, but the code you submitted is {actual}.")


#: The only language this container can execute. `tools/code_exec.py` runs
#: `sys.executable -c <code>` — there is no toolchain for anything else, so an `output`
#: field for any other language is a claim rather than evidence.
_RUNNABLE_LANGUAGES = {"Python"}

#: Ways of saying "I did not run this". Any one of them is enough.
_NOT_RUN = ("not executed", "not run", "cannot run", "could not run", "did not run",
            "unverified", "not verified", "cannot verify", "could not verify",
            "not compiled", "cannot compile", "could not compile", "no toolchain")


def _unrunnable_execution_claim(result: dict, task_text: str) -> str | None:
    """Describe an `output` presented as a run that cannot have happened.

    Live failure, goal b4d3e69a. The wrong-language guard worked and the coder submitted
    real Rust at `auth.rs`. It also submitted `output: "Login successful"` — a string
    lifted out of its own source, because `code_exec` runs Python and nothing else. The
    Rust did not even compile: the first line closes a brace with a paren. The writer then
    reported the migration as successfully completed on the strength of that output.

    Being unable to run something is not a failure; saying you ran it is. So this does not
    reject the work, only the claim — an `output` that admits the code was not executed
    passes untouched, and that is exactly what the message asks for.
    """
    wanted = language.requested_language(task_text)
    if not wanted or wanted in _RUNNABLE_LANGUAGES:
        return None
    output = result.get("output")
    if not isinstance(output, str) or not output.strip():
        return None
    if any(phrase in output.lower() for phrase in _NOT_RUN):
        return None
    return (f"you reported output {output.strip()[:60]!r} for {wanted} code, but nothing "
            f"here can run {wanted} — code_exec is a Python interpreter.")


#: A claim to have PRODUCED something on GitHub: a pull request, or a posted comment.
#: Deliberately not every GitHub URL — a researcher assembling a blob or repository link
#: is doing its job, while "here is the PR I opened" is an assertion about the world.
_CLAIMED_URL = re.compile(
    r"https?://(?:www\.)?github\.com/[\w.-]+/[\w.-]+/"
    r"(?:pull/\d+|issues/\d+#issuecomment-\d+)", re.I)


def _collect_urls(obj: Any) -> list[str]:
    """Every produced-artifact URL anywhere inside a nested structure."""
    found: list[str] = []
    if isinstance(obj, str):
        found.extend(_CLAIMED_URL.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            found.extend(_collect_urls(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found.extend(_collect_urls(v))
    return found


def _fabricated_urls(result: Any, known: set[str]) -> list[str]:
    """URLs the result claims that nothing in this task ever produced or was given.

    Live failure, goal 00605510. The integrator submitted `url: ".../pull/1"` and
    `result: "PR raised and comment posted successfully"`. No pull request was created —
    the newest in that repository is #34 — and it posted a public comment on the issue
    announcing the PR, linking to nothing. Every shape check passed, because the shape was
    perfect; nothing compared the claim against what the task had actually done.

    `known` holds URLs that really exist as far as this task can tell: whatever its tool
    calls returned, plus whatever it was handed in its inputs or description. Anything
    else in a produced-artifact position was invented.
    """
    seen = {u.rstrip("/.,);") for u in known}
    return [u for u in dict.fromkeys(_collect_urls(result)) if u.rstrip("/.,);") not in seen]


def _submission_problem(result: Any, schema_required: list[str],
                        task_text: str = "",
                        known_urls: set[str] | None = None) -> str | None:
    """The feedback to hand back when a submitted result cannot be accepted, else None.

    A task can end in four places — the `submit_result` tool call, JSON parsed out of a
    plain assistant message, the forced final submit after the iteration cap, and JSON
    parsed out of THAT message. Only the first one checked anything, so the other three
    were a way around every guard.

    PR #32 went out through the forced final. The coder was asked to migrate a file to
    Rust, its only execution tool is a Python interpreter, so it could not run what it
    had written and truthfully submitted `success: False`. The loop rejected that ten
    times, the cap hit, and the forced final returned the same payload unchecked. Every
    route now funnels through here.
    """
    if not schema_required:
        return None
    if not isinstance(result, dict):
        return (
            f"submit_result rejected — the result must be a JSON object with the "
            f"keys {schema_required}, but you sent a bare "
            f"{type(result).__name__}. Call submit_result again, passing an object."
        )
    missing = [k for k in schema_required if k not in result]
    if missing:
        return (
            f"submit_result rejected — missing required keys: {missing}. "
            f"Your result had keys: {list(result.keys())}. "
            f"You MUST include ALL of: {schema_required}. "
            "Call submit_result again with the correct keys."
        )
    mismatch = _wrong_language_for_task(result, task_text)
    if mismatch:
        return (
            f"submit_result rejected — {mismatch} Write the task in the language it asks "
            "for. If you cannot run or verify that language with the tools you have, say "
            "so plainly instead of submitting something else and calling it done — an "
            "answer in the wrong language is not a partial answer, it is the wrong answer."
        )
    if known_urls is not None and isinstance(result, dict):
        invented = _fabricated_urls(result, known_urls)
        if invented:
            return (
                f"submit_result rejected — you are reporting {', '.join(invented)}, but no "
                "tool call in this task produced that and it was not given to you. A pull "
                "request or comment exists only if you created it: call the tool, and "
                "report the URL it returns. If the tool failed or you never called it, say "
                "that instead — do not describe an outcome that did not happen."
            )

    unrunnable = _unrunnable_execution_claim(result, task_text)
    if unrunnable:
        return (
            f"submit_result rejected — {unrunnable} Say so in the output field instead: "
            "that the code was not executed, and why. Not being able to run something is "
            "not a failure and will be accepted. Reporting a run that did not happen is, "
            "because everything downstream reads that field as evidence the code works."
        )
    contradiction = _self_reported_failure(result, schema_required)
    if contradiction:
        return (
            f"submit_result rejected — {contradiction} You are reporting failure "
            "and submitting it as the task's result, which would hand an empty or "
            "failed output to the next agent as if it had worked. Either do the "
            "work and submit a real result, or if it genuinely cannot be done "
            "(the file does not exist, the input you were given is wrong), say so "
            "in every field rather than leaving them blank — do not submit a "
            "success-shaped result that is empty."
        )
    return None


async def run(
    task: TaskRow,
    resolved_inputs: dict,
    emit: Callable[[str, dict], None] | None = None,
) -> dict[str, Any]:
    """
    Execute an agent task. Returns the structured output dict.
    Raises RuntimeError on failure (caller handles retry logic).
    Raises WaitingWebhookSignal when the agent calls wait_webhook.
    """
    config = get_agent_config(task.agent_name)

    tools = _build_tool_defs(config["allowed_tools"])
    model = config["model"]
    max_iter = config["max_iterations"]

    import context as ctx_store
    ctx_prompt = ctx_store.get_context_prompt()
    user_content = f"Task: {task.description}\n\nInputs:\n{json.dumps(resolved_inputs, indent=2)}"
    if ctx_prompt:
        user_content = f"Background context about the project:{ctx_prompt}\n\n{user_content}"
    # Inject previous failure context on retries so the agent knows what went wrong
    if task.attempt_count > 0 and task.error:
        user_content += (
            f"\n\n⚠️ RETRY ATTEMPT {task.attempt_count}: Previous attempt failed with:\n"
            f"{task.error[:500]}\n"
            "Take a different approach to avoid repeating the same failure."
        )

    messages: list[dict] = [
        {"role": "system", "content": config["system_prompt"]},
        {"role": "user", "content": user_content},
    ]

    if emit:
        emit("message", {"task_id": task.id, "role": "user", "content": user_content})

    await db.save_message(task.id, "user", user_content, sequence=0)

    logger.info("[task=%s agent=%s] Starting agent loop (model=%s max_iter=%d)",
                task.id, task.agent_name, model, max_iter)

    # URLs this task can honestly refer to: whatever it was handed, plus whatever its
    # tool calls actually return. A produced-artifact URL outside this set was invented.
    known_urls: set[str] = set(_collect_urls(resolved_inputs)) | set(_collect_urls(task.description))

    consecutive_errors = 0  # consecutive tool-call errors; triggers forced submit
    _failing_tools: set[str] = set()  # tools that have failed — used in nudge messages

    for iteration in range(max_iter):
        logger.debug("[task=%s] Iteration %d/%d — calling %s", task.id, iteration + 1, max_iter, model)

        _kwargs: dict = {"tools": tools}
        if not any(m in model for m in ("claude-opus-4", "claude-sonnet-4", "claude-haiku-4-5")):
            _kwargs["temperature"] = 0.1
        try:
            response = await acompletion(role=task.agent_name, model=model, messages=messages, **_kwargs)
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

                result = await _execute_tool_idempotent(task, tool_name, args_str, args, ikey)
                if isinstance(result, dict) and result.get(WAITING_WEBHOOK_SENTINEL):
                    wait_token = result["wait_token"]
                    await db.set_task_waiting_webhook(task.id, wait_token)
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
                # This is a submission by another name, so it answers to the same rules.
                # Returning it unchecked let an agent skip every guard simply by printing
                # its JSON instead of calling the tool.
                problem = _submission_problem(result, config.get("output_schema", {}).get("required", []),
                                              task.description, known_urls)
                if problem is None:
                    logger.info("[task=%s agent=%s] Parsed JSON result from assistant text (no tool call)",
                                task.id, task.agent_name)
                    return result
                logger.warning("[task=%s agent=%s] JSON in assistant text rejected: %s",
                               task.id, task.agent_name, problem[:160])
                messages.append({"role": "assistant", "content": assistant_content})
                messages.append({"role": "user", "content": problem})
                if iteration < max_iter - 1:
                    continue
                break
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
        _submit_rejected = False
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            args_str = tc.function.arguments
            tc_id = tc.id
            # A syntax error in the model's own tool call used to raise straight out of
            # run(), killing the task. Goal 32d630f2: the coder wrote Rust containing
            # backticks where quotes belong, that string reached the next task's tool
            # call, and `Unterminated string starting at line 1 column 12` failed the
            # review — so the integrator behind it never ran and no PR was opened. Every
            # other invalid thing a model sends gets a rejection and another turn; this
            # was the one shape that ended the task instead.
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as exc:
                logger.warning("[task=%s agent=%s] %s called with invalid JSON (%s) — re-prompting",
                               task.id, task.agent_name, tool_name, exc)
                messages.append({"role": "assistant", "content": assistant_content or "", "tool_calls": [
                    {"id": tc_id, "type": "function",
                     "function": {"name": tool_name, "arguments": args_str}}
                ]})
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": (
                    f"Your call to {tool_name} could not be read: its arguments are not valid "
                    f"JSON ({exc}). This usually means a string in the payload contains an "
                    "unescaped quote, newline or backtick. Send the call again with the "
                    "arguments as well-formed JSON."
                )})
                _submit_rejected = True
                break

            if tool_name == "submit_result":
                result = args.get("result", args)
                # Validate required keys for agents that have strict output schemas
                schema_required = config.get("output_schema", {}).get("required", [])
                feedback = _submission_problem(result, schema_required, task.description, known_urls)
                if feedback is not None:
                    logger.warning("[task=%s agent=%s] submit_result rejected: %s",
                                   task.id, task.agent_name, feedback[:160])
                    # Anthropic: assistant msg (with tool_use) must come before tool_result
                    messages.append({"role": "assistant", "content": assistant_content or "", "tool_calls": [
                        {"id": tc_id, "type": "function", "function": {"name": tool_name, "arguments": args_str}}
                    ]})
                    messages.append({"role": "tool", "tool_call_id": tc_id, "content": feedback})
                    _submit_rejected = True
                    break  # skip remaining tool calls; lines 373-377 must also be skipped
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

            result = await _execute_tool_idempotent(task, tool_name, args_str, args, ikey)

            if isinstance(result, dict) and result.get(WAITING_WEBHOOK_SENTINEL):
                wait_token = result["wait_token"]
                await db.set_task_waiting_webhook(task.id, wait_token)
                logger.info("[task=%s] Task suspended — waiting for webhook (token=%s)", task.id, wait_token)
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
            else:
                consecutive_errors = 0
                logger.debug("[task=%s] Tool %s succeeded", task.id, tool_name)

            if emit:
                emit("tool_result", {"task_id": task.id, "tool": tool_name,
                                     "status": "ERROR" if "error" in result else "SUCCESS"})

            # A URL becomes claimable only once a tool has actually returned it.
            known_urls.update(_collect_urls(result))
            result_str = json.dumps(result)
            tool_results.append({"role": "tool", "tool_call_id": tc_id, "content": result_str})
            await db.save_message(task.id, "tool", result_str, sequence=len(messages) + iteration + 1, tool_call_id=tc_id)

        if not _submit_rejected:
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
    # The result still has to be coherent. Running out of iterations is a reason to ask
    # one last time, not a reason to accept anything: PR #32 was a `success: False` payload
    # the loop had already rejected ten times, waved through here and committed to GitHub.
    # A rejection gets ONE corrective call — a missing key is trivially fixable and failing
    # the goal over it is waste — and after that the task fails rather than lying.
    schema_required = config.get("output_schema", {}).get("required", [])
    last_problem: str | None = None
    for _attempt in range(2):
        try:
            _fkw: dict = {"tools": [SUBMIT_RESULT_TOOL], "tool_choice": {"type": "function", "function": {"name": "submit_result"}}}
            if not any(m in model for m in ("claude-opus-4", "claude-sonnet-4", "claude-haiku-4-5")):
                _fkw["temperature"] = 0.1
            final = await acompletion(role=task.agent_name, model=model, messages=messages, **_fkw)
            fmsg = final.choices[0].message
            if fmsg.tool_calls:
                # Unreadable arguments are a reason to use the second attempt, not to
                # abandon it: this `raise` used to land in the `except Exception` below
                # and break out of the loop, so the retry existed but was never made.
                try:
                    fargs = json.loads(fmsg.tool_calls[0].function.arguments)
                except json.JSONDecodeError as exc:
                    last_problem = f"the arguments were not valid JSON ({exc})"
                    logger.warning("[task=%s] forced final sent invalid JSON: %s", task.id, exc)
                    messages.append({"role": "user", "content": (
                        f"Your submit_result arguments were not valid JSON ({exc}). Send it "
                        "again as a well-formed JSON object.")})
                    continue
                result = fargs.get("result", fargs)
            else:
                result = _try_parse_json_result(fmsg.content or "")
            if result is None:
                break  # nothing was submitted at all — the generic failure below says so
            problem = _submission_problem(result, schema_required, task.description, known_urls)
            if problem is None:
                logger.info("[task=%s agent=%s] forced final submit_result succeeded", task.id, task.agent_name)
                return result
            last_problem = problem
            logger.warning("[task=%s agent=%s] forced final submit rejected: %s",
                           task.id, task.agent_name, problem[:160])
            messages.append({
                "role": "user",
                "content": problem + " This is your final attempt — submit a coherent result now.",
            })
        except Exception as exc:
            logger.warning("[task=%s] forced final submit attempt failed: %s", task.id, exc)
            break

    if last_problem is not None:
        raise RuntimeError(
            f"Agent {task.agent_name} could not produce a usable result: {last_problem}"
        )
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
