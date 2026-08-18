import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

import db
import events
from auth.gate import require_user

router = APIRouter(prefix="/api/goals", tags=["stream"])

TERMINAL = ("COMPLETED", "FAILED")

#: How long to wait for an event before sending a keepalive and re-checking the goal's
#: stored state. Bounds how long a client can wait when a terminal event is lost.
PING_TIMEOUT = 30


def _terminal_frame(goal) -> dict:
    """The event a live subscriber would have received when this goal finished.

    Deliberately mirrors the worker's own choice of event name rather than always
    sending `goal_done`: `_after_task_done` emits `goal_done` on success and
    `_handle_goal_failure` emits `goal_status` on failure. Consumers rely on that split —
    `LiveLog` renders any `goal_done` as a completion — so a replay that sent `goal_done`
    for a FAILED goal would print "COMPLETED" underneath a goal that failed.
    """
    completed = goal.status == "COMPLETED"
    return {
        "event": "goal_done" if completed else "goal_status",
        "data": json.dumps({
            "status": goal.status,
            "goal_id": goal.id,
            "output": goal.output,
            "error": goal.error,
            "replayed": True,
        }),
    }


@router.get("/{goal_id}/stream")
async def stream_goal(goal_id: str, request: Request):
    # Checked BEFORE subscribing. This endpoint is the easiest one to leave open — it is
    # not CRUD-shaped, so it does not look like a read — and it streams raw tool results,
    # agent reasoning and goal output to anyone holding a goal id.
    #
    # The cookie arrives by itself: `lib/sse.ts` opens a relative URL, so the browser
    # attaches it same-origin. That is precisely why the session lives in a cookie rather
    # than an Authorization header, which EventSource cannot set.
    user = require_user(request)
    goal = await db.get_goal(goal_id, user_id=user["id"])
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Subscribe before deciding whether the goal is finished. The other order loses the
    # race: a goal completing between the status read and the subscription emits its
    # `goal_done` to nobody, and the client then waits on a queue no one will ever fill.
    q = events.subscribe(goal_id)

    async def generator():
        try:
            # Re-read after subscribing. Anything that finished before this point has no
            # event left to deliver, so replay it from stored state and close — otherwise
            # the stream sits open emitting pings forever, one leaked connection per
            # visit to a past goal on the dashboard.
            settled = await db.get_goal(goal_id)
            if settled and settled.status in TERMINAL:
                yield _terminal_frame(settled)
                return

            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=PING_TIMEOUT)
                    yield {"event": item["event"], "data": json.dumps(item["data"])}
                    if item["event"] in ("goal_done", "goal_status") and item["data"].get("status") in TERMINAL:
                        break
                except asyncio.TimeoutError:
                    # No traffic for 30s. A goal that reached a terminal state without us
                    # seeing its event (worker restart, dropped queue) would otherwise
                    # keep this connection alive indefinitely.
                    current = await db.get_goal(goal_id)
                    if current and current.status in TERMINAL:
                        yield _terminal_frame(current)
                        break
                    yield {"event": "ping", "data": "{}"}
        finally:
            events.unsubscribe(goal_id, q)

    return EventSourceResponse(generator())
