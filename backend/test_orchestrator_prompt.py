"""Guards on the orchestrator's system prompt.

A live run on 2026-08-12 showed the orchestrator silently dropping every constraint the
user stated. The goal was:

    "Explain what SQLite WAL journal mode is and why a server application would enable it.
     Keep it to 4 short bullet points. Use your own knowledge, no web search needed."

and the plan it produced was:

    researcher: "Explain SQLite WAL journal mode"
    writer:     "Write a text explaining SQLite WAL journal mode and its benefits"

The bullet-point limit, the "why a server would enable it" angle and the no-search
instruction never reached an agent, so the output could not possibly satisfy the request.
The agents behaved correctly; they were briefed wrongly.

These tests do not assert model behaviour — they assert that the instruction exists, so the
guidance cannot be dropped again without a test failing.
"""
import orchestrator


def test_prompt_requires_preserving_user_constraints():
    prompt = orchestrator.SYSTEM_PROMPT.lower()
    assert "constraint" in prompt, (
        "the orchestrator is never told to carry the user's constraints into the plan"
    )


def test_prompt_names_the_constraint_kinds_that_get_lost():
    prompt = orchestrator.SYSTEM_PROMPT.lower()
    for kind in ["format", "length", "exclusion"]:
        assert kind in prompt, f"the prompt does not mention preserving {kind} constraints"


def test_prompt_requires_constraints_on_the_terminal_task():
    """The terminal task produces the answer the user reads — that is where a format
    constraint has to land."""
    prompt = orchestrator.SYSTEM_PROMPT.lower()
    assert "terminal" in prompt and "constraint" in prompt


def test_constraint_rule_is_in_the_numbered_rules():
    """Guidance buried outside the rules list gets ignored by smaller models."""
    lines = orchestrator.SYSTEM_PROMPT.splitlines()
    rules_start = next(i for i, line in enumerate(lines) if line.strip() == "Rules:")
    rules_block = "\n".join(lines[rules_start:]).lower()
    assert "constraint" in rules_block
