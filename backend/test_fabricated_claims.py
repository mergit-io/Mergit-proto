"""An agent may not claim an outcome it never produced.

Live failure, goal 00605510 — run on a build carrying every other guard in this repo.

The integrator submitted:

    {"action": "Raised PR and posted comment",
     "result": "PR raised and comment posted successfully",
     "url": "https://github.com/OfficialAbhinavSingh/mergit-e2e-sandbox/pull/1"}

No pull request was created. The newest PR in that repository is #34; #1 does not exist.
The goal reported COMPLETED, and the integrator posted a public comment on the issue
announcing the PR, linking to nothing.

Every other guard in this codebase validates the SHAPE of a submission — empty content,
wrong language, wrong path, a diff that changes nothing, an admission of failure. This
submission is shape-perfect. Both required keys are present and non-empty and no field
says `False`. Nothing compared the claim against what the task actually DID.

Tool calls are recorded as they happen, so a URL that no tool ever returned is detectable.
That is the whole idea: an outcome may only be claimed if some tool produced it.

The second half is the same lie in a smaller space. The coder's `success` field that run:

    success = "The task was to implement a secure authentication system in Rust, but the
               provided code_exec function only supports Python code execution. Therefore
               the task c..."

`_self_reported_failure` tests `result.get("success") is False`, so a prose admission of
failure sitting in a boolean field passes untouched.
"""
import asyncio
import importlib
import json
import os
import tempfile
import types

import pytest

from agent_registry import AGENT_REGISTRY
from agent_runner import _fabricated_urls, _self_reported_failure, _submission_problem

CODER_REQUIRED = AGENT_REGISTRY["coder"]["output_schema"]["required"]
INTEGRATOR_REQUIRED = AGENT_REGISTRY["integrator"]["output_schema"]["required"]

PHANTOM = "https://github.com/OfficialAbhinavSingh/mergit-e2e-sandbox/pull/1"
REAL = "https://github.com/OfficialAbhinavSingh/mergit-e2e-sandbox/pull/35"


# ── Claiming a pull request that no tool produced ───────────────────────────────

def test_the_exact_integrator_result_that_invented_a_pull_request_is_rejected():
    result = {"action": "Raised PR and posted comment",
              "result": "PR raised and comment posted successfully", "url": PHANTOM}
    assert _fabricated_urls(result, known=set()) == [PHANTOM]


def test_a_url_a_tool_really_returned_is_accepted():
    result = {"action": "created_pr", "result": {"pr_url": REAL}, "url": REAL}
    assert _fabricated_urls(result, known={REAL}) == []


def test_a_url_the_task_was_given_in_its_inputs_is_accepted():
    """"Merge PR #35" hands the integrator the URL up front. Referring to what you were
    told is not a claim to have made it."""
    result = {"action": "merged", "result": f"merged {REAL}"}
    assert _fabricated_urls(result, known={REAL}) == []


def test_only_pull_request_urls_are_policed():
    """A researcher cites file and repository URLs it assembled itself, and that is its
    job. Only a claim to have PRODUCED something is checked."""
    result = {"summary": "s", "key_points": ["k"],
              "sources": ["https://github.com/o/r/blob/main/auth.py",
                          "https://github.com/o/r"]}
    assert _fabricated_urls(result, known=set()) == []


def test_an_issue_comment_url_is_policed_too():
    """The same lie in the other shape: reporting a comment that was never posted."""
    comment = "https://github.com/o/r/issues/1#issuecomment-5302011418"
    result = {"action": "commented", "result": comment}
    assert _fabricated_urls(result, known=set()) == [comment]


def test_urls_are_found_however_deeply_they_are_nested():
    result = {"action": "a", "result": {"steps": [{"pr": {"url": PHANTOM}}]}}
    assert _fabricated_urls(result, known=set()) == [PHANTOM]


def test_the_rejection_reaches_the_agent_through_submission_problem():
    result = {"action": "Raised PR and posted comment",
              "result": "PR raised and comment posted successfully", "url": PHANTOM}
    problem = _submission_problem(result, INTEGRATOR_REQUIRED, "Raise a PR", known_urls=set())
    assert problem is not None and "pull/1" in problem


def test_a_task_with_no_url_claim_is_unaffected():
    result = {"action": "read", "result": {"lines": 40}}
    assert _submission_problem(result, INTEGRATOR_REQUIRED, "Read the file",
                               known_urls=set()) is None


# ── `success` has to be a boolean ───────────────────────────────────────────────

def test_a_prose_explanation_in_the_success_field_is_rejected():
    """The live coder payload from goal 00605510: an admission of failure, in the field
    that is supposed to hold True or False."""
    result = {"code": "fn main() {}", "path": "auth.rs", "output": "not executed",
              "success": "The task was to implement a secure authentication system in "
                         "Rust, but code_exec only supports Python. Therefore the task "
                         "could not be completed."}
    problem = _self_reported_failure(result, CODER_REQUIRED)
    assert problem is not None and "success" in problem


def test_the_string_false_still_counts_as_failure():
    """Models write JSON by hand. "false" means false and must not be read as a pass."""
    result = {"code": "x", "path": "a.py", "output": "o", "success": "false"}
    assert _self_reported_failure(result, CODER_REQUIRED) is not None


def test_the_string_true_is_tolerated():
    """The benign half of the same habit — accepted rather than bounced, because a
    re-prompt over a spelling of True costs a turn and teaches nothing."""
    result = {"code": "x", "path": "a.py", "output": "o", "success": "True"}
    assert _self_reported_failure(result, CODER_REQUIRED) is None


def test_a_real_boolean_still_works():
    result = {"code": "x", "path": "a.py", "output": "o", "success": True}
    assert _self_reported_failure(result, CODER_REQUIRED) is None


# ── End to end through the real agent loop ──────────────────────────────────────

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
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


@pytest.fixture()
def runner(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "fab.db"))
    monkeypatch.setattr(config.settings, "workspace_dir", os.path.join(tmp, "ws"))
    import db as _db
    importlib.reload(_db)
    asyncio.run(_db.init_db())
    import agent_runner as _ar
    importlib.reload(_ar)
    return _ar


def _integrator_task():
    import db as _db

    async def build():
        goal = await _db.create_goal("Raise a PR for the Rust migration")
        rows = await _db.create_tasks(
            [{"id": "t1", "agent": "integrator", "description": "Raise a PR with the Rust code",
              "inputs": {}, "depends_on": []}], goal.id, goal.trace_id)
        return rows[0]

    return asyncio.run(build())


def test_an_invented_pull_request_does_not_finish_the_task(runner, monkeypatch):
    """The live shape end to end: the agent calls no tool at all and announces a PR."""
    invented = {"action": "Raised PR and posted comment",
                "result": "PR raised and comment posted successfully", "url": PHANTOM}
    llm = ScriptedLLM(_msg([("submit_result", {"result": invented})]))
    monkeypatch.setattr(runner, "acompletion", llm)

    with pytest.raises(RuntimeError):
        asyncio.run(runner.run(_integrator_task(), {}))


def test_a_pull_request_a_tool_really_opened_is_accepted(runner, monkeypatch):
    """The honest path must stay open: call github_pr, then report what it returned."""
    async def fake_github_pr(args):
        return {"action": "create_pr", "ok": True, "url": REAL, "result": {"url": REAL}}

    from tools import TOOL_REGISTRY
    monkeypatch.setitem(TOOL_REGISTRY, "github_pr",
                        TOOL_REGISTRY["github_pr"]._replace(fn=fake_github_pr)
                        if hasattr(TOOL_REGISTRY["github_pr"], "_replace")
                        else TOOL_REGISTRY["github_pr"])
    monkeypatch.setattr(TOOL_REGISTRY["github_pr"], "fn", fake_github_pr, raising=False)

    reported = {"action": "created_pr", "result": {"pr_url": REAL}}
    llm = ScriptedLLM(
        _msg([("github_pr", {"repo": "o/r", "title": "t", "body": "b",
                             "head_branch": "x", "files": []})]),
        _msg([("submit_result", {"result": reported})]),
    )
    monkeypatch.setattr(runner, "acompletion", llm)

    assert asyncio.run(runner.run(_integrator_task(), {})) == reported
