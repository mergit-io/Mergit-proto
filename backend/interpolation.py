import re
from typing import Any

TEMPLATE_RE = re.compile(r"\{\{(\w+)\.output\.(\w+)\}\}")


def resolve_inputs(inputs: dict, task_outputs: dict[str, dict]) -> dict:
    """Replace {{task_id.output.field}} templates with actual values from completed tasks."""

    def resolve_value(v: Any) -> Any:
        if not isinstance(v, str):
            return v
        full_match = TEMPLATE_RE.fullmatch(v)
        if full_match:
            task_id, field = full_match.groups()
            return task_outputs[task_id][field]
        def replace(m: re.Match) -> str:
            task_id, field = m.groups()
            return str(task_outputs[task_id][field])
        return TEMPLATE_RE.sub(replace, v)

    return {k: resolve_value(v) for k, v in inputs.items()}
