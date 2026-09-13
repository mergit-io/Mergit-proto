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
import re

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


def test_the_decision_guide_only_recommends_agents_that_exist():
    """Rule 7 says "do not invent agent names" — the prompt must not break its own rule.

    The decision guide used to end a line with "send a Slack message" -> notifier is fine
    as terminal.  There is no `notifier` in AGENT_REGISTRY and there has been no Slack tool
    since `slack_notify` was deleted, so the one worked example of a non-GitHub goal pointed
    the planner at an agent that cannot be scheduled.  `economy.ROLES` still mints a passport
    for `notifier`, which is why the name looks real from the ledger side.
    """
    from agent_registry import AGENT_REGISTRY

    real = set(AGENT_REGISTRY)
    prompt = orchestrator.SYSTEM_PROMPT

    # Every "<name> is fine as terminal" / "-> <name> alone" recommendation names a real agent.
    for match in re.finditer(r"([a-z_]+) (?:is fine as terminal|alone)", prompt):
        assert match.group(1) in real, (
            f"the decision guide recommends {match.group(1)!r}, which is not in AGENT_REGISTRY "
            f"({sorted(real)})"
        )


def test_the_prompt_says_a_tree_url_segment_is_a_branch_not_a_directory():
    """The `main/mergesort.py` failure.

    Goal text: "https://github.com/OfficialAbhinavSingh/mergit-e2e-sandbox/tree/main this
    repo has a mergesort file check if the code is correct if not fix it raise a pr".
    The orchestrator read `main` — the branch — as a folder and wrote
    `file_path: "main/mergesort.py"` into task 1. The researcher reported "The directory
    main was not found in the repository", and every agent after it produced nothing.
    """
    prompt = orchestrator.SYSTEM_PROMPT.lower()
    assert "/tree/" in prompt and "/blob/" in prompt, (
        "the prompt never tells the planner how to read a GitHub tree/blob URL"
    )
    assert "branch" in prompt and "not a" in prompt, (
        "the prompt does not say the segment after /tree/ is a branch rather than a directory"
    )


def test_the_prompt_forbids_inventing_a_file_path():
    """A guessed path is worse than no path: with none, the researcher enumerates the
    repo; with a wrong one, every downstream agent aims at a file that does not exist."""
    prompt = orchestrator.SYSTEM_PROMPT.lower()
    assert "never invent a file path" in prompt


def test_the_prompt_never_promises_a_tool_that_is_not_registered():
    """A prompt naming a deleted tool teaches the model to call something that 404s."""
    from tools import TOOL_REGISTRY

    prompt = orchestrator.SYSTEM_PROMPT.lower()
    for gone in ["slack_notify", "notifier"]:
        assert gone not in prompt, (
            f"the orchestrator prompt still mentions {gone!r}, which does not exist "
            f"(registered tools: {sorted(TOOL_REGISTRY)})"
        )
