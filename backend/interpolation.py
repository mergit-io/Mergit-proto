import re
from typing import Any

# Matches {{task_id.output.path}} where path can include array indices: field[0], field[0].subfield
TEMPLATE_RE = re.compile(r"\{\{(\w+)\.output\.([\w\[\]\.0-9]+)\}\}")

_INDEX_RE = re.compile(r"(\[\d+\])")


def _resolve_path(obj: Any, path: str) -> Any:
    """Traverse a nested object using a dotted path that may include array indices like field[0].sub."""
    for part in path.split("."):
        segments = _INDEX_RE.split(part)
        for seg in segments:
            if not seg:
                continue
            if seg.startswith("[") and seg.endswith("]"):
                obj = obj[int(seg[1:-1])]
            else:
                obj = obj[seg]
    return obj


def resolve_inputs(inputs: dict, task_outputs: dict[str, dict]) -> dict:
    """Replace {{task_id.output.field}} templates with actual values from completed tasks."""

    def resolve_value(v: Any) -> Any:
        if not isinstance(v, str):
            return v
        full_match = TEMPLATE_RE.fullmatch(v)
        if full_match:
            task_id, path = full_match.groups()
            return _resolve_path(task_outputs[task_id], path)

        def replace(m: re.Match) -> str:
            task_id, path = m.groups()
            return str(_resolve_path(task_outputs[task_id], path))

        return TEMPLATE_RE.sub(replace, v)

    return {k: resolve_value(v) for k, v in inputs.items()}
