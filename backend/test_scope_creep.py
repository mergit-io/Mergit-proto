"""Work nobody asked for, riding along inside a bug fix.

Two live failures that no existing guard could see, because nothing about either was
false. Grounding asks whether the description is true of the diff; these ask the other
half — whether the diff contains anything the description does not account for.

* PR #52 added module-level `assert` statements and a `print` to `calc.py`. Every future
  importer of that module runs them. The pull request was entirely truthful.
* PR #53's Root Cause section reads "No code-level issue was found in the `total()`
  function" — and it changed the file anyway. The agent had already reached the right
  answer and shipped a pull request instead of reporting it.

The rule is not "never change anything extra". It is **say so**. A change disclosed in the
body passes; the same change slipped in silently does not.
"""
from tools.scope_creep import (added_import_time_effects, added_undisclosed_guards,
                               declares_no_defect, unrequested_changes)

LIBRARY = '''"""Tiny calculator."""


def total(numbers):
    """Sum a sequence."""
    return sum(numbers)


def largest(numbers):
    """Return the largest number in a sequence."""
    biggest = 0
    for n in numbers:
        if n > biggest:
            biggest = n
    return biggest
'''

# PR #52, verbatim in shape: asserts and a print at column zero.
WITH_ASSERTS = LIBRARY.replace(
    "def largest(numbers):",
    'assert total([1, 2, 3]) == 6\nprint("All tests passed.")\n\n\ndef largest(numbers):')

# PR #53: the same intent, kept behind the __main__ guard where it harms nobody.
WITH_MAIN_GUARD = LIBRARY.replace(
    "def largest(numbers):",
    'if __name__ == "__main__":\n    print(total([1, 2, 3]))\n\n\ndef largest(numbers):')

# The fix that was asked for.
FIXED = LIBRARY.replace(
    "    biggest = 0\n    for n in numbers:",
    "    biggest = numbers[0]\n    for n in numbers[1:]:")

# The fix, with an empty-input guard nobody asked for riding along.
FIXED_PLUS_GUARD = LIBRARY.replace(
    "    biggest = 0\n    for n in numbers:",
    "    if not numbers:\n        return 0\n    biggest = numbers[0]\n    for n in numbers[1:]:")


# ── Statements that run on import ────────────────────────────────────────────────

def test_asserts_added_at_module_level_are_refused():
    added = added_import_time_effects(LIBRARY, WITH_ASSERTS, "calc.py")
    assert any("assert total([1, 2, 3]) == 6" in a for a in added)
    assert any("print(" in a for a in added)


def test_the_main_guard_is_where_that_belongs():
    """PR #53 put its prints behind `if __name__ == "__main__"`. Nothing runs on import,
    so nothing here objects."""
    assert added_import_time_effects(LIBRARY, WITH_MAIN_GUARD, "calc.py") == []


def test_definitions_imports_and_constants_are_how_a_module_is_meant_to_look():
    after = LIBRARY.replace('"""Tiny calculator."""',
                            '"""Tiny calculator."""\nimport math\n\nPRECISION = 4')
    assert added_import_time_effects(LIBRARY, after, "calc.py") == []


def test_a_file_that_does_not_parse_is_left_alone():
    """Refusing a change we cannot analyse would block real work for the sake of a rule we
    could not actually apply."""
    assert added_import_time_effects(LIBRARY, "def broken(:", "calc.py") == []
    assert added_import_time_effects(LIBRARY, WITH_ASSERTS, "calc.rs") == []


# ── Guards that arrive unannounced ───────────────────────────────────────────────

def test_an_undisclosed_empty_guard_is_refused():
    problems = added_undisclosed_guards(
        LIBRARY, FIXED_PLUS_GUARD, "calc.py",
        "## Problem\n`largest` returned 0 for an all-negative list.")
    assert len(problems) == 1
    assert "empty" in problems[0]
    assert "largest" in problems[0]


def test_the_same_guard_is_fine_once_the_body_says_so():
    """PR #48 added exactly this guard and wrote "The function now also checks for empty
    input and returns 0 in that case." Disclosed is the whole rule."""
    assert added_undisclosed_guards(
        LIBRARY, FIXED_PLUS_GUARD, "calc.py",
        "## Fix\nStarts from the first element. The function now also checks for empty "
        "input and returns 0 in that case.") == []


def test_the_fix_on_its_own_passes():
    assert added_undisclosed_guards(LIBRARY, FIXED, "calc.py", "fixes largest") == []


def test_a_new_function_is_the_change_not_a_passenger_on_one():
    after = LIBRARY + '\n\ndef smallest(numbers):\n    if not numbers:\n        return 0\n    return min(numbers)\n'
    assert added_undisclosed_guards(LIBRARY, after, "calc.py", "adds smallest()") == []


def test_a_condition_we_cannot_name_is_not_refused():
    """Refusing a change whose reason we cannot describe produces an error nobody can act
    on, so an unrecognised guard is left alone."""
    after = LIBRARY.replace(
        "    biggest = 0",
        "    if numbers[0] > 99999:\n        return -1\n    biggest = 0")
    assert added_undisclosed_guards(LIBRARY, after, "calc.py", "fixes largest") == []


# ── Saying there is no defect, then changing the code ────────────────────────────

def test_no_defect_in_root_cause_is_refused():
    body = ("## Problem\nThe total() function was reviewed.\n\n"
            "## Root Cause\nNo code-level issue was found in the `total()` function.\n\n"
            "## Fix\nAdded test cases.")
    assert declares_no_defect(body) == "No code-level issue was found"


def test_noting_another_function_is_fine_does_not_refuse_the_fix():
    """A pull request that fixes one thing while observing another is fine is ordinary.
    Only the Root Cause section is read, which is why this passes."""
    body = ("## Problem\n`largest` returns 0 for negative lists. There are no issues in "
            "`total`.\n\n## Root Cause\n`biggest` is initialised to 0.\n\n## Fix\nStart "
            "from the first element.")
    assert declares_no_defect(body) == ""


def test_a_body_with_no_root_cause_section_is_not_second_guessed():
    assert declares_no_defect("just a quick change") == ""


# ── The whole check ──────────────────────────────────────────────────────────────

def test_the_two_real_failures_are_both_refused():
    pr52 = unrequested_changes([("calc.py", LIBRARY, WITH_ASSERTS)], "## Fix\nAdded tests.")
    assert any("runs whenever the module is imported" in p for p in pr52)

    pr53_body = ("## Root Cause\nNo code-level issue was found in the `total()` function.\n\n"
                 "## Fix\nAdded test cases.")
    pr53 = unrequested_changes([("calc.py", LIBRARY, WITH_MAIN_GUARD)], pr53_body)
    assert any("states there is no defect" in p for p in pr53)


def test_the_fix_that_was_asked_for_ships():
    body = ("## Problem\n`largest` returned 0 for an all-negative list.\n\n"
            "## Root Cause\n`biggest` was initialised to 0.\n\n"
            "## Fix\nStart from the first element.")
    assert unrequested_changes([("calc.py", LIBRARY, FIXED)], body) == []
