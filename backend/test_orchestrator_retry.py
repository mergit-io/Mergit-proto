"""A rejected plan must be told *why* before the orchestrator asks again.

Observed on a real goal (sandbox issue #19, "make some docs for new contributors"):
the orchestrator produced the same two-task plan five times in a row, was rejected five
times with the same message, and the goal FAILED at PLANNING without ever running a
task.

The cause is the retry loop's guard:

    if last_error and "invalid" in last_error.lower():
        messages.append(...)      # tell the model what was wrong

None of `_validate_plan`'s messages contain the word "invalid", so the branch never
fired. Every retry re-sent a byte-identical prompt to a near-deterministic model
(temperature 0.1) and unsurprisingly got a byte-identical plan back. The retry budget
was spent re-asking the same question rather than correcting anything.
"""
import asyncio
import json
import types

import pytest

import orchestrator
from state import GoalRow


def _goal(text="make some docs for new contributors and open a PR"):
    return GoalRow(
        id="g-test-0001", title="t", goal_text=text, status="PLANNING",
        output=None, error=None, plan_json=None, terminal_task_id=None,
        trace_id="tr-1", created_at=0, updated_at=0,
    )


def _tool_response(plan: dict):
    """Shape an LLM response carrying `plan` as a submit_plan tool call."""
    call = types.SimpleNamespace(function=types.SimpleNamespace(arguments=json.dumps(plan)))
    msg = types.SimpleNamespace(tool_calls=[call], content=None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


#: Rejected: an integrator terminal with nothing that authored content.
BAD_PLAN = {
    "reasoning": "read the repo then open a PR",
    "tasks": [
        {"id": "t1", "agent": "researcher", "description": "read repo",
         "inputs": {"repo": "o/r"}, "depends_on": []},
        {"id": "t2", "agent": "integrator", "description": "open PR",
         "inputs": {"repo": "o/r"}, "depends_on": ["t1"]},
    ],
    "terminal": "t2",
}

#: Accepted: the writer authors the docs, the integrator publishes them.
GOOD_PLAN = {
    "reasoning": "read, write the docs, open a PR",
    "tasks": [
        {"id": "t1", "agent": "researcher", "description": "read repo",
         "inputs": {"repo": "o/r"}, "depends_on": []},
        {"id": "t2", "agent": "writer", "description": "write docs",
         "inputs": {"data": "{{t1.output}}"}, "depends_on": ["t1"]},
        {"id": "t3", "agent": "integrator", "description": "open PR",
         "inputs": {"repo": "o/r", "docs": "{{t2.output}}"}, "depends_on": ["t2"]},
    ],
    "terminal": "t3",
}


class Recorder:
    """Replays scripted plans and keeps the `messages` it was asked with each time."""

    def __init__(self, *plans):
        self.plans = list(plans)
        self.calls: list[list[dict]] = []

    async def __call__(self, **kwargs):
        # Copy: the caller mutates the same list between attempts.
        self.calls.append([dict(m) for m in kwargs["messages"]])
        plan = self.plans[min(len(self.calls) - 1, len(self.plans) - 1)]
        return _tool_response(plan)


def test_a_rejected_plan_is_explained_to_the_model_before_retrying(monkeypatch):
    rec = Recorder(BAD_PLAN, GOOD_PLAN)
    monkeypatch.setattr(orchestrator, "acompletion", rec)

    result = asyncio.run(orchestrator.plan(_goal()))

    assert len(rec.calls) >= 2, "the orchestrator gave up without retrying"
    second = rec.calls[1]
    assert len(second) > len(rec.calls[0]), (
        "the retry prompt was identical to the first — the model was re-asked the same "
        "question and had no way to know its plan had been rejected"
    )
    feedback = second[-1]["content"].lower()
    assert "integrator" in feedback and "writer" in feedback, (
        f"the retry prompt does not carry the rejection reason: {second[-1]['content'][:200]!r}"
    )
    assert result.terminal == "t3"


def test_the_model_is_corrected_for_every_kind_of_rejection(monkeypatch):
    """Not just the ones whose text happens to contain a magic word."""
    broken = {
        "reasoning": "x",
        "tasks": [{"id": "t1", "agent": "researcher", "description": "x",
                   "inputs": {}, "depends_on": []}],
        "terminal": "t9",  # not a task id
    }
    rec = Recorder(broken, GOOD_PLAN)
    monkeypatch.setattr(orchestrator, "acompletion", rec)

    asyncio.run(orchestrator.plan(_goal()))

    assert len(rec.calls) >= 2
    assert "t9" in rec.calls[1][-1]["content"], (
        "a structural rejection was not fed back either; the retry loop only ever "
        "corrected errors whose wording contained 'invalid'"
    )


def test_a_plan_that_passes_first_time_gets_no_correction(monkeypatch):
    rec = Recorder(GOOD_PLAN)
    monkeypatch.setattr(orchestrator, "acompletion", rec)

    result = asyncio.run(orchestrator.plan(_goal()))

    assert len(rec.calls) == 1
    assert result.terminal == "t3"


def test_the_rejection_message_says_where_the_writer_goes(monkeypatch):
    """The advice was "add a writer task after it", which is right for a fetch-then-
    present plan and wrong for author-then-publish: putting a writer *after* the
    integrator makes the writer terminal and leaves the PR with nothing to publish.
    For a goal that publishes content the writer belongs before the integrator."""
    from orchestrator import PlanSchema, TaskSpec

    p = PlanSchema(
        reasoning="x",
        tasks=[
            TaskSpec(id="t1", agent="researcher", description="x", inputs={}, depends_on=[]),
            TaskSpec(id="t2", agent="integrator", description="x", inputs={}, depends_on=["t1"]),
        ],
        terminal="t2",
    )
    with pytest.raises(ValueError) as exc:
        orchestrator._validate_plan(p)

    message = str(exc.value).lower()
    assert "before" in message, (
        f"the rejection tells the model to put a writer after the integrator, which "
        f"cannot produce the deliverable: {str(exc.value)!r}"
    )
