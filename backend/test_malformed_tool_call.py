"""Malformed JSON from the model must re-prompt, not kill the task.

Live failure, goal 32d630f2 — the run that was supposed to raise a pull request.

The coder produced Rust containing backticks where quotes belong:

    users.insert("admin`.to_string(), "1234`.to_string());

That string was interpolated into the next task's inputs. When the review researcher
built its tool call around it, the arguments came back as invalid JSON, and
`agent_runner.py` parsed them with a bare:

    args = json.loads(args_str)

which raised `json.JSONDecodeError: Unterminated string starting at line 1 column 12`
straight out of `run()`. The task went to FAILED, the integrator that depended on it was
never promoted, and no pull request was ever opened.

Every other invalid thing a model can send is answered with a rejection message and
another turn. A syntax error in its own tool call was the one shape that killed the task
outright — the same class as the `'str' object has no attribute 'get'` crash fixed in
1246fb0, one layer up.
"""
import asyncio
import importlib
import json
import os
import tempfile
import types

import pytest

from agent_registry import AGENT_REGISTRY

LOOP = AGENT_REGISTRY["coder"]["max_iterations"]

#: The shape that actually arrived: a string opened with " and closed with a backtick.
BROKEN_ARGS = '{"code": "users.insert("admin`.to_string());", "path": "auth.rs"}'

VALID_RESULT = {"code": "def add(a, b):\n    return a + b\n", "path": "calc.py",
                "output": "3", "success": True}


def _raw_msg(name: str, arguments: str, content: str = ""):
    """A tool call whose arguments are a RAW string — valid JSON or not."""
    call = types.SimpleNamespace(
        id="call_0", function=types.SimpleNamespace(name=name, arguments=arguments))
    message = types.SimpleNamespace(content=content, tool_calls=[call])
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _msg(tool_calls=None, content=""):
    calls = []
    for i, (name, args) in enumerate(tool_calls or []):
        calls.append(types.SimpleNamespace(
            id=f"call_{i}",
            function=types.SimpleNamespace(name=name, arguments=json.dumps(args))))
    message = types.SimpleNamespace(content=content, tool_calls=calls or None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class ScriptedLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    async def __call__(self, model, messages, tools=None, tool_choice=None, **kwargs):
        self.calls += 1
        self.last_messages = messages
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


@pytest.fixture()
def runner(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "malformed.db"))
    monkeypatch.setattr(config.settings, "workspace_dir", os.path.join(tmp, "ws"))

    import db as _db
    importlib.reload(_db)
    asyncio.run(_db.init_db())

    import agent_runner as _ar
    importlib.reload(_ar)
    return _ar


def _task():
    import db as _db

    async def build():
        goal = await _db.create_goal("Review the Rust implementation", user_id="usr_legacy_demo")
        tasks = await _db.create_tasks(
            [{"id": "t1", "agent": "coder", "description": "Fix the login helper",
              "inputs": {}, "depends_on": []}],
            goal.id, goal.trace_id)
        return tasks[0]

    return asyncio.run(build())


def _run(ar, llm, monkeypatch):
    monkeypatch.setattr(ar, "acompletion", llm)
    return asyncio.run(ar.run(_task(), {}))


def test_a_tool_call_with_invalid_json_does_not_kill_the_task(runner, monkeypatch):
    """The exact failure from goal 32d630f2."""
    llm = ScriptedLLM(
        _raw_msg("code_exec", BROKEN_ARGS),
        _msg([("submit_result", {"result": VALID_RESULT})]),
    )

    assert _run(runner, llm, monkeypatch) == VALID_RESULT
    assert llm.calls == 2, "the agent was not given another turn after the parse error"


def test_the_agent_is_told_what_was_wrong_with_its_arguments(runner, monkeypatch):
    """A rejection the model cannot read teaches it nothing — the message has to name
    the tool and say the arguments were not valid JSON."""
    llm = ScriptedLLM(
        _raw_msg("code_exec", BROKEN_ARGS),
        _msg([("submit_result", {"result": VALID_RESULT})]),
    )
    _run(runner, llm, monkeypatch)

    fed_back = " ".join(str(m.get("content", "")) for m in llm.last_messages)
    assert "code_exec" in fed_back
    assert "JSON" in fed_back or "json" in fed_back


def test_a_malformed_submit_result_is_re_prompted_too(runner, monkeypatch):
    """submit_result is parsed by the same line, so it failed the same way."""
    llm = ScriptedLLM(
        _raw_msg("submit_result", '{"result": {"code": "x`", "path": "a.py"'),
        _msg([("submit_result", {"result": VALID_RESULT})]),
    )

    assert _run(runner, llm, monkeypatch) == VALID_RESULT


def test_the_forced_final_uses_its_second_attempt_after_a_parse_error(runner, monkeypatch):
    """The forced final is allowed two calls. A JSON error on the first threw straight
    out of the retry loop, so the second was never made and the task failed anyway."""
    silent = _msg(content="thinking")
    llm = ScriptedLLM(
        *([silent] * LOOP),
        _raw_msg("submit_result", '{"result": {"code": "broken`'),
        _msg([("submit_result", {"result": VALID_RESULT})]),
    )

    assert _run(runner, llm, monkeypatch) == VALID_RESULT


def test_repeated_garbage_still_ends_the_task_rather_than_looping_forever(runner, monkeypatch):
    """Re-prompting must not become an infinite loop: a model that only ever emits
    broken JSON runs out of iterations and the task fails, loudly."""
    llm = ScriptedLLM(_raw_msg("code_exec", BROKEN_ARGS))

    with pytest.raises(RuntimeError):
        _run(runner, llm, monkeypatch)
