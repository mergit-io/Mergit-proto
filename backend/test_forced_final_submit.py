"""Every path that returns a result must validate it — not just the happy one.

`_self_reported_failure` was wired into the `submit_result` branch of the tool loop, and
that is the only place it ran. Three other paths returned straight to the caller:

    agent_runner.py:283   JSON parsed out of a plain assistant message (no tool call)
    agent_runner.py:477   the forced final submit, after the iteration cap
    agent_runner.py:481   JSON parsed out of the forced final's message

Live proof, goal efb784fb on the deployed build. The task was "migrate auth.py to Rust".
The coder's only execution tool is `code_exec`, a PYTHON interpreter, so it could not run
what it had written and honestly submitted `success: False`. The guard rejected that ten
times — correctly — and the model had no way to make it true. The iteration cap hit, the
forced final fired, and its result was returned with no checks at all:

    {"code": "use std::collections::HashMap; ...", "path": "auth.py",
     "output": "Invalid username or password.", "success": false}

The integrator then interpolated it into PR #32, committing Rust into a `.py` file, and
the pipeline recorded four green tasks. The escape hatch outranked the gate.

A submission that contradicts itself must FAIL the task. Handing it downstream is what
produced the empty PR #30 and the broken PR #32; a failed task is visible and retryable,
a green pull request that fixes nothing is not.
"""
import asyncio
import importlib
import json
import os
import tempfile
import types

import pytest

from agent_registry import AGENT_REGISTRY

#: The coder's iteration cap — the forced final fires on the call after this many.
LOOP = AGENT_REGISTRY["coder"]["max_iterations"]


def _msg(tool_calls=None, content=""):
    """Shape an object like the LiteLLM response the code reads."""
    calls = []
    for i, (name, args) in enumerate(tool_calls or []):
        calls.append(types.SimpleNamespace(
            id=f"call_{i}",
            function=types.SimpleNamespace(name=name, arguments=json.dumps(args)),
        ))
    message = types.SimpleNamespace(content=content, tool_calls=calls or None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


#: The exact payload the coder submitted on goal efb784fb.
RUST_IN_A_PY_FILE = {
    "code": "use std::collections::HashMap;\n\nfn main() {}\n",
    "path": "auth.py",
    "output": "Invalid username or password.",
    "success": False,
}

VALID_CODER_RESULT = {
    "code": "def add(a, b):\n    return a + b\n",
    "path": "calc.py",
    "output": "3",
    "success": True,
}


class ScriptedLLM:
    """Replays a fixed list of responses, then repeats the last one forever.

    The agent loop calls until it converges, so the script says what happens on each
    call and the tail covers however many iterations the registry allows.
    """

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    async def __call__(self, model, messages, tools=None, tool_choice=None, **kwargs):
        self.calls += 1
        idx = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[idx]


@pytest.fixture()
def runner(monkeypatch):
    """The real agent_runner over a throwaway database, with only the LLM stubbed."""
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "forced.db"))
    monkeypatch.setattr(config.settings, "workspace_dir", os.path.join(tmp, "ws"))

    import db as _db
    importlib.reload(_db)
    asyncio.run(_db.init_db())

    import agent_runner as _ar
    importlib.reload(_ar)
    return _ar


def _coder_task():
    """A real row in the real schema — `run` writes messages against a foreign key."""
    import db as _db

    async def build():
        goal = await _db.create_goal("Migrate auth.py to Rust")
        tasks = await _db.create_tasks(
            [{"id": "t1", "agent": "coder",
              "description": "Migrate and enhance the auth.py code to Rust",
              "inputs": {}, "depends_on": []}],
            goal.id, goal.trace_id,
        )
        return tasks[0]

    return asyncio.run(build())


def _run(ar, llm, monkeypatch):
    monkeypatch.setattr(ar, "acompletion", llm)
    return asyncio.run(ar.run(_coder_task(), {}))


# ── The forced final submit, after the iteration cap ────────────────────────────

def test_the_forced_final_submit_refuses_a_result_that_reports_its_own_failure(runner, monkeypatch):
    """PR #32. Every loop iteration declines to submit, so the forced final fires and
    hands back `success: False`. That must raise, not return."""
    silent = _msg(content="Still working on the migration.")
    forced = _msg([("submit_result", {"result": RUST_IN_A_PY_FILE})])
    llm = ScriptedLLM(*([silent] * LOOP), forced, forced)

    with pytest.raises(RuntimeError) as exc:
        _run(runner, llm, monkeypatch)
    assert "success=False" in str(exc.value)


def test_the_forced_final_submit_refuses_a_result_that_is_missing_required_keys(runner, monkeypatch):
    silent = _msg(content="thinking")
    forced = _msg([("submit_result", {"result": {"code": "print(1)"}})])
    llm = ScriptedLLM(*([silent] * LOOP), forced, forced)

    with pytest.raises(RuntimeError) as exc:
        _run(runner, llm, monkeypatch)
    assert "path" in str(exc.value)


def test_the_forced_final_submit_gets_one_corrective_retry(runner, monkeypatch):
    """The cap is not the model's fault, so it is worth one more call with the reason
    attached — a missing key is trivially fixable and failing the goal over it is waste."""
    silent = _msg(content="thinking")
    bad = _msg([("submit_result", {"result": {"code": "print(1)"}})])
    good = _msg([("submit_result", {"result": VALID_CODER_RESULT})])
    llm = ScriptedLLM(*([silent] * LOOP), bad, good)

    assert _run(runner, llm, monkeypatch) == VALID_CODER_RESULT


def test_the_forced_final_submit_still_returns_a_coherent_result(runner, monkeypatch):
    """The whole point of the forced final is that a slow task degrades to a usable
    answer rather than failing the goal. That must keep working."""
    silent = _msg(content="thinking")
    forced = _msg([("submit_result", {"result": VALID_CODER_RESULT})])
    llm = ScriptedLLM(*([silent] * LOOP), forced)

    assert _run(runner, llm, monkeypatch) == VALID_CODER_RESULT


def test_the_forced_final_refuses_a_failing_result_parsed_from_plain_text(runner, monkeypatch):
    """The forced final has a second exit: JSON scraped out of the message when the model
    answers in prose instead of calling the tool. Same result, same rules."""
    silent = _msg(content="thinking")
    forced = _msg(content=json.dumps(RUST_IN_A_PY_FILE))
    llm = ScriptedLLM(*([silent] * LOOP), forced, forced)

    with pytest.raises(RuntimeError) as exc:
        _run(runner, llm, monkeypatch)
    assert "success=False" in str(exc.value)


# ── The in-loop plain-text exit ─────────────────────────────────────────────────

def test_json_in_a_plain_message_is_validated_like_a_submit_result(runner, monkeypatch):
    """`_try_parse_json_result` returns straight to the caller mid-loop. An agent that
    prints its JSON instead of calling the tool must not thereby skip every check."""
    failing = _msg(content=json.dumps(RUST_IN_A_PY_FILE))
    llm = ScriptedLLM(failing)

    with pytest.raises(RuntimeError):
        _run(runner, llm, monkeypatch)


def test_a_coherent_result_in_a_plain_message_is_still_accepted(runner, monkeypatch):
    llm = ScriptedLLM(_msg(content=json.dumps(VALID_CODER_RESULT)))
    assert _run(runner, llm, monkeypatch) == VALID_CODER_RESULT


def test_a_rejected_plain_text_result_is_re_prompted_before_the_cap(runner, monkeypatch):
    """Rejection must leave the agent a way back: tell it what was wrong and let it
    answer again, rather than failing on the first bad shape."""
    failing = _msg(content=json.dumps(RUST_IN_A_PY_FILE))
    good = _msg([("submit_result", {"result": VALID_CODER_RESULT})])
    llm = ScriptedLLM(failing, good)

    assert _run(runner, llm, monkeypatch) == VALID_CODER_RESULT
    assert llm.calls == 2, "the agent was not given a second turn after the rejection"
