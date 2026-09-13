"""
In-process SSE event bus. Worker pushes events; stream endpoint drains them.
Uses asyncio.Queue per goal. No Redis needed (single-process deployment).
"""
import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_queues: dict[str, list[asyncio.Queue]] = {}


def subscribe(goal_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _queues.setdefault(goal_id, []).append(q)
    return q


def unsubscribe(goal_id: str, q: asyncio.Queue) -> None:
    subs = _queues.get(goal_id, [])
    try:
        subs.remove(q)
    except ValueError:
        pass


def emit(goal_id: str, event: str, data: dict[str, Any]) -> None:
    data["ts"] = int(time.time())
    subs = _queues.get(goal_id, [])
    for q in subs:
        try:
            q.put_nowait({"event": event, "data": data})
        except asyncio.QueueFull:
            logger.warning("SSE queue full for goal %s, dropping event %s", goal_id, event)
