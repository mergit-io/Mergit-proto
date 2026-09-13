from fastapi import APIRouter, HTTPException, Request

import db
from auth.gate import require_user
from models import TaskDetail, TaskListResponse

router = APIRouter(prefix="/api", tags=["tasks"])


def _to_detail(t) -> TaskDetail:
    return TaskDetail(
        id=t.id,
        goal_id=t.goal_id,
        agent_name=t.agent_name,
        description=t.description,
        status=t.status,
        inputs=t.inputs,
        output=t.output,
        error=t.error,
        attempt_count=t.attempt_count,
        wait_token=t.wait_token,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("/goals/{goal_id}/tasks")
async def list_goal_tasks(goal_id: str, request: Request) -> TaskListResponse:
    user = require_user(request)
    goal = await db.get_goal(goal_id, user_id=user["id"])
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    tasks = await db.list_goal_tasks(goal_id)
    return TaskListResponse(tasks=[_to_detail(t) for t in tasks])


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request) -> TaskDetail:
    """Tasks carry no owner of their own — ownership derives through the goal.

    Deliberate: a denormalised `user_id` on `tasks` would be a second place for the two to
    disagree, and the disagreement would be invisible until it leaked. One join instead.
    """
    user = require_user(request)
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    goal = await db.get_goal(task.goal_id, user_id=user["id"])
    if not goal:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_detail(task)
