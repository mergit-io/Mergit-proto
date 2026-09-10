"""A value that was never filled in, and the check that refuses to publish one.

`{{t3.output.pr_number}}` is an interpolation template that outlived its task; `#<pr_number>`
is the model writing its own blank. Either one published to a channel, a ticket or a page is
a message that says nothing and cannot be un-sent.

The check began life inside `github_ops` for issue comments. It moved here when Slack, Linear
and Notion arrived, because a plan can — and on run `0e9fefe4` did — hand the same unresolved
template to a Linear description: task t3's inputs contained
`"issue_description": "Bug fix PR: {{0e9fefe4_t3.output.url}}"`, a self-reference that can
never resolve, because t3 is the task being planned.

The angle-bracket form requires snake_case with an underscore, which is what a blank looks
like and what ordinary prose does not: `Vec<String>` and `<div>` have no underscore, and
<https://example.com> is not an identifier. `<number>` slips through as the price of that —
a wrong refusal costs a real message.

Matching is case-insensitive. It was lowercase-only, and on 2026-08-22 an integrator posted
`Fixed in PR #<PR_NUMBER>` on issue #25 of the sandbox repo: the same blank this guard exists
to stop, written in the casing it did not cover.
"""
import re

PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}|<[a-z][a-z0-9]*_[a-z0-9_]*>", re.I)


def unfilled_placeholders(body: str) -> list[str]:
    """Every unresolved blank in `body`. Empty means it is safe to publish."""
    return PLACEHOLDER.findall(body or "")


def refuse_if_unfilled(body: str, what: str) -> dict | None:
    """The tool-shaped refusal for a body with blanks in it, or None.

    Returns the error rather than raising it, because every tool here reports failure as
    `{"ok": False}` and an exception would be swallowed by their `except Exception` blocks
    into a less specific message.
    """
    blanks = unfilled_placeholders(body)
    if not blanks:
        return None
    return {"ok": False, "error": (
        f"refusing to publish {what}: it still contains unfilled placeholders "
        f"{blanks[:3]}. Substitute the real values — a template that reached this point "
        f"will never resolve on its own.")}
