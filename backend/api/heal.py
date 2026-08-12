"""Self-heal API — makes the auto-repair loop observable.

Before this the whole mechanism ran invisibly: no endpoint, no page, no history.
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

import db
import events
import self_heal

router = APIRouter(prefix="/api/heal", tags=["self-heal"])


@router.get("/attempts")
async def list_attempts(limit: int = 100):
    """Every detected bug, newest first, with its issue, fix goal and outcome."""
    return await db.list_heal_attempts(limit=limit)


@router.get("/stats")
async def stats():
    """Headline numbers: distinct bugs, total recurrences, how many were fixed."""
    return await db.heal_stats()


@router.get("/attempts/{attempt_id}")
async def get_attempt(attempt_id: str):
    attempt = await db.get_heal_attempt(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Unknown heal attempt")
    return attempt


@router.get("/stream")
async def stream():
    """Live feed of heal_started / heal_recurrence / heal_settled events."""
    queue = events.subscribe(self_heal.HEAL_CHANNEL)

    async def generator():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": item["event"], "data": json.dumps(item["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            events.unsubscribe(self_heal.HEAL_CHANNEL, queue)

    return EventSourceResponse(generator())
