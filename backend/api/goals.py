import json

from fastapi import APIRouter, HTTPException, Query, Request

import db
from auth.gate import require_user
from config import settings
from models import GoalListResponse, GoalResponse, GoalSummary, SubmitGoalRequest

router = APIRouter(prefix="/api/goals", tags=["goals"])


def _task_to_dict(t) -> dict:
    return {
        "id": t.id,
        "agent_name": t.agent_name,
        "description": t.description,
        "status": t.status,
        "inputs": t.inputs,
        "output": t.output,
        "error": t.error,
        "attempt_count": t.attempt_count,
        "wait_token": t.wait_token,
        "depends_on": t.depends_on,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@router.post("", status_code=202)
async def submit_goal(body: SubmitGoalRequest, request: Request) -> dict:
    user = require_user(request)
    goal_text = (body.goal or "").strip()
    if not goal_text:
        raise HTTPException(status_code=400, detail="goal must not be empty")
    if len(goal_text) > settings.max_goal_chars:
        raise HTTPException(
            status_code=413,
            detail=f"goal must be at most {settings.max_goal_chars} characters (got {len(goal_text)})",
        )
    goal = await db.create_goal(goal_text, user_id=user["id"])
    return {"goal_id": goal.id, "status": goal.status, "created_at": goal.created_at}


@router.get("")
async def list_goals(
    request: Request,
    status: str | None = None,
    # Bounded because these reach `LIMIT ?`/`OFFSET ?` directly and SQLite reads a
    # negative limit as unbounded — ?limit=-1 returned the whole table.
    limit: int = Query(20, ge=1, le=settings.max_page_size),
    offset: int = Query(0, ge=0),
) -> GoalListResponse:
    user = require_user(request)
    goals = await db.list_goals(status=status, limit=limit, offset=offset,
                                user_id=user["id"])
    return GoalListResponse(
        goals=[GoalSummary(goal_id=g.id, title=g.title, status=g.status, created_at=g.created_at, updated_at=g.updated_at) for g in goals],
        total=len(goals),
    )


@router.get("/{goal_id}")
async def get_goal(goal_id: str, request: Request) -> GoalResponse:
    user = require_user(request)
    goal = await db.get_goal(goal_id, user_id=user["id"])
    if not goal:
        # 404, never 403. A 403 confirms the goal exists, which turns sequential ids into
        # an enumeration oracle: an attacker learns how many goals the deployment has and
        # which ids are real, without ever reading one.
        raise HTTPException(status_code=404, detail="Goal not found")
    tasks = await db.list_goal_tasks(goal_id)
    return GoalResponse(
        goal_id=goal.id,
        title=goal.title,
        goal_text=goal.goal_text,
        status=goal.status,
        output=goal.output,
        error=goal.error,
        plan=json.loads(goal.plan_json) if goal.plan_json else None,
        tasks=[_task_to_dict(t) for t in tasks],
        trace_id=goal.trace_id,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )
