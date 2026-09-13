import asyncio
import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

import db
import events

router = APIRouter(prefix="/api/goals", tags=["stream"])


@router.get("/{goal_id}/stream")
async def stream_goal(goal_id: str):
    goal = await db.get_goal(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    q = events.subscribe(goal_id)

    async def generator():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=30)
                    yield {"event": item["event"], "data": json.dumps(item["data"])}
                    if item["event"] in ("goal_done", "goal_status") and item["data"].get("status") in ("COMPLETED", "FAILED"):
                        break
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            events.unsubscribe(goal_id, q)

    return EventSourceResponse(generator())
