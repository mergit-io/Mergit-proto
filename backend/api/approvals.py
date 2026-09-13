"""Pending irreversible actions, and the decision that releases them.

The **only** authenticated releaser of an `approval:*` key. This matters: the other way to
un-park a task is `POST /api/webhooks/{token}`, which is unauthenticated by design and
releases any waiting task — so approvals deliberately do not use that mechanism, and this
router is the sole path from "waiting" to "allowed".
"""
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db
import events
from auth.gate import require_user
from tools import approval

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("")
async def list_approvals(request: Request, limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    user = require_user(request)
    return JSONResponse({
        "pending": await approval.list_pending(user["id"]),
        "recent": await approval.list_recent(user["id"], limit),
    })


class DecisionBody(BaseModel):
    decision: str  # "approve" | "deny"


@router.post("/{approval_id}")
async def decide(approval_id: str, body: DecisionBody, request: Request) -> JSONResponse:
    """Approve or deny, then release the parked task.

    Scoped to the caller inside the UPDATE, so learning an approval id is not enough to
    authorise an action against someone else's repository.
    """
    user = require_user(request)
    if body.decision not in ("approve", "deny"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'deny'")

    record = await approval.decide(approval_id, user["id"], body.decision)
    if not record:
        raise HTTPException(status_code=404, detail="Approval not found")

    # Release the task either way. On denial the gate raises PermissionError on the next
    # attempt, which the agent reports as a refusal — the run finishes and says what
    # happened, rather than sitting parked until it is swept away.
    resumed = await db.resume_credential_tasks(record["credential_key"])
    for task in resumed:
        events.emit(task["goal_id"], "task_update", {
            "task_id": task["id"], "status": "READY", "agent": task["agent_name"],
            "approval": body.decision,
        })

    logger.info("user=%s %sd approval %s (%s)", user["id"], body.decision, approval_id,
                record["summary"])
    return JSONResponse({
        "ok": True,
        "approval_id": approval_id,
        "decision": record["decision"],
        "already_decided": record["decision"] != body.decision,
        "resumed_tasks": len(resumed),
    })
