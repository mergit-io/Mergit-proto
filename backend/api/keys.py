import os
from pathlib import Path

from dotenv import dotenv_values, set_key
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import events as event_bus
from config import settings

router = APIRouter(prefix="/api/config", tags=["config"])

_ENV_FILE = Path(settings.runtime_config_dir) / ".env"

PROVIDER_KEYS: dict[str, str] = {
    "groq":      "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "tavily":    "TAVILY_API_KEY",
    "github":    "GITHUB_TOKEN",
    "omium":     "OMIUM_API_KEY",
}


def _mask(value: str) -> str:
    if not value or len(value) <= 8:
        return "***"
    return value[:6] + "..." + value[-4:]


@router.get("/keys")
async def get_keys():
    file_vals = dotenv_values(str(_ENV_FILE)) if _ENV_FILE.exists() else {}
    result = {}
    for provider, env_var in PROVIDER_KEYS.items():
        val = os.environ.get(env_var) or file_vals.get(env_var, "")
        val = (val or "").strip()
        result[provider] = {
            "env_var": env_var,
            "set": bool(val),
            "masked": _mask(val) if val else None,
        }
    return result


class KeyBody(BaseModel):
    provider: str
    key: str


@router.put("/keys")
async def update_key(body: KeyBody):
    provider = body.provider.lower()
    key_value = body.key.strip()

    if provider not in PROVIDER_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider!r}")
    if not key_value:
        raise HTTPException(status_code=400, detail="Key value cannot be empty")

    env_var = PROVIDER_KEYS[provider]

    _ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _ENV_FILE.exists():
        _ENV_FILE.touch()
    set_key(str(_ENV_FILE), env_var, key_value)
    os.environ[env_var] = key_value

    # Reinitialise Omium tracing live when key is updated
    if provider == "omium":
        import tracing as _tracing
        from config import settings as _settings
        _tracing.init_tracing(key_value, _settings.omium_project)

    # Resume any tasks that were waiting for this credential
    resumed = await db.resume_credential_tasks(env_var)
    for task in resumed:
        event_bus.emit(task["goal_id"], "task_update", {
            "task_id": task["id"],
            "status": "READY",
            "agent": task["agent_name"],
        })

    return {"ok": True, "provider": provider, "env_var": env_var, "masked": _mask(key_value), "resumed_tasks": len(resumed)}
