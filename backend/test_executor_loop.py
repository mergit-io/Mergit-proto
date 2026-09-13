"""The interleaved executor: does it actually interleave, and can it still not lie?

The loop replaces a plan committed before any tool ran with one revised while the work
happens. What it must NOT replace is the checking: `finish` goes through the same guards
as `submit_result`, so an agent cannot end a run by claiming an outcome it never produced.

The model is stubbed throughout — these pin the loop's control flow, not GPT-4.1's
judgement. A scripted sequence of tool calls stands in for what a model would decide.
"""
import asyncio
import json
import types

import pytest

import executor


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


def _call(name, args, cid=None):
    return types.SimpleNamespace(
        id=cid or ("c_" + name),
        function=types.SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _response(msg):
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


class _Task:
    id = "g1_op"
    goal_id = "g1"
    description = "do the thing"
    agent_name = "operator"


@pytest.fixture()
def loop(monkeypatch):
    """Drive the loop with a scripted list of assistant turns."""
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(executor.db, "save_message", _noop)

    async def _goal(_gid):
        return types.SimpleNamespace(goal_text="Fix the bug in calc.py")
    monkeypatch.setattr(executor.db, "get_goal", _goal)

    def install(turns, tool_results=None):
        """turns: list of _Msg. tool_results: dict tool_name -> result dict."""
        seen = {"turns": 0, "tools": [], "messages": None}

        async def _acompletion(role=None, model=None, messages=None, **kw):
            seen["turns"] += 1
            seen["messages"] = messages
            if seen["turns"] > len(turns):
                # Ran past the script: keep the loop fed rather than raising IndexError,
                # so a test that expected fewer turns fails on its assertion, not here.
                return _response(_Msg(content="(script exhausted)"))
            return _response(turns[seen["turns"] - 1])

        async def _exec_tool(task, name, raw, args, ikey):
            seen["tools"].append((name, args))
            return (tool_results or {}).get(name, {"ok": True})

        monkeypatch.setattr(executor, "acompletion", _acompletion)
        monkeypatch.setattr(executor, "_execute_tool_idempotent", _exec_tool)
        return seen

    return install


def run(coro):
    return asyncio.run(coro)


# ── The loop interleaves ────────────────────────────────────────────────────────

def test_a_tool_result_comes_back_before_the_next_decision(loop):
    """The whole thesis: turn two is chosen having seen what turn one returned."""
    seen = loop(
        [
            _Msg(tool_calls=[_call("github_read_file", {"repo": "o/r", "path": "calc.py"})]),
            _Msg(tool_calls=[_call("finish", {"summary": "read the file"})]),
        ],
        tool_results={"github_read_file": {"ok": True, "content": "biggest = 0"}},
    )
    out = run(executor.run_loop(_Task(), {}))

    assert out["summary"] == "read the file"
    assert seen["tools"][0][0] == "github_read_file"
    # The file's contents must be in the context the second decision was made from.
    assert any("biggest = 0" in (m.get("content") or "")
               for m in seen["messages"] if m.get("role") == "tool")


def test_the_plan_is_recorded_and_revised_without_ending_the_run(loop):
    first = [{"step": "read calc.py", "status": "in_progress"}]
    revised = [{"step": "read calc.py", "status": "done"},
               {"step": "open a PR", "status": "pending", "note": "found the bug"}]
    emitted = []
    seen = loop([
        _Msg(tool_calls=[_call("update_plan", {"items": first})]),
        _Msg(tool_calls=[_call("update_plan", {"items": revised})]),
        _Msg(tool_calls=[_call("finish", {"summary": "done"})]),
    ])
    out = run(executor.run_loop(_Task(), {}, emit=lambda n, d: emitted.append((n, d))))

    assert out["plan"] == revised, "the run keeps the LAST plan, not the first"
    assert [n for n, _ in emitted].count("plan_update") == 2
    assert seen["tools"] == [], "update_plan is the loop's own tool, not a registry call"


def test_a_turn_with_no_tool_call_is_prompted_rather_than_ending_the_run(loop):
    """A model thinking out loud has not concluded anything."""
    loop([
        _Msg(content="Let me think about this."),
        _Msg(tool_calls=[_call("finish", {"summary": "done"})]),
    ])
    out = run(executor.run_loop(_Task(), {}))
    assert out["summary"] == "done"


def test_a_failing_tool_is_reported_back_and_the_run_continues(loop):
    """A failure is information about the world, not the end of the run."""
    seen = loop(
        [
            _Msg(tool_calls=[_call("github_list_prs", {"repo": "o/r"})]),
            _Msg(tool_calls=[_call("finish", {"summary": "listed what I could"})]),
        ],
        tool_results={"github_list_prs": {"ok": False, "error": "404 Not Found"}},
    )
    out = run(executor.run_loop(_Task(), {}))

    assert out["summary"] == "listed what I could"
    assert any("404 Not Found" in (m.get("content") or "")
               for m in seen["messages"] if m.get("role") == "tool")


# ── It still cannot lie ─────────────────────────────────────────────────────────

def test_finish_claiming_a_url_no_tool_returned_is_rejected(loop):
    """The guard that made goal 373874b9 impossible applies to `finish` too."""
    seen = loop([
        _Msg(tool_calls=[_call("finish", {
            "summary": "Opened the pull request",
            "url": "https://github.com/o/r/pull/99"}, cid="c1")]),
        _Msg(tool_calls=[_call("finish", {"summary": "I could not open a pull request"},
                               cid="c2")]),
    ])
    out = run(executor.run_loop(_Task(), {}))

    assert out["summary"] == "I could not open a pull request"
    # The rejection has to reach the model, or it simply repeats itself.
    assert any("pull/99" in (m.get("content") or "")
               for m in seen["messages"] if m.get("role") == "tool")


def test_a_url_a_tool_did_return_is_accepted(loop):
    loop(
        [
            _Msg(tool_calls=[_call("github_pr", {"repo": "o/r"})]),
            _Msg(tool_calls=[_call("finish", {
                "summary": "Opened the pull request",
                "url": "https://github.com/o/r/pull/44"})]),
        ],
        tool_results={"github_pr": {"ok": True, "url": "https://github.com/o/r/pull/44"}},
    )
    out = run(executor.run_loop(_Task(), {}))
    assert out["url"] == "https://github.com/o/r/pull/44"


def test_repeated_writes_are_capped_inside_the_loop_too(loop):
    """The eight-comment run must not become possible again via a different executor."""
    cap = executor.WRITE_TOOL_CALL_CAP["github_post_comment"]
    turns = [_Msg(tool_calls=[_call("github_post_comment", {"repo": "o/r", "body": f"note {i}"},
                                    cid=f"c{i}")])
             for i in range(cap + 3)]
    turns.append(_Msg(tool_calls=[_call("finish", {"summary": "commented"})]))
    seen = loop(turns, tool_results={"github_post_comment": {"ok": True}})
    run(executor.run_loop(_Task(), {}))

    posted = [t for t, _ in seen["tools"] if t == "github_post_comment"]
    assert len(posted) == cap, f"expected the cap ({cap}) to hold, got {len(posted)}"


# ── Budgets ─────────────────────────────────────────────────────────────────────

def test_a_run_that_never_finishes_is_an_error_not_a_success(loop, monkeypatch):
    monkeypatch.setattr(executor.settings, "loop_max_turns", 3)
    loop([_Msg(tool_calls=[_call("github_read_file", {"repo": "o/r", "path": "a.py"})])] * 3)

    with pytest.raises(RuntimeError) as e:
        run(executor.run_loop(_Task(), {}))
    assert "3 turns" in str(e.value)


def test_the_deadline_ends_a_run_whose_tools_are_slow(loop, monkeypatch):
    monkeypatch.setattr(executor.settings, "loop_deadline_seconds", 1)
    clock = {"t": 0.0}
    monkeypatch.setattr(executor.time, "monotonic", lambda: clock["t"])

    def _advance(*_a, **_k):
        clock["t"] += 10
        return _response(_Msg(tool_calls=[_call("github_read_file", {"repo": "o/r", "path": "a.py"})]))

    async def _acompletion(**kw):
        return _advance()
    loop([])
    monkeypatch.setattr(executor, "acompletion", _acompletion)

    with pytest.raises(RuntimeError) as e:
        run(executor.run_loop(_Task(), {}))
    assert "deadline" in str(e.value)


# ── Wiring ──────────────────────────────────────────────────────────────────────

def test_the_operator_is_offered_every_registered_tool():
    from agent_registry import AGENT_REGISTRY
    from tools import TOOL_REGISTRY

    assert AGENT_REGISTRY["operator"]["allowed_tools"] == sorted(TOOL_REGISTRY)


def test_dag_remains_the_default():
    from config import settings
    assert settings.executor_mode == "dag", "the loop must stay opt-in until it earns it"


def test_a_loop_run_mints_no_proof_yet():
    """Pins a known gap so it cannot drift into a silent claim.

    `economy.record_proof` only mints for a role in ROLES. `operator` is not one, so a
    loop run records nothing in the ledger. Adding it to ROLES would make the number go
    up without the meaning: a proof records a specialist doing a unit of work, and "the
    whole goal" is not that. Subagent dispatch is what makes loop proofs real.
    """
    import economy
    from agent_registry import AGENT_REGISTRY

    assert "operator" in AGENT_REGISTRY
    assert "operator" not in economy.ROLES
