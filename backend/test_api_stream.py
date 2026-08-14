"""`GET /api/goals/{id}/stream` must end when the goal has ended.

Observed on the live deployment: opening the stream for a goal that had already
COMPLETED held the connection for 75 seconds and nine ping frames without ever sending
a terminating event. The endpoint only breaks on a *live* `goal_done` it happens to
witness, so a goal that finished before the client subscribed is never reported at all.

Two ways a client hangs:
  - opening a past goal from the dashboard (every visit leaks a connection), and
  - the race where the goal completes between the 404 lookup and `events.subscribe()`,
    which loses the event to nobody and hangs that client forever.
"""
import asyncio
import importlib
import json
import os
import tempfile

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture()
def stack(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("config.settings.db_path", os.path.join(tmp, "stream.db"))

    import db as _db
    importlib.reload(_db)
    import events as _events
    importlib.reload(_events)
    from api import stream as _stream
    importlib.reload(_stream)
    monkeypatch.setattr(_stream, "db", _db)
    monkeypatch.setattr(_stream, "events", _events)

    app = FastAPI()
    app.include_router(_stream.router)

    asyncio.run(_db.init_db())
    return app, _db, _events


async def _read_stream(app, goal_id: str, budget: float = 6.0) -> list[dict]:
    """Collect SSE frames until the server closes, or give up after `budget` seconds."""
    frames: list[dict] = []
    transport = httpx.ASGITransport(app=app)

    async def pump():
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            async with c.stream("GET", f"/api/goals/{goal_id}/stream") as r:
                assert r.status_code == 200, r.status_code
                name = None
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        raw = line.split(":", 1)[1].strip()
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            payload = raw
                        frames.append({"event": name, "data": payload})

    try:
        await asyncio.wait_for(pump(), timeout=budget)
    except asyncio.TimeoutError:
        frames.append({"event": "__TIMED_OUT__", "data": {}})
    return frames


def test_stream_of_a_completed_goal_closes_immediately(stack):
    app, db, _ = stack

    async def go():
        goal = await db.create_goal("already finished")
        await db.update_goal_status(goal.id, "COMPLETED", output={"text": "done"})

        frames = await _read_stream(app, goal.id)

        assert frames and frames[-1]["event"] != "__TIMED_OUT__", (
            "the stream never closed for a goal that is already COMPLETED — it will "
            "ping forever and leak one connection per dashboard visit"
        )
        assert any(f["event"] == "goal_done" for f in frames), (
            f"a client joining late was never told the goal finished; got {frames}"
        )

    asyncio.run(go())


def test_stream_of_a_failed_goal_closes_immediately(stack):
    app, db, _ = stack

    async def go():
        goal = await db.create_goal("already failed")
        await db.update_goal_status(goal.id, "FAILED", error="planner blew up")

        frames = await _read_stream(app, goal.id)

        assert frames[-1]["event"] != "__TIMED_OUT__", "stream did not close on a FAILED goal"
        terminal = [f for f in frames if f["event"] in ("goal_done", "goal_status")]
        assert terminal, f"no terminal event sent; got {frames}"
        assert terminal[-1]["data"]["status"] == "FAILED"
        assert terminal[-1]["data"]["error"] == "planner blew up"

        # LiveLog renders *any* goal_done as the literal text "COMPLETED", so a failed
        # goal must not be replayed under that event name.
        assert not any(f["event"] == "goal_done" for f in frames), (
            "a FAILED goal was replayed as `goal_done`; the live log would show it as "
            "COMPLETED"
        )

    asyncio.run(go())


def test_the_replayed_event_carries_the_stored_result(stack):
    """A late subscriber must get the same payload a live one would have seen."""
    app, db, _ = stack

    async def go():
        goal = await db.create_goal("finished with output")
        await db.update_goal_status(goal.id, "COMPLETED", output={"text": "the answer", "title": "t"})

        frames = await _read_stream(app, goal.id)
        done = next(f for f in frames if f["event"] == "goal_done")

        assert done["data"]["goal_id"] == goal.id
        assert done["data"]["output"] == {"text": "the answer", "title": "t"}

    asyncio.run(go())


def test_a_goal_finishing_between_lookup_and_subscribe_still_closes(stack, monkeypatch):
    """The race: the endpoint reads the goal as RUNNING, then it completes before the
    subscription exists, so the real `goal_done` goes to an empty subscriber list.

    Driven deterministically — the goal is completed between the handler's first and
    second read of it, which is exactly the window the subscription opens in.
    """
    app, db, events = stack
    from api import stream as stream_api

    async def go():
        goal = await db.create_goal("races to the finish")
        await db.update_goal_status(goal.id, "RUNNING")

        real_get_goal = db.get_goal
        reads = {"n": 0}

        async def get_goal_then_finish(goal_id):
            result = await real_get_goal(goal_id)
            reads["n"] += 1
            if reads["n"] == 1:  # the 404 lookup has happened; now it finishes
                await db.update_goal_status(goal.id, "COMPLETED", output={"text": "raced"})
            return result

        monkeypatch.setattr(stream_api.db, "get_goal", get_goal_then_finish)

        frames = await _read_stream(app, goal.id, budget=8.0)

        assert reads["n"] >= 2, (
            "the goal was read only once — its state was never re-checked after "
            "subscribing, so a goal finishing in that window hangs the client forever"
        )
        assert frames[-1]["event"] != "__TIMED_OUT__", (
            "the goal completed while the client was subscribing and the stream hung"
        )
        done = next(f for f in frames if f["event"] == "goal_done")
        assert done["data"]["output"] == {"text": "raced"}

    asyncio.run(go())


def test_a_lost_terminal_event_is_recovered_on_the_next_keepalive(stack, monkeypatch):
    """If the `goal_done` event never arrives — worker restart, full queue — the stream
    must still notice on its next keepalive rather than stay open indefinitely."""
    app, db, _ = stack
    from api import stream as stream_api

    monkeypatch.setattr(stream_api, "PING_TIMEOUT", 0.3)

    async def go():
        goal = await db.create_goal("finishes silently")
        await db.update_goal_status(goal.id, "RUNNING")

        async def finish_without_emitting():
            await asyncio.sleep(0.5)
            await db.update_goal_status(goal.id, "COMPLETED", output={"text": "silent"})

        task = asyncio.ensure_future(finish_without_emitting())
        frames = await _read_stream(app, goal.id, budget=8.0)
        await task

        assert frames[-1]["event"] != "__TIMED_OUT__", (
            "no terminal event was ever emitted and the stream never closed"
        )
        assert frames[-1]["event"] == "goal_done"
        assert frames[-1]["data"]["output"] == {"text": "silent"}

    asyncio.run(go())


def test_a_running_goal_still_streams_live_events(stack):
    """The fix must not turn the endpoint into a one-shot poll for live goals."""
    app, db, events = stack

    async def go():
        goal = await db.create_goal("still running")
        await db.update_goal_status(goal.id, "RUNNING")

        async def finish_later():
            await asyncio.sleep(0.4)
            events.emit(goal.id, "task_update", {"task_id": "t1", "status": "RUNNING"})
            await asyncio.sleep(0.2)
            await db.update_goal_status(goal.id, "COMPLETED", output={"text": "late"})
            events.emit(goal.id, "goal_done", {"status": "COMPLETED", "goal_id": goal.id, "output": {"text": "late"}})

        task = asyncio.ensure_future(finish_later())
        frames = await _read_stream(app, goal.id, budget=8.0)
        await task

        assert frames[-1]["event"] != "__TIMED_OUT__", "live stream never closed"
        assert any(f["event"] == "task_update" for f in frames), (
            f"live events were lost — the stream must not short-circuit a RUNNING goal; got {frames}"
        )

    asyncio.run(go())


def test_unknown_goal_is_still_a_404(stack):
    app, _, _ = stack

    async def go():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/api/goals/nope-00000000/stream")
        assert r.status_code == 404

    asyncio.run(go())
