"""Two defects from the first real GPT-4.1 run, goal e6b9529c.

The run succeeded — PR #43 fixed `largest()` in calc.py correctly, and the envelope
recovery added the day before rescued an integrator submission that would otherwise have
failed the goal. Two things went wrong around that success.

1. The integrator posted EIGHT near-identical comments on the PR, at 18:29:13, :16, :19,
   :22, :25, :28, :31 and :34 — one every three seconds until it ran out of turns. Raising
   the integrator's budget from 8 to 14 iterations the day before is what gave it the room:
   with the PR already open and nothing left to do, it filled the rest with chatter. The
   budget was right; the missing half was a reason to stop.

2. The plan ended with a coder task, AFTER the PR was opened, told to "run the fixed
   calc.py to prove the fix works". It read calc.py from main rather than the PR branch, so
   its output was the ORIGINAL buggy source — and being terminal, that became the goal's
   final answer. A user reading a COMPLETED goal saw `biggest = 0`, the very bug that had
   just been fixed.
"""
import pytest

import agent_runner as ar
from orchestrator import PlanSchema, TaskSpec, _validate_plan


# ── 1. Repeated write calls ─────────────────────────────────────────────────────

def test_comment_tool_is_capped_per_task():
    cap = ar.WRITE_TOOL_CALL_CAP["github_post_comment"]
    assert cap >= 2, "the documented pattern comments on the issue and may comment on the PR"
    assert cap < 8, "eight is what the live run produced; the cap exists to stop that"


def test_a_call_within_the_cap_is_allowed():
    counts = {}
    for _ in range(ar.WRITE_TOOL_CALL_CAP["github_post_comment"]):
        assert ar._over_write_cap("github_post_comment", counts) is None
        counts["github_post_comment"] = counts.get("github_post_comment", 0) + 1


def test_the_call_past_the_cap_is_refused_with_a_reason():
    counts = {"github_post_comment": ar.WRITE_TOOL_CALL_CAP["github_post_comment"]}
    refusal = ar._over_write_cap("github_post_comment", counts)
    assert refusal is not None
    # The model has to learn what to do instead, or it simply tries again.
    assert "submit_result" in refusal.lower()


def test_read_tools_are_never_capped():
    """Reading twenty files is how a repo gets surveyed. Only writes leave a mark."""
    counts = {"github_read_file": 50, "github_list_dir": 50, "web_search": 50}
    for tool in counts:
        assert ar._over_write_cap(tool, counts) is None


def test_every_capped_tool_writes_something_durable():
    """A cap on a read tool would break surveying; this pins the list to writes only."""
    for tool in ar.WRITE_TOOL_CALL_CAP:
        assert tool.startswith("github_"), tool
        assert not any(r in tool for r in ("read", "list", "get", "search")), tool


# ── 2. A coder must not be terminal after the pull request ──────────────────────

def _plan(tasks, terminal):
    return PlanSchema(
        tasks=[TaskSpec(id=i, agent=a, description=d, inputs=inp or {}, depends_on=dep or [])
               for i, a, d, inp, dep in tasks],
        terminal=terminal,
        reasoning="test plan",
    )


REPO = {"repo": "o/r"}


def test_the_shape_that_shipped_pre_fix_code_as_the_answer():
    """researcher -> coder -> integrator(PR) -> coder(verify), terminal on the verify."""
    plan = _plan([
        ("t1", "researcher", "Read calc.py and find the bug", REPO, []),
        ("t2", "coder", "Write a fix for the bug", {"code_context": "{{t1.output}}"}, ["t1"]),
        ("t3", "integrator", "Open a pull request with the fix",
         {**REPO, "fixed_code": "{{t2.output.code}}", "file_path": "{{t2.output.path}}"}, ["t2"]),
        ("t4", "coder", "Run the fixed calc.py to prove the fix works", REPO, ["t3"]),
    ], terminal="t4")

    with pytest.raises(ValueError) as e:
        _validate_plan(plan)
    message = str(e.value)
    assert "t4" in message and "t3" in message
    assert "pull request" in message


def test_the_integrator_that_opened_the_pr_may_be_terminal():
    plan = _plan([
        ("t1", "researcher", "Read calc.py and find the bug", REPO, []),
        ("t2", "coder", "Write a fix for the bug", {"code_context": "{{t1.output}}"}, ["t1"]),
        ("t3", "integrator", "Open a pull request with the fix",
         {**REPO, "fixed_code": "{{t2.output.code}}", "file_path": "{{t2.output.path}}"}, ["t2"]),
    ], terminal="t3")
    _validate_plan(plan)


def test_a_writer_may_still_close_out_a_pull_request_run():
    """Summarising what shipped is a legitimate final step; dumping source is not."""
    plan = _plan([
        ("t1", "researcher", "Read calc.py and find the bug", REPO, []),
        ("t2", "coder", "Write a fix for the bug", {"code_context": "{{t1.output}}"}, ["t1"]),
        ("t3", "integrator", "Open a pull request with the fix",
         {**REPO, "fixed_code": "{{t2.output.code}}", "file_path": "{{t2.output.path}}"}, ["t2"]),
        ("t4", "writer", "Summarise the fix and link the PR", {"data": "{{t3.output}}"}, ["t3"]),
    ], terminal="t4")
    _validate_plan(plan)


def test_a_coder_terminal_is_fine_when_no_pull_request_is_involved():
    """"Run this script" ends with the coder, and always did."""
    plan = _plan([
        ("t1", "coder", "Write and run a script that prints the first 10 primes", {"task": "primes"}, []),
    ], terminal="t1")
    _validate_plan(plan)
