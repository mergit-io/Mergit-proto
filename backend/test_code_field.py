"""The `code` field has to contain code, and `path` has to be a path.

Live failure, goal 2c7b400b → PR #38. The coder submitted:

    {"code": "No Rust code was provided to execute",
     "path": "No file path available",
     "output": "The code was not executed because it is written in Rust...",
     "success": True}

An excuse in the field that is supposed to hold source, a sentence in the field that is
supposed to hold a filename, and `success: True` over the top. Every guard passed it and
each was right to:

* `_self_reported_failure` — `success` is a real boolean and no required field is empty.
* `_wrong_language_for_task` — the text shows no marker of any language, and silence is
  deliberately treated as "no opinion" so that stubs and constants files survive.
* `_unrunnable_execution_claim` — `output` really does say the code was not executed.

Two tasks later a second coder, handed that as its starting point, produced
`import os / print("Hello World")` at `hello.py` — a Python hello-world answering a Rust
migration — and the integrator committed it. PR #38 is downstream of this submission, not
of a defect in the integrator.

The rule stays syntactic. Not "is this relevant to the goal", which is a judgement, but
"is this a program and is that a filename", which is not.
"""
import pytest

from agent_registry import AGENT_REGISTRY
from agent_runner import _not_actually_code, _submission_problem

CODER_REQUIRED = AGENT_REGISTRY["coder"]["output_schema"]["required"]


def _result(code, path="a.py"):
    return {"code": code, "path": path, "output": "ok", "success": True}


# ── prose where the source should be ────────────────────────────────────────────

def test_the_exact_submission_behind_pr_38_is_rejected():
    result = {"code": "No Rust code was provided to execute",
              "path": "No file path available", "output": "not executed", "success": True}
    problem = _not_actually_code(result)
    assert problem is not None


@pytest.mark.parametrize("excuse", [
    "No Rust code was provided to execute",
    "The code could not be generated",
    "Unable to produce an implementation",
])
def test_an_excuse_is_not_code(excuse):
    assert _not_actually_code(_result(excuse)) is not None


@pytest.mark.parametrize("code", [
    "print('Hello World')",
    "import os\nprint(os.getcwd())",
    "def add(a, b):\n    return a + b\n",
    "fn main() { let mut x = 1; }",
    "X = 30",
    "users = {}",
])
def test_real_code_passes(code):
    assert _not_actually_code(_result(code)) is None


def test_a_single_expression_with_no_keywords_still_passes():
    """Punctuation is enough evidence of a program. This must not become a language test —
    that is a different guard with a different failure mode."""
    assert _not_actually_code(_result("total = sum(values)")) is None


# ── a sentence where the filename should be ─────────────────────────────────────

@pytest.mark.parametrize("bad_path", [
    "No file path available",
    "the file could not be determined",
    "N/A - no file",
])
def test_a_sentence_is_not_a_path(bad_path):
    assert _not_actually_code(_result("print(1)", bad_path)) is not None


@pytest.mark.parametrize("good_path", [
    "auth.rs", "src/main.rs", "a.py", "tests/test_stats.py", "Makefile", ".env.example",
])
def test_real_paths_pass(good_path):
    assert _not_actually_code(_result("print(1)", good_path)) is None


# ── wired into the submission check ─────────────────────────────────────────────

def test_the_rejection_reaches_the_agent():
    result = {"code": "No Rust code was provided to execute",
              "path": "No file path available", "output": "not executed", "success": True}
    problem = _submission_problem(result, CODER_REQUIRED, "Implement the TODOs in Rust")
    assert problem is not None
    assert "code" in problem.lower()


def test_an_agent_with_no_code_field_is_untouched():
    """The researcher and writer submit prose, and prose is what they are for."""
    required = AGENT_REGISTRY["writer"]["output_schema"]["required"]
    assert _submission_problem({"text": "A report.", "title": "T"}, required, "Write it") is None
