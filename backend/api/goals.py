import json

from fastapi import APIRouter, HTTPException

import db
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
async def submit_goal(body: SubmitGoalRequest) -> dict:
    if not body.goal or not body.goal.strip():
        raise HTTPException(status_code=400, detail="goal must not be empty")
    goal = await db.create_goal(body.goal.strip())
    return {"goal_id": goal.id, "status": goal.status, "created_at": goal.created_at}


@router.get("")
async def list_goals(status: str | None = None, limit: int = 20, offset: int = 0) -> GoalListResponse:
    goals = await db.list_goals(status=status, limit=limit, offset=offset)
    return GoalListResponse(
        goals=[GoalSummary(goal_id=g.id, title=g.title, status=g.status, created_at=g.created_at, updated_at=g.updated_at) for g in goals],
        total=len(goals),
    )


@router.get("/{goal_id}")
async def get_goal(goal_id: str) -> GoalResponse:
    goal = await db.get_goal(goal_id)
    if not goal:
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
