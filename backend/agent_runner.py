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
import redaction
from tools import approval
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


def _idempotency_key(task_id: str, tool_name: str, args_json: str) -> str:
    """Identifies one tool invocation for the life of a task, across every attempt.

    `attempt` used to be part of this key. It could not be: `claim_ready_task` does
    `attempt_count=attempt_count+1` on *every* claim, including the claim that follows a
    resume, so a task that parked on a credential and was released came back with a
    different key for identical work — missed the whole cache and re-fired every write it
    had already completed. A goal that paused once posted its issue comment twice.

    Dropping `attempt` only works together with the park handling in
    `_execute_tool_idempotent`: a `WAITING_*` sentinel must never be stored as a completed
    call, or the resumed task replays the sentinel and parks again forever.
    """
    raw = f"{task_id}:{tool_name}:{args_json}"
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


#: How many times one task may call a tool that leaves a durable, public mark.
#:
#: Goal e6b9529c: the integrator opened PR #43 correctly, then posted EIGHT near-identical
#: comments on it — 18:29:13, :16, :19, :22, :25, :28, :31, :34 — one every three seconds
#: until its turns ran out. Raising its budget from 8 to 14 iterations is what gave it the
#: room. The budget was right; what was missing was a reason to stop once the deliverable
#: existed. An agent with nothing left to do will fill the space, and here the space was
#: somebody's repository.
#:
#: Reads are deliberately absent. Surveying a repo is twenty list_dir and read_file calls
#: and capping those would break the thing the researcher exists to do. Only writes leave
#: a mark, so only writes are counted.
#:
#: Two comments, because the documented GitHub pattern posts on the original issue and may
#: also comment on the pull request it just opened.
WRITE_TOOL_CALL_CAP: dict[str, int] = {
    "github_post_comment": 2,
    "github_create_issue": 2,
    "github_pr": 2,
    "github_create_repo": 1,
    "github_fork": 1,
    "github_merge_pr": 1,
    "github_review_pr": 1,
    "github_set_branch_protection": 1,
}


def _over_write_cap(tool_name: str, counts: dict[str, int]) -> str | None:
    """Feedback to hand back instead of firing a write tool again, or None to proceed."""
    cap = WRITE_TOOL_CALL_CAP.get(tool_name)
    if cap is None or counts.get(tool_name, 0) < cap:
        return None
    return (
        f"{tool_name} has already been called {counts[tool_name]} time(s) in this task, "
        f"which is the limit. Repeating it adds noise to the repository rather than "
        f"progress. If the work is done, call submit_result now with what you have."
    )


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


#: Punctuation that only appears in source. A line of English has none of it.
_CODE_PUNCTUATION = re.compile(r"[{}()\[\];=<>]|::|->|:\s*$", re.M)

#: A filename, possibly with directories. No spaces, because a sentence has spaces.
_LOOKS_LIKE_A_PATH = re.compile(r"^[\w.\-]+(?:/[\w.\-]+)*$")


def _not_actually_code(result: dict) -> str | None:
    """Describe a `code` field holding prose, or a `path` field holding a sentence.

    Live failure, goal 2c7b400b → PR #38:

        {"code": "No Rust code was provided to execute",
         "path": "No file path available", "success": True}

    An excuse where the source belongs. Everything else passed it — `success` is a real
    boolean, no required field is empty, `output` honestly says nothing was executed, and
    the language guard abstains because the text shows no marker of any language, which is
    exactly the silence that lets legitimate stubs through. Two tasks later a second coder
    built `import os / print("Hello World")` on top of it, and that became PR #38.

    The test stays syntactic — "is this a program, is that a filename" — rather than "is
    this relevant to the goal", which is a judgement this cannot make. Punctuation is
    enough evidence of a program: `total = sum(values)` counts, while a sentence has none.
    """
    code = result.get("code")
    if isinstance(code, str) and code.strip():
        if not _CODE_PUNCTUATION.search(code) and not language.detect_language(code):
            return f"the code field contains prose, not source: {code.strip()[:70]!r}."
    path = result.get("path")
    if isinstance(path, str) and path.strip() and not _LOOKS_LIKE_A_PATH.match(path.strip()):
        return f"the path field is not a file path: {path.strip()[:70]!r}."
    return None


#: A claim to have PRODUCED something on GitHub: a pull request, or a posted comment.
#: Deliberately not every GitHub URL — a researcher assembling a blob or repository link
#: is doing its job, while "here is the PR I opened" is an assertion about the world.
#:
#: The identifier is a number OR an unfilled blank. It was `\d+` alone, and on 2026-08-22
#: the integrator submitted `.../pull/<PR_NUMBER>` for issue #25 of the sandbox repo: it
#: never called github_pr, wrote the tool's arguments into submit_result, and reported
#: "action": "opened PR". No pull request existed. The guard read straight past it,
#: because a template blank is not `\d+` — so the most brazen version of the very lie
#: this pattern exists to catch was the one shape it could not see.
_PLACEHOLDER_ID = r"<[^>\s]+>|\{\{?[^}\s]+\}?\}"
#: An artifact address: something a tool produced and handed back. Ordered longest-first,
#: because the engine takes the first alternative that matches and a bare `issues/N` would
#: otherwise swallow the head of a comment URL and report the wrong artifact.
#:
#: A bare issue URL was missing. `github_create_issue` returns one, so its absence meant
#: two things at once: a created issue was not recognised as evidence of work, and an
#: issue URL an agent simply made up was never checked against the ones tools returned.
_CLAIMED_URL = re.compile(
    r"https?://(?:www\.)?github\.com/[\w.-]+/[\w.-]+/"
    rf"(?:pull/(?:\d+|{_PLACEHOLDER_ID})"
    rf"|issues/\d+#issuecomment-(?:\d+|{_PLACEHOLDER_ID})"
    rf"|issues/(?:\d+|{_PLACEHOLDER_ID}))", re.I)


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


#: Actions whose whole point is that GitHub hands back an address. A pull request that
#: exists has a URL, and so does a posted comment.
#:
#: Deliberately narrow. `set_branch_protection` and `merge_pr` produce no URL and are none
#: of this check's business, and a bare past-tense `"commented"` is not matched either:
#: it is what an agent writes when summarising, and refusing it costs finished work for a
#: weak signal. The tool-shaped names below are the ones the live failures used.
_PRODUCES_A_URL = re.compile(
    r"create[_ ]?pr|open(?:ed)?[_ ]?(?:a )?pull|pull[_ ]?request"
    r"|post[_ ]?comment|create[_ ]?repo", re.I)


def _claimed_without_artifact(result: Any) -> str | None:
    """An action that says it produced something addressable, with no address.

    The companion to `_carries_tool_failure`, and the reason it needs one. That guard
    matched the tool failure ENVELOPE — `{"error": ...}` — so the next run of the same
    goal simply used a different shape:

        {"action": "create_pr", "result": "Failed to create PR: Repository not found",
         "url": None}

    Same lie, same COMPLETED, no envelope to match. Reading the prose for words like
    "failed" would be the third round of the same mistake, so this asks a structural
    question instead: you say you opened a pull request — where is it? A real one always
    came back with a URL, because that is what the tool returns.
    """
    if not isinstance(result, dict):
        return None
    action = result.get("action")
    if not isinstance(action, str) or not _PRODUCES_A_URL.search(action):
        return None
    url = result.get("url")
    if isinstance(url, str) and url.strip():
        return None
    # Anywhere in the submission will do. Agents put the address under `url`, `pr_url`,
    # `html_url`, or inside whatever the tool handed back, and which key it chose is not
    # what this is asking about — only whether an address is there at all.
    if _collect_urls(result):
        return None
    return action


def _carries_tool_failure(obj: Any, _depth: int = 0) -> str | None:
    """The tool failure a result is carrying as though it were the outcome, or None.

    Live failure, goal 373874b9. The goal named a repository that does not exist. Every
    tool said so, and every agent submitted that as its result:

        integrator: {"action": "create_pr",
                     "result": {"error": "cannot access repo owner/repo: 404 Not Found"},
                     "url": None}

    Both integrator tasks did this, the goal reported COMPLETED, and its final output was
    the 404 itself. Nothing objected: the required keys were present and non-empty, no
    URL was claimed so `_fabricated_urls` had nothing to compare, and `success` was not
    False because the integrator's schema has no `success`.

    This is the third shape in the same family. `_self_reported_failure` catches an agent
    that ADMITS failure. `_fabricated_urls` catches one that INVENTS a success.
    This catches one that hands back the failure itself and lets the pipeline read it as
    a success — the only one of the three that requires no dishonesty from the model,
    which is presumably why it survived longest.

    Detection is structural, not semantic: tools in this codebase fail with `ok: False`
    or an `error` key, so a result carrying that envelope is carrying a tool's refusal.
    A field that merely mentions an error in prose — the coder's `output` holding
    "404 Not Found" as text — is not matched, because describing a failure is not the
    same as submitting one.
    """
    if _depth > 6:
        return None
    if isinstance(obj, dict):
        if obj.get("ok") is False:
            reason = obj.get("error") or obj.get("reason") or "ok=false"
            return str(reason)[:200]
        err = obj.get("error")
        if err not in (None, "", [], {}, False):
            return str(err)[:200]
        for v in obj.values():
            found = _carries_tool_failure(v, _depth + 1)
            if found:
                return found
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found = _carries_tool_failure(v, _depth + 1)
            if found:
                return found
    return None


def _wrap_bare_payload(result: Any, schema_required: list[str]) -> dict | None:
    """The envelope a payload should have had, or None to leave it alone.

    Goal 5981fe39: the integrator called `github_create_issue`, the tool returned SUCCESS,
    GitHub issue #36 was created — and then it submitted

        {"issue_number": 36, "status": "created", "url": ".../issues/36", ", ": ...}

    against a schema requiring ["action", "result"]. Neither key was there, so the task
    failed with `output: None`. The issue number and the URL were thrown away, the coder
    downstream never learned what to fix, and the goal reported FAILED — while the work
    sat finished on GitHub. The model had assembled the object badly (note the literal
    ", " key); it had not failed to do the job.

    The rescue is deliberately narrow, because the guards below exist to stop agents
    claiming work they never did and this must not become the hole in them:

    - Only when a required key is actually missing. A valid envelope is untouched.
    - Only when the payload carries a URL. That is the artifact an agent cannot produce
      without having done something — every tool that makes one returns it. No URL, no
      evidence, and the envelope is all there is to judge by, so it still fails.
    - `action` is synthesised as a neutral word, never a produce-verb, so wrapping can
      neither trip `_claimed_without_artifact` nor blind it.
    - The wrapped object goes through every guard afterwards, unchanged. A payload that
      lies still fails; it just fails for lying rather than for punctuation.
    """
    if not isinstance(result, dict) or not schema_required:
        return None
    if not [k for k in schema_required if k not in result]:
        return None
    urls = _collect_urls(result)
    if not urls:
        return None

    action = result.get("action")
    url = result.get("url")
    # A copy, not the object itself. The caller updates `result` in place, so nesting the
    # live dict under its own "result" key made it self-referential and every guard that
    # walks the structure recursed until the stack gave out.
    payload = dict(result)
    wrapped: dict[str, Any] = {
        "result": payload,
        "action": action if isinstance(action, str) and action.strip() else "submitted",
        "url": url if isinstance(url, str) and url.strip() else urls[0],
    }
    # Anything else the schema demands cannot be invented from the payload, and guessing
    # is how a rescue turns into a fabrication.
    if [k for k in schema_required if k not in wrapped]:
        return None
    return wrapped


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
    # Recover a usable envelope before judging one. Mutated in place because all four
    # submission routes hand their own `result` straight to the caller that stores it,
    # so returning a new object here would be discarded by three of them.
    if isinstance(result, dict):
        wrapped = _wrap_bare_payload(result, schema_required)
        if wrapped is not None:
            logger.info("submission wrapped into %s — payload carried %s",
                        schema_required, wrapped["url"])
            result.clear()
            result.update(wrapped)
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

    unaddressed = _claimed_without_artifact(result)
    if unaddressed:
        return (
            f"submit_result rejected — you reported {unaddressed!r} but gave no URL for "
            "it. A pull request or comment that exists has an address, and the tool "
            "returns it. Call the tool and report the URL it gives back. If the call "
            "failed, say what failed and why, in your own words — do not report the "
            "action as though it happened."
        )

    carried = _carries_tool_failure(result)
    if carried:
        return (
            f"submit_result rejected — the result you submitted is a tool failure: "
            f"{carried!r}. That is the tool refusing, not the work being done, and "
            "handing it back as the outcome records the goal as completed with the error "
            "inside it. Fix the cause and call the tool again if you can — a wrong "
            "repository, path or number is usually the reason. If it cannot be fixed, "
            "say so plainly in your own words rather than submitting the failure."
        )

    not_code = _not_actually_code(result)
    if not_code:
        return (
            f"submit_result rejected — {not_code} Those fields carry the work itself: the "
            "next agent commits `code` at `path` exactly as you send them. If you could "
            "not write the code, say that in `output` and set success=false — do not put "
            "the explanation where the source belongs."
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
    _write_calls: dict[str, int] = {}  # writes made this task — see WRITE_TOOL_CALL_CAP

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

                ikey = _idempotency_key(task.id, tool_name, args_str)
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

            ikey = _idempotency_key(task.id, tool_name, args_str)
            logger.debug("[task=%s] Tool call: %s(%s…) ikey=%s…",
                         task.id, tool_name, args_str[:80], ikey[:12])

            if emit:
                emit("tool_call", {"task_id": task.id, "tool": tool_name, "args": args})

            # Checked BEFORE dispatch: the point is that the eighth comment is never
            # posted, not that it is posted and then regretted.
            capped = _over_write_cap(tool_name, _write_calls)
            if capped is not None:
                logger.warning("[task=%s] %s refused — %s", task.id, tool_name, capped)
                result = {"ok": False, "error": capped}
                if emit:
                    emit("tool_result", {"task_id": task.id, "tool": tool_name, "status": "REFUSED"})
                result_str = json.dumps(result)
                tool_results.append({"role": "tool", "tool_call_id": tc_id, "content": result_str})
                await db.save_message(task.id, "tool", result_str,
                                      sequence=len(messages) + iteration + 1, tool_call_id=tc_id)
                continue

            result = await _execute_tool_idempotent(task, tool_name, args_str, args, ikey)
            if tool_name in WRITE_TOOL_CALL_CAP and not (isinstance(result, dict) and result.get("error")):
                _write_calls[tool_name] = _write_calls.get(tool_name, 0) + 1

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

    # The human-in-the-loop gate, deliberately here rather than in a prompt. This runs
    # before the tool function is reached, so an agent that has been talked into merging
    # a stranger's pull request by text in an issue body still cannot: the instruction
    # reaches the model, and the model's only route to the action is through this line.
    try:
        await approval.check(task, tool_name, args)
    except approval.ApprovalRequired as gate:
        await db.delete_tool_call(ikey)
        return {
            WAITING_CREDENTIAL_SENTINEL: True,
            "credential": gate.credential_key,
            "provider": "approval",
            "message": f"Waiting for your approval: {gate.summary}",
            "connect_url": "/app/approvals",
            "approval_id": gate.approval_id,
        }
    except PermissionError as denied:
        # A refusal is a legitimate terminal outcome, not an error to retry. It is
        # returned as a tool result so the agent reads it and reports it.
        await db.settle_tool_call(ikey, json.dumps({"ok": False, "refused": True,
                                                    "error": str(denied)}), "SUCCESS")
        return {"ok": False, "refused": True, "error": str(denied)}

    try:
        result = await entry.fn(enriched_args)

        # A `WAITING_*` sentinel is control flow, not a result. It means the tool declined
        # to run and the task is about to park — nothing happened, so nothing may be
        # cached. Storing it would be fatal now that the key no longer varies by attempt:
        # the resumed task would hit the replay branch above, get the sentinel back, and
        # park again on every claim, forever, no matter what the user connects. Drop the
        # PENDING row created moments ago so the next attempt re-executes cleanly.
        if isinstance(result, dict) and (
            result.get(WAITING_CREDENTIAL_SENTINEL) or result.get(WAITING_WEBHOOK_SENTINEL)
        ):
            await db.delete_tool_call(ikey)
            return result

        # Scrub before persisting, not before returning. A cache hit replays `result_json`
        # straight back into model context, so the stored copy is a prompt — the live
        # result the tool just produced is not, and the caller may legitimately need it.
        await db.settle_tool_call(ikey, json.dumps(redaction.scrub_obj(result)), "SUCCESS")
        return result
    except Exception as e:
        error_str = str(e)
        logger.error("Tool %s failed: %s", tool_name, error_str)
        await db.settle_tool_call(ikey, None, "FAILED", error=redaction.scrub(error_str))
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
