import os
from pathlib import Path

from dotenv import dotenv_values, set_key
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import events as event_bus

router = APIRouter(prefix="/api/config", tags=["config"])

_ENV_FILE = Path(__file__).parent.parent / ".env"

PROVIDER_KEYS: dict[str, str] = {
    "groq":      "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "google":    "GOOGLE_API_KEY",
    "mistral":   "MISTRAL_API_KEY",
    "tavily":    "TAVILY_API_KEY",
    "github":    "GITHUB_TOKEN",
    "slack":     "SLACK_WEBHOOK_URL",
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

    if not _ENV_FILE.exists():
        _ENV_FILE.touch()
    set_key(str(_ENV_FILE), env_var, key_value)
    os.environ[env_var] = key_value

    # LiteLLM uses GEMINI_API_KEY for gemini/ models — bridge from GOOGLE_API_KEY
    if provider == "google":
        set_key(str(_ENV_FILE), "GEMINI_API_KEY", key_value)
        os.environ["GEMINI_API_KEY"] = key_value

    # Resume any tasks that were waiting for this credential
    resumed = await db.resume_credential_tasks(env_var)
    for task in resumed:
        event_bus.emit(task["goal_id"], "task_update", {
            "task_id": task["id"],
            "status": "READY",
            "agent": task["agent_name"],
        })

    return {"ok": True, "provider": provider, "env_var": env_var, "masked": _mask(key_value), "resumed_tasks": len(resumed)}
