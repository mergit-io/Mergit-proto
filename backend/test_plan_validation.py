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
