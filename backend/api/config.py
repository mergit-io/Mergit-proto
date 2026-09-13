from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import model_config
import model_health
from auth.gate import require_admin

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
async def update_model_config(body: ModelConfigUpdate, request: Request):
    # `model_config.json` is a single file for the whole deployment, so this write picks
    # the model every other user's agents will run on. Reading it is harmless and the
    # Models page needs it; overwriting it is an operator action.
    require_admin(request)
    try:
        updated = model_config.update(body.models)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"models": updated, "ok": True}


@router.get("/model-health")
async def get_model_health():
    status = model_health.get_status()
    return {"unhealthy": status, "all_healthy": len(status) == 0}
