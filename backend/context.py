import json
from pathlib import Path

from config import settings

CONTEXT_FILE = Path(settings.runtime_config_dir) / "context.json"

DEFAULT: dict = {
    "github_repo": "",
    "description": "",
    "tech_stack": "",
    "notes": "",
}


def load() -> dict:
    if CONTEXT_FILE.exists():
        try:
            return {**DEFAULT, **json.loads(CONTEXT_FILE.read_text())}
        except Exception:
            pass
    return dict(DEFAULT)


def save(ctx: dict) -> dict:
    merged = {**DEFAULT, **{k: v for k, v in ctx.items() if k in DEFAULT}}
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(json.dumps(merged, indent=2))
    return merged


def get_context_prompt() -> str:
    ctx = load()
    parts = []
    if ctx.get("github_repo"):
        parts.append(f"- GitHub repo: {ctx['github_repo']}")
    if ctx.get("description"):
        parts.append(f"- Project: {ctx['description']}")
    if ctx.get("tech_stack"):
        parts.append(f"- Tech stack: {ctx['tech_stack']}")
    if ctx.get("notes"):
        parts.append(f"- Notes: {ctx['notes']}")
    if not parts:
        return ""
    return "\n\nProject context (use when planning and executing):\n" + "\n".join(parts)
