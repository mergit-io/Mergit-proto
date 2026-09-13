import os
from pathlib import Path

from config import settings
from tracing import trace

WORKSPACE = Path(settings.workspace_dir).resolve()


def _safe_path(goal_id: str, rel_path: str) -> Path:
    base = (WORKSPACE / goal_id).resolve()
    base.mkdir(parents=True, exist_ok=True)
    # Strip any leading slashes / absolute prefix the LLM may inject
    if os.path.isabs(rel_path):
        rel_path = os.path.basename(rel_path)
    resolved = (base / rel_path).resolve()
    if not str(resolved).startswith(str(base)):
        raise ValueError(f"Path traversal attempt: {rel_path}")
    return resolved


@trace("file_ops")
async def file_ops(args: dict) -> dict:
    operation = args["operation"]
    path = args["path"]
    content = args.get("content", "")
    goal_id = args.get("_goal_id", "shared")

    if operation == "list":
        base = WORKSPACE / goal_id
        base.mkdir(parents=True, exist_ok=True)
        files = [str(p.relative_to(base)) for p in base.rglob("*") if p.is_file()]
        return {"files": files, "ok": True}

    full_path = _safe_path(goal_id, path)

    if operation == "read":
        if not full_path.exists():
            return {"ok": False, "error": f"File not found: {path}"}
        return {"content": full_path.read_text(), "ok": True}

    if operation == "write":
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return {"ok": True, "path": str(full_path.relative_to(WORKSPACE / goal_id).as_posix())}

    if operation == "append":
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "a") as f:
            f.write(content)
        return {"ok": True}

    return {"ok": False, "error": f"Unknown operation: {operation}"}


SCHEMA = {
    "description": "Read, write, append, or list files in the goal's workspace directory.",
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["read", "write", "append", "list"]},
        "path": {"type": "string", "description": "Relative file path within the workspace"},
        "content": {"type": "string", "description": "Content to write (for write/append operations)"},
    },
    "required": ["operation", "path"],
}
