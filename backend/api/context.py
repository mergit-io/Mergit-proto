from fastapi import APIRouter
from pydantic import BaseModel

import context as ctx_store

router = APIRouter(prefix="/api/config", tags=["config"])


class ContextBody(BaseModel):
    github_repo: str = ""
    description: str = ""
    tech_stack: str = ""
    notes: str = ""


@router.get("/context")
async def get_context():
    return ctx_store.load()


@router.put("/context")
async def update_context(body: ContextBody):
    saved = ctx_store.save(body.model_dump())
    return {"ok": True, **saved}
