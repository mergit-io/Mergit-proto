"""Guards on what `submit_result` is allowed to claim.

Presence of the required keys was the only check, and that is how PR #30 on the sandbox
came to exist. A goal whose text contained a `/tree/main` URL made the orchestrator read
the BRANCH as a directory and write `file_path: "main/mergesort.py"` into task 1. The
researcher correctly reported the file was missing. The coder then submitted:

    {"code": "", "path": "main/mergesort.py",
     "output": "404 {\\"message\\": \\"Not Found\\", ...}", "success": False}

Every required key was present, so the task was recorded DONE. The integrator
interpolated that empty `code` into `files[].content` and opened a pull request whose one
commit added an empty file. The agent said it failed; the pipeline said it succeeded.

These tests pin the contradiction check itself, which is a pure function, plus the fact
that the real coder schema is what makes it fire.
"""
import pytest

from agent_registry import AGENT_REGISTRY
from agent_runner import _self_reported_failure

CODER_REQUIRED = AGENT_REGISTRY["coder"]["output_schema"]["required"]


def test_the_exact_payload_that_shipped_an_empty_pull_request_is_rejected():
    result = {
        "code": "",
        "path": "main/mergesort.py",
        "output": '404 {"message": "Not Found", "status": "404"}',
        "success": False,
    }
    assert _self_reported_failure(result, CODER_REQUIRED) is not None


def test_success_false_is_rejected_even_when_every_field_is_filled_in():
    """An agent that says it failed has failed, however much prose it attaches."""
    result = {"code": "def f(): pass", "path": "a.py", "output": "boom", "success": False}
    assert "success=False" in _self_reported_failure(result, CODER_REQUIRED)


def test_an_empty_required_string_is_rejected_and_named():
    result = {"code": "   \n ", "path": "a.py", "output": "ok", "success": True}
    problem = _self_reported_failure(result, CODER_REQUIRED)
    assert problem is not None and "code" in problem


def test_a_real_result_passes():
    result = {"code": "def f():\n    return 1\n", "path": "calc.py",
              "output": "1", "success": True}
    assert _self_reported_failure(result, CODER_REQUIRED) is None


def test_only_required_fields_have_to_be_non_empty():
    """`code_context` is optional on the researcher — a research task that found no code
    is still a legitimate result, so an empty optional field must not be rejected."""
    required = AGENT_REGISTRY["researcher"]["output_schema"]["required"]
    assert "code_context" not in required
    result = {"summary": "no code found", "key_points": ["none"], "sources": ["url"],
              "code_context": ""}
    assert _self_reported_failure(result, required) is None


def test_a_falsy_value_that_is_not_a_string_is_left_alone():
    """Only strings are checked for emptiness. An integer 0 or an empty list may be the
    honest answer, and this guard must not invent a failure out of one."""
    assert _self_reported_failure({"a": 0, "b": [], "c": "x"}, ["a", "b", "c"]) is None


def test_success_is_the_only_field_read_for_its_truth_value():
    """A field that merely happens to be False-ish must not be mistaken for a failure
    flag — only the literal `success` key means what this guard thinks it means."""
    assert _self_reported_failure({"ok": False, "text": "hi"}, ["text"]) is None


@pytest.mark.parametrize("agent", ["researcher", "writer", "coder", "integrator"])
def test_every_agent_still_accepts_a_well_formed_result(agent):
    """The guard must not make any agent unable to finish. Build the minimal valid result
    from each schema and confirm it passes."""
    required = AGENT_REGISTRY[agent]["output_schema"]["required"]
    result = {k: f"value for {k}" for k in required}
    if "success" in result:
        result["success"] = True
    assert _self_reported_failure(result, required) is None
