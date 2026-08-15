"""A task must be given work it has the tools to do.

Goal efb784fb planned four tasks, and the last one was:

    writer: "Write a review of the PR, ensuring it meets the requirements and is
             properly tested"
    inputs: {"pr_number": "{{t3.output.pr_number}}", "repo": "OfficialAbhinavSingh/..."}

The writer's entire toolset is `['file_ops']`. It has no `github_get_pr`, no
`github_get_pr_files`, no network — it cannot open a pull request, and nothing in the
inputs contains the diff either. Both values are REFERENCES to something it would have to
fetch, and fetching is exactly what it cannot do.

So it invented an answer: "The PR meets the requirements and is properly tested." PR #32
committed Rust into a `.py` file. The review was not wrong by accident; it was structurally
incapable of being right, and it read as a clean approval.

The orchestrator prompt already says a PR review goes to the researcher, which owns
`github_get_pr_files`. That instruction was simply not followed, so the shape is rejected
here instead of asked for.
"""
import json

import pytest

from orchestrator import PlanSchema, TaskSpec, _validate_plan


def _plan(*tasks: TaskSpec, terminal: str | None = None) -> PlanSchema:
    return PlanSchema(tasks=list(tasks), terminal=terminal or tasks[-1].id,
                      reasoning="test plan")


RESEARCH = TaskSpec(id="t1", agent="researcher", description="Read the PR diff",
                    inputs={"repo": "o/r", "pr_number": 32}, depends_on=[])


def test_a_writer_given_only_references_to_fetch_is_rejected():
    """The exact terminal task from goal efb784fb."""
    review = TaskSpec(id="t2", agent="writer",
                      description="Write a review of the PR",
                      inputs={"pr_number": "{{t1.output.pr_number}}", "repo": "o/r"},
                      depends_on=["t1"])

    with pytest.raises(ValueError) as exc:
        _validate_plan(_plan(RESEARCH, review))
    assert "writer" in str(exc.value)
    assert "pr_number" in str(exc.value) or "repo" in str(exc.value)


def test_a_writer_given_the_content_itself_is_accepted():
    """The correct shape: the researcher fetched the diff, the writer turns it into prose."""
    review = TaskSpec(id="t2", agent="writer", description="Write a review of the PR",
                      inputs={"diff": "{{t1.output.code_context}}",
                              "findings": "{{t1.output.summary}}"},
                      depends_on=["t1"])

    _validate_plan(_plan(RESEARCH, review))


def test_a_writer_given_a_whole_output_object_is_accepted():
    """`{{t1.output}}` is the handoff the prompt recommends for integrator → writer, and
    it carries the real content."""
    review = TaskSpec(id="t2", agent="writer", description="Summarise the result",
                      inputs={"data": "{{t1.output}}"}, depends_on=["t1"])

    _validate_plan(_plan(RESEARCH, review))


def test_a_reference_alongside_real_content_is_fine():
    """Naming the repo is useful context for the prose. It is only a problem when it is
    ALL the writer was given."""
    review = TaskSpec(id="t2", agent="writer", description="Write up the findings",
                      inputs={"repo": "o/r", "findings": "{{t1.output.summary}}"},
                      depends_on=["t1"])

    _validate_plan(_plan(RESEARCH, review))


def test_a_writer_with_no_inputs_is_not_rejected_by_this_rule():
    """Empty inputs are a different problem with a different message. This guard is about
    being handed references and nothing else."""
    write = TaskSpec(id="t2", agent="writer", description="Write a poem about the sea",
                     inputs={}, depends_on=["t1"])

    _validate_plan(_plan(RESEARCH, write))


def test_an_agent_that_can_actually_fetch_may_be_given_references():
    """The integrator owns `github_get_pr`, so a PR number is a real instruction to it,
    not a request to imagine one."""
    act = TaskSpec(id="t2", agent="integrator", description="Merge the pull request",
                   inputs={"repo": "o/r", "pr_number": "{{t1.output.pr_number}}"},
                   depends_on=["t1"])

    _validate_plan(_plan(RESEARCH, act))


def test_the_researcher_may_be_given_references_too():
    single = TaskSpec(id="t1", agent="researcher", description="Read the PR diff",
                      inputs={"repo": "o/r", "pr_number": 32}, depends_on=[])

    _validate_plan(_plan(single))


# ── A rejected plan has to come back with the reason attached ───────────────────

def _goal(text="Review the pull request"):
    from state import GoalRow
    return GoalRow(id="g1", title=text[:80], goal_text=text, status="PLANNING",
                   output=None, error=None, plan_json=None, terminal_task_id=None,
                   trace_id="tr1", created_at=0, updated_at=0)


def _plan_response(plan: dict):
    import types
    call = types.SimpleNamespace(
        id="c0",
        function=types.SimpleNamespace(name="submit_plan", arguments=json.dumps(plan)),
    )
    message = types.SimpleNamespace(content="", tool_calls=[call])
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


REJECTED_PLAN = {
    "tasks": [
        {"id": "t1", "agent": "integrator", "description": "Open the pull request",
         "inputs": {"repo": "o/r"}, "depends_on": []},
        {"id": "t2", "agent": "writer", "description": "Write a review of the PR",
         "inputs": {"pr_number": "{{t1.output.pr_number}}", "repo": "o/r"},
         "depends_on": ["t1"]},
    ],
    "terminal": "t2", "reasoning": "review it",
}

ACCEPTED_PLAN = {
    "tasks": [
        {"id": "t1", "agent": "researcher", "description": "Read the PR diff",
         "inputs": {"repo": "o/r", "pr_number": 32}, "depends_on": []},
        {"id": "t2", "agent": "writer", "description": "Write a review of the PR",
         "inputs": {"diff": "{{t1.output.code_context}}"}, "depends_on": ["t1"]},
    ],
    "terminal": "t2", "reasoning": "read it, then review it",
}


def test_a_rejected_plan_is_retried_with_the_reason_attached(monkeypatch):
    """A guard the planner is never told about cannot teach it anything.

    The retry only appended the reason when the error text happened to contain the word
    "invalid", and no message from `_validate_plan` does — not the writer rule, not the
    pre-existing terminal-agent rule. So a rejected plan was regenerated blind from an
    unchanged prompt, and the model had no reason to produce anything different until all
    five attempts were gone.
    """
    import asyncio

    import orchestrator as orch

    seen = []

    async def fake(messages, **kwargs):
        seen.append([m["content"] for m in messages])
        return _plan_response(REJECTED_PLAN if len(seen) == 1 else ACCEPTED_PLAN)

    monkeypatch.setattr(orch, "acompletion", fake)
    result = asyncio.run(orch.plan(_goal()))

    assert [t.id for t in result.tasks] == ["t1", "t2"]
    assert result.tasks[0].agent == "researcher", "the accepted plan should be the one returned"
    assert len(seen) == 2, "the rejected plan should have been retried"
    assert any("no tool that can read anything" in m for m in seen[1]), (
        "the second attempt never saw why the first was rejected"
    )


def test_a_rate_limit_is_not_fed_back_as_plan_criticism(monkeypatch):
    """Only a complaint about the PLAN belongs in the plan conversation. Telling the model
    its plan was invalid because the provider was busy is a lie that teaches it nothing."""
    import asyncio

    import orchestrator as orch

    seen = []

    async def fake(messages, **kwargs):
        seen.append([m["content"] for m in messages])
        if len(seen) == 1:
            raise RuntimeError("litellm.RateLimitError: rate_limit_exceeded")
        return _plan_response(ACCEPTED_PLAN)

    monkeypatch.setattr(orch, "acompletion", fake)
    asyncio.run(orch.plan(_goal()))

    assert len(seen) == 2
    assert not any("previous plan was invalid" in m for m in seen[1]), (
        "a rate limit was reported to the model as a defect in its plan"
    )


# ── An integrator told to raise a PR must be given the code ─────────────────────

def _t(id, agent, desc, inputs, deps=()):
    return TaskSpec(id=id, agent=agent, description=desc, inputs=inputs,
                    depends_on=list(deps))


#: The plan from goal b78892d5, which produced PR #35.
PR_WITHOUT_CODE = [
    _t("t1", "researcher", "Research the auth.py file", {"file_path": "auth.py"}),
    _t("t2", "coder", "Implement the TODO in Rust",
       {"code_context": "{{t1.output.code_context}}"}, ["t1"]),
    _t("t3", "writer", "Write a review of the Rust codebase",
       {"data": "{{t2.output}}"}, ["t2"]),
    _t("t4", "integrator", "Raise a PR with the migrated codebase in Rust",
       {"file_path": "auth.rs", "pr_title": "Migrated to Rust",
        "pr_body": "{{t3.output.text}}", "repo": "o/r"}, ["t3"]),
]


def test_an_integrator_raising_a_pr_without_the_code_is_rejected():
    """Live failure, goal b78892d5 → PR #35.

    The integrator was handed a filename, a title and a body, and no code. It had nothing
    to commit, so it committed the literal string "TODO: replace with actual file
    content". The coder's Rust — which existed, and was fine — was never referenced by the
    task that does the committing.
    """
    with pytest.raises(ValueError) as exc:
        _validate_plan(PlanSchema(tasks=PR_WITHOUT_CODE, terminal="t4", reasoning="r"))
    assert "t4" in str(exc.value)
    assert "code" in str(exc.value).lower()


def test_the_same_plan_with_the_code_handed_over_is_accepted():
    """The corrected shape, and the one the working mergesort plans always had."""
    fixed = list(PR_WITHOUT_CODE)
    fixed[-1] = _t("t4", "integrator", "Raise a PR with the migrated codebase in Rust",
                   {"file_path": "{{t2.output.path}}", "fixed_code": "{{t2.output.code}}",
                    "pr_title": "Migrated to Rust", "repo": "o/r"}, ["t2", "t3"])
    _validate_plan(PlanSchema(tasks=fixed, terminal="t4", reasoning="r"))


def test_a_whole_output_handoff_from_the_coder_counts():
    """`{{t2.output}}` carries the code along with everything else."""
    fixed = list(PR_WITHOUT_CODE)
    fixed[-1] = _t("t4", "integrator", "Open a pull request",
                   {"work": "{{t2.output}}", "repo": "o/r"}, ["t2"])
    _validate_plan(PlanSchema(tasks=fixed, terminal="t4", reasoning="r"))


def test_an_integrator_doing_something_other_than_a_pr_is_not_policed():
    """Merging, commenting and labelling do not commit files, so they need no code."""
    tasks = [
        _t("t1", "coder", "Write the fix", {"x": 1}),
        _t("t2", "integrator", "Merge pull request 7",
           {"repo": "o/r", "pr_number": 7}, ["t1"]),
        _t("t3", "writer", "Report", {"d": "{{t2.output}}"}, ["t2"]),
    ]
    _validate_plan(PlanSchema(tasks=tasks, terminal="t3", reasoning="r"))


def test_a_pr_plan_with_no_coder_at_all_is_not_policed():
    """A docs PR is written by the writer, and its text is the content."""
    tasks = [
        _t("t1", "writer", "Draft the CONTRIBUTING guide", {"topic": "contributing"}),
        _t("t2", "integrator", "Raise a PR adding CONTRIBUTING.md",
           {"repo": "o/r", "content": "{{t1.output.text}}"}, ["t1"]),
        _t("t3", "writer", "Report what was opened", {"d": "{{t2.output}}"}, ["t2"]),
    ]
    _validate_plan(PlanSchema(tasks=tasks, terminal="t3", reasoning="r"))


def test_referencing_a_coder_without_taking_its_code_is_still_rejected():
    """Live failure, goal d38a64b8 → PR #36, on the build carrying the first version of
    this rule. The integrator's only template was:

        "file_path": "{{d38a64b8_t4.output.file_path}}"

    t4 is a coder, so "does it reference a coder task" was satisfied — and the integrator
    still had no code, and still committed "TODO: replace with actual file content".
    Pointing at a coder is not the same as being handed what the coder wrote.
    """
    tasks = [
        _t("t1", "coder", "Write the Rust", {"x": 1}),
        _t("t2", "integrator", "Raise a PR with the Rust",
           {"repo": "o/r", "file_path": "{{t1.output.file_path}}"}, ["t1"]),
        _t("t3", "writer", "Report", {"d": "{{t2.output}}"}, ["t2"]),
    ]
    with pytest.raises(ValueError) as exc:
        _validate_plan(PlanSchema(tasks=tasks, terminal="t3", reasoning="r"))
    assert "code" in str(exc.value).lower()


def test_taking_the_path_alongside_the_code_is_fine():
    """`file_path` is useful — it just cannot be the only thing taken from the coder."""
    tasks = [
        _t("t1", "coder", "Write the Rust", {"x": 1}),
        _t("t2", "integrator", "Raise a PR with the Rust",
           {"repo": "o/r", "file_path": "{{t1.output.path}}",
            "fixed_code": "{{t1.output.code}}"}, ["t1"]),
        _t("t3", "writer", "Report", {"d": "{{t2.output}}"}, ["t2"]),
    ]
    _validate_plan(PlanSchema(tasks=tasks, terminal="t3", reasoning="r"))
