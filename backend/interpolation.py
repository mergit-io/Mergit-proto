import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Matches {{task_id.output}} (whole output) or {{task_id.output.path}} (field path)
TEMPLATE_RE = re.compile(r"\{\{(\w+)\.output(?:\.([\w\[\]\.0-9]+))?\}\}")

_INDEX_RE = re.compile(r"(\[\d+\])")


class _PathMiss(Exception):
    """Raised internally when a dotted path can't be resolved against an output."""


def _resolve_path(obj: Any, path: str) -> Any:
    """Traverse a nested object using a dotted path that may include array indices like field[0].sub.
    Raises _PathMiss if any segment is absent so the caller can fall back gracefully."""
    for part in path.split("."):
        segments = _INDEX_RE.split(part)
        for seg in segments:
            if not seg:
                continue
            try:
                if seg.startswith("[") and seg.endswith("]"):
                    obj = obj[int(seg[1:-1])]
                else:
                    obj = obj[seg]
            except (KeyError, IndexError, TypeError):
                raise _PathMiss(seg)
    return obj


#: How deep a plan's inputs are followed. A model-authored structure is a handful of levels
#: at most; this only exists so a pathological one cannot raise RecursionError inside the
#: worker, which would fail the goal for a reason that has nothing to do with the goal.
_MAX_DEPTH = 12


def resolve_inputs(inputs: dict, task_outputs: dict[str, dict]) -> dict:
    """Replace {{task_id.output}} or {{task_id.output.field}} templates with values from completed tasks.

    Resilient by design: if the LLM-authored plan references a field that does not
    exist on the upstream output (wrong field name, schema drift), fall back to the
    whole upstream output instead of failing the entire goal.

    **Templates are replaced wherever they appear, at any depth.** This walked only the top
    level once, and run `8738177b` is what that cost: the planner gave a writer task the
    inputs

        {"data": {"root_cause": "{{8738177b_t2.output.summary}}", ...}}

    and `data` was a dict, so every template inside it was returned untouched — no warning,
    no error, no resolution. The writer then produced "The root cause of the bug was related
    to {{8738177b_t2.output.summary}}." as finished prose, and the next task filed that text
    as an incident note. Only the publish-time placeholder guard stopped it reaching a page
    a human would read.

    Nesting is ordinary in an LLM-authored plan — the planner is shown
    `{"data": "{{t1.output}}"}` for the writer and nests one level deeper about as often as
    not — so it is a thing to support, not a thing to forbid."""

    def _lookup(task_id: str, path: str | None) -> Any:
        if task_id not in task_outputs:
            logger.warning("Interpolation: unknown task '%s' — substituting empty", task_id)
            return ""
        obj = task_outputs[task_id]
        if not path:
            return obj
        try:
            return _resolve_path(obj, path)
        except _PathMiss as miss:
            logger.warning(
                "Interpolation: '%s.output.%s' missing segment %s — falling back to whole output of '%s'",
                task_id, path, miss, task_id,
            )
            return obj

    def resolve_value(v: Any, depth: int = 0) -> Any:
        if depth < _MAX_DEPTH:
            if isinstance(v, dict):
                return {k: resolve_value(item, depth + 1) for k, item in v.items()}
            if isinstance(v, list):
                return [resolve_value(item, depth + 1) for item in v]
        if not isinstance(v, str):
            return v
        full_match = TEMPLATE_RE.fullmatch(v)
        if full_match:
            task_id, path = full_match.groups()
            return _lookup(task_id, path)

        def replace(m: re.Match) -> str:
            task_id, path = m.groups()
            val = _lookup(task_id, path)
            return json.dumps(val) if isinstance(val, (dict, list)) else str(val)

        return TEMPLATE_RE.sub(replace, v)

    return {k: resolve_value(v) for k, v in inputs.items()}
