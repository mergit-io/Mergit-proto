from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import llm
import model_config
import model_health

router = APIRouter(prefix="/api/config", tags=["config"])


class ModelConfigUpdate(BaseModel):
    models: dict[str, str]


def _with_availability(models: list[dict]) -> list[dict]:
    """Annotate each offered model with whether this deployment can actually run it.

    Being in the catalogue only means the provider serves the id. Whether *this*
    instance can use it depends on an API key that is set at runtime, so it is computed
    per request rather than frozen at import — `PUT /api/config/keys` must take effect
    without a restart. Without this the picker renders every option identically, and the
    live instance (GROQ_API_KEY and nothing else) offered five Anthropic models that
    fail every goal the moment they are selected.
    """
    annotated = []
    for m in models:
        usable = llm.has_credentials(m["id"])
        annotated.append({
            **m,
            "usable": usable,
            "unusable_reason": None if usable else f"No {m['provider']} API key configured",
        })
    return annotated


@router.get("/models")
async def get_model_config():
    return {
        "models": model_config.get_all(),
        "available": _with_availability(model_config.AVAILABLE_MODELS),
        "defaults": model_config.DEFAULTS,
    }


@router.put("/models")
async def update_model_config(body: ModelConfigUpdate):
    try:
        updated = model_config.update(body.models)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"models": updated, "ok": True}


@router.get("/model-health")
async def get_model_health():
    status = model_health.get_status()
    return {"unhealthy": status, "all_healthy": len(status) == 0}
