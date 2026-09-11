"""A plan's `{{t1.output.field}}` references, and where they stopped being replaced.

Run `8738177b` planned a writer task whose inputs were

    {"data": {"root_cause": "{{8738177b_t2.output.summary}}",
              "pr_url":     "{{8738177b_t3.output.url}}",
              "linear_url": "{{8738177b_t4.output.url}}"}}

and the writer produced prose reading "The root cause of the bug was related to
{{8738177b_t2.output.summary}}." — the template, verbatim, in the finished text. The next
task filed that text as a Notion incident note, and only the publish-time placeholder guard
stopped it reaching a page a human would read.

`resolve_inputs` replaced nothing there, because it walked only the top level of the inputs
dict: any value that was not a string was returned untouched, and `data` was a dict. Every
template inside it survived, silently — no warning, no error, no resolution.

Templates nested in a dict or a list are ordinary in an LLM-authored plan. The planner is
shown `{"data": "{{t1.output}}"}` as the writer's example and it nests one level deeper
about as often as not, which is a thing to support rather than a thing to forbid.
"""
from interpolation import resolve_inputs

OUTPUTS = {
    "t1": {"summary": "largest() returned 0 for an all-negative list",
           "code_context": "biggest = 0"},
    "t3": {"url": "https://github.com/o/r/pull/59", "action": "create_pr"},
    "t4": {"url": "https://linear.app/x/issue/ABH-15"},
}


def test_a_template_at_the_top_level_resolves():
    assert resolve_inputs({"root_cause": "{{t1.output.summary}}"}, OUTPUTS) == {
        "root_cause": "largest() returned 0 for an all-negative list"}


def test_a_template_nested_in_a_dict_resolves():
    """The exact shape run 8738177b planned, and the exact shape that survived unreplaced."""
    resolved = resolve_inputs(
        {"data": {"root_cause": "{{t1.output.summary}}",
                  "pr_url": "{{t3.output.url}}",
                  "linear_url": "{{t4.output.url}}"}},
        OUTPUTS)
    assert resolved == {"data": {
        "root_cause": "largest() returned 0 for an all-negative list",
        "pr_url": "https://github.com/o/r/pull/59",
        "linear_url": "https://linear.app/x/issue/ABH-15"}}


def test_a_template_nested_in_a_list_resolves():
    assert resolve_inputs({"links": ["{{t3.output.url}}", "{{t4.output.url}}"]}, OUTPUTS) == {
        "links": ["https://github.com/o/r/pull/59", "https://linear.app/x/issue/ABH-15"]}


def test_templates_resolve_however_deep_they_are():
    resolved = resolve_inputs(
        {"report": {"sections": [{"title": "Root cause",
                                  "body": "caused by {{t1.output.summary}}"}]}},
        OUTPUTS)
    assert resolved["report"]["sections"][0]["body"] == (
        "caused by largest() returned 0 for an all-negative list")


def test_a_whole_output_substituted_into_a_nested_string_is_json():
    """Inside a sentence an object has to be rendered, not returned — the same rule the
    top level already followed."""
    resolved = resolve_inputs({"data": {"note": "context: {{t3.output}}"}}, OUTPUTS)
    assert '"url": "https://github.com/o/r/pull/59"' in resolved["data"]["note"]


def test_a_whole_output_as_the_entire_nested_value_stays_an_object():
    resolved = resolve_inputs({"data": {"upstream": "{{t3.output}}"}}, OUTPUTS)
    assert resolved["data"]["upstream"] == OUTPUTS["t3"]


def test_values_that_are_not_templates_are_left_exactly_as_they_were():
    inputs = {"repo": "o/r", "pr_number": 59, "draft": False, "labels": ["bug", "fix"],
              "nested": {"keep": None, "n": 1.5}}
    assert resolve_inputs(inputs, OUTPUTS) == inputs


def test_a_missing_field_still_falls_back_to_the_whole_output_when_nested():
    """`{{t2.output.summary}}` in run 8738177b named a field the coder's schema does not
    have. Falling back beats failing the goal, and it must behave the same nested as it
    does at the top level."""
    resolved = resolve_inputs({"data": {"x": "{{t3.output.nope}}"}}, OUTPUTS)
    assert resolved["data"]["x"] == OUTPUTS["t3"]


def test_an_unknown_task_substitutes_empty_when_nested():
    assert resolve_inputs({"data": {"x": "{{t99.output.url}}"}}, OUTPUTS) == {"data": {"x": ""}}


def test_no_template_survives_a_resolution_that_had_the_outputs_for_it():
    """The property that failed in production, stated directly: after resolving, nothing
    anywhere in the inputs still looks like a template."""
    import json

    resolved = resolve_inputs(
        {"data": {"root_cause": "{{t1.output.summary}}", "pr_url": "{{t3.output.url}}"},
         "links": ["{{t4.output.url}}"],
         "top": "{{t1.output.summary}}"},
        OUTPUTS)
    assert "{{" not in json.dumps(resolved)
