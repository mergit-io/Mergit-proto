from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import model_config
import model_health

router = APIRouter(prefix="/api/config", tags=["config"])


class ModelConfigUpdate(BaseModel):
    models: dict[str, str]


@router.get("/models")
async def get_model_config():
    return {
        "models": model_config.get_all(),
        "available": model_config.AVAILABLE_MODELS,
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
