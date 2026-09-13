"""The pull request that was correct and described the wrong bug.

Run `0e067775` read a Slack thread reporting that `largest([-5, -2, -9])` returned 0
instead of -2, wrote the right fix, and opened PR #47 whose body began:

    ## Problem
    The `average` function did not handle empty lists properly

`average` was already correct and the diff never touched it. Every tool returned
`ok: true`, every guard passed, and the Linear ticket moved to In Review carrying the same
wrong story. Nothing was fabricated — no URL was invented, no failure was hidden — so none
of the fabrication guards could see it.

These tests pin the check that does. It is deliberately narrow, because its false
positives cost real pull requests: only backticked tokens, only the token nearest before a
claim verb, and a symbol counts as supported when a changed line merely sits inside it.
"""
from tools.grounding import claimed_tokens, normalise, touched, unsupported_claims

BEFORE = '''"""Tiny calculator."""


def average(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def total(numbers):
    return sum(numbers)


def largest(numbers):
    biggest = 0
    for n in numbers:
        if n > biggest:
            biggest = n
    return biggest
'''

# The real fix from run 0e067775: start from the first element instead of zero.
AFTER = BEFORE.replace(
    "    biggest = 0\n    for n in numbers:",
    "    biggest = numbers[0]\n    for n in numbers[1:]:")

FILES = [("calc.py", BEFORE, AFTER)]


def test_the_actual_pr_47_body_is_refused():
    problems = unsupported_claims(
        "## Problem\n"
        "The `average` function did not handle empty lists properly.\n\n"
        "## Fix\n"
        "- `average(numbers)` now returns `0.0` for empty input.\n"
        "- `largest(numbers)` now iterates safely.\n",
        FILES)
    assert len(problems) == 1
    assert "`average`" in problems[0]


def test_an_honest_body_passes():
    """The fix is inside `largest`; its `def` line never changes. A check that demanded
    otherwise would reject every real bug fix."""
    assert unsupported_claims(
        "## Problem\n`largest` returned 0 for an all-negative list.\n\n"
        "## Fix\n`largest` no longer starts from 0 — it starts from the first element.\n",
        FILES) == []


def test_context_beside_a_claim_is_not_itself_a_claim():
    """In "unlike `total`, `largest` now starts from the first element" the assertion is
    about `largest`. Flagging `total` would be wrong."""
    assert unsupported_claims(
        "Unlike `total`, `largest` now starts from the first element.", FILES) == []


def test_a_claim_about_an_untouched_file_is_refused():
    problems = unsupported_claims(
        "## Fix\nAlso corrected `stats.py` so the median is right.", FILES)
    assert len(problems) == 1
    assert "`stats.py`" in problems[0]
    assert "does not change" in problems[0]


def test_background_prose_may_mention_untouched_code():
    """A body is allowed to explain context. Only sentences that assert a change are
    checked — otherwise every PR that says why something is out of scope gets refused."""
    assert unsupported_claims(
        "`average` and `total` are unrelated to this bug and were left alone.\n"
        "`largest` now starts from the first element.", FILES) == []


def test_literals_and_types_are_never_treated_as_claims():
    assert normalise("`0.0`") is None or normalise("0.0") is None
    assert normalise("True") is None
    assert normalise("int") is None
    assert normalise("average(numbers)") == ("symbol", "average")
    assert normalise("calc.py") == ("file", "calc.py")


def test_a_changed_line_inside_a_function_marks_that_function_touched():
    symbols, words = touched(BEFORE, AFTER)
    assert "largest" in symbols
    assert "average" not in symbols
    assert "numbers" in words


def test_a_body_with_no_backticks_is_not_second_guessed():
    """Prose that names nothing in code cannot be checked against a diff, so it is left
    alone rather than guessed at."""
    assert unsupported_claims("Fixes the reporting bug from the Slack thread.", FILES) == []


def test_nothing_is_reported_when_no_file_could_be_read():
    """A new file has no before-content. The check reports only what it is certain of."""
    assert unsupported_claims("`average` now handles empty input.", []) == []


def test_claim_verbs_are_what_makes_a_sentence_a_claim():
    assert claimed_tokens("`average` now returns 0.0") == ["average"]
    assert claimed_tokens("`average` is a helper") == []
