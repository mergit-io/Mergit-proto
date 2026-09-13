from fastapi import APIRouter, Request
from pydantic import BaseModel

import context as ctx_store
from auth.gate import require_admin

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
async def update_context(body: ContextBody, request: Request):
    # `context.json` is deployment-wide too, and `github_repo` is the repository agents
    # act on by default — so an ordinary signed-in user must not be able to repoint it.
    require_admin(request)
    saved = ctx_store.save(body.model_dump())
    return {"ok": True, **saved}
