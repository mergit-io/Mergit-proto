"""Replanner tests — the "instead of giving up, find another path" claim.

Untested until now, despite being the difference between an agent system that stops at the
first failure and one that routes around it. Only the model is stubbed.
"""
import asyncio
import importlib
import json
import os
import tempfile
import types

import pytest


def _msg(tool_calls=None, content=""):
    calls = [
        types.SimpleNamespace(
            id=f"call_{i}",
            function=types.SimpleNamespace(name=name, arguments=json.dumps(args)),
        )
        for i, (name, args) in enumerate(tool_calls or [])
    ]
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=content, tool_calls=calls or None))]
    )


RECOVERY_PLAN = {
    "tasks": [
        {"id": "r1", "agent": "writer",
         "description": "Summarise what was achieved and what could not be done",
         "inputs": {"note": "web search was unavailable"}, "depends_on": []},
    ],
    "terminal": "r1",
    "reasoning": "The research step is unrecoverable; salvage the run with a summary.",
}


@pytest.fixture()
def ctx(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "replan.db"))

    import db as _db
    importlib.reload(_db)
    import replanner as _rp
    importlib.reload(_rp)

    calls = []

    async def fake_llm(model, messages, **kwargs):
        calls.append(messages)
        return _msg([("submit_plan", RECOVERY_PLAN)])

    monkeypatch.setattr(_rp, "acompletion", fake_llm)
    asyncio.run(_db.init_db())

    return types.SimpleNamespace(db=_db, replanner=_rp, calls=calls)


async def _goal_with_failed_task(ctx):
    """A goal where the researcher finished and the coder then failed."""
    goal = await ctx.db.create_goal("Research X and build Y")
    await ctx.db.create_tasks(
        [
            {"id": "t1", "agent": "researcher", "description": "Research X",
             "inputs": {}, "depends_on": []},
            {"id": "t2", "agent": "coder", "description": "Build Y",
             "inputs": {}, "depends_on": ["t1"]},
        ],
        goal.id, goal.trace_id,
    )
    await ctx.db.set_goal_plan(goal.id, "{}", "t2")
    await ctx.db.settle_task("t1", ctx.db.TaskStatus.DONE,
                             output={"summary": "X is documented in the README",
                                     "key_points": ["a"], "sources": ["README.md"]})
    await ctx.db.settle_task("t2", ctx.db.TaskStatus.FAILED, error="web_search unavailable")
    return goal


# ── Guard ───────────────────────────────────────────────────────────────────────

def test_a_goal_may_be_replanned_once(ctx):
    async def go():
        goal = await _goal_with_failed_task(ctx)
        assert await ctx.replanner.should_replan(goal.id) is True

        assert await ctx.replanner.attempt_replan(goal.id, "t2", "web_search unavailable") is True

        # ...and never again, or a failing goal replans forever.
        assert await ctx.replanner.should_replan(goal.id) is False

    asyncio.run(go())


def test_unknown_goal_is_not_replanned(ctx):
    async def go():
        assert await ctx.replanner.should_replan("no-such-goal") is False
        assert await ctx.replanner.attempt_replan("no-such-goal", "t1", "boom") is False
    asyncio.run(go())


def test_unknown_failed_task_is_not_replanned(ctx):
    async def go():
        goal = await _goal_with_failed_task(ctx)
        assert await ctx.replanner.attempt_replan(goal.id, "no-such-task", "boom") is False
    asyncio.run(go())


# ── What the planner is told ────────────────────────────────────────────────────

def test_replan_prompt_carries_progress_and_failure(ctx):
    """The whole point: the new plan must know what already worked and what broke."""
    async def go():
        goal = await _goal_with_failed_task(ctx)
        await ctx.replanner.attempt_replan(goal.id, "t2", "web_search unavailable")

        prompt = ctx.calls[0][1]["content"]
        assert "X is documented in the README" in prompt, "completed work was not carried over"
        assert "Build Y" in prompt, "the failed task was not described"
        assert "web_search unavailable" in prompt, "the failure reason was not passed on"
        assert "do NOT redo" in prompt or "Do not include tasks that already completed" in prompt

    asyncio.run(go())


# ── What the replan produces ────────────────────────────────────────────────────

def test_replan_inserts_new_tasks_and_moves_the_terminal(ctx):
    async def go():
        goal = await _goal_with_failed_task(ctx)
        await ctx.replanner.attempt_replan(goal.id, "t2", "web_search unavailable")

        tasks = await ctx.db.list_goal_tasks(goal.id)
        new_tasks = [t for t in tasks if t.id not in ("t1", "t2")]
        assert len(new_tasks) == 1
        assert new_tasks[0].agent_name == "writer"
        assert new_tasks[0].status == "READY", "a dependency-free new task must be runnable"

        refreshed = await ctx.db.get_goal(goal.id)
        assert refreshed.terminal_task_id == new_tasks[0].id, (
            "the goal still points at the failed task as terminal, so it can never complete"
        )

    asyncio.run(go())


def test_replanned_task_ids_cannot_collide_with_the_originals(ctx):
    async def go():
        goal = await _goal_with_failed_task(ctx)
        await ctx.replanner.attempt_replan(goal.id, "t2", "boom")

        tasks = await ctx.db.list_goal_tasks(goal.id)
        assert len({t.id for t in tasks}) == len(tasks), "duplicate task ids"
        assert any(t.id.startswith(f"{goal.id[:8]}_r") for t in tasks)

    asyncio.run(go())


def test_goal_returns_to_running_and_is_flagged(ctx):
    async def go():
        goal = await _goal_with_failed_task(ctx)
        await ctx.replanner.attempt_replan(goal.id, "t2", "web_search unavailable")

        refreshed = await ctx.db.get_goal(goal.id)
        assert refreshed.status == "RUNNING", "a replanned goal must not stay failed"
        assert "[replanned]" in (refreshed.error or ""), "the replan flag is what stops a second one"

    asyncio.run(go())


def test_completed_work_is_preserved(ctx):
    """Replanning must never discard a task that already succeeded."""
    async def go():
        goal = await _goal_with_failed_task(ctx)
        await ctx.replanner.attempt_replan(goal.id, "t2", "boom")

        t1 = await ctx.db.get_task("t1")
        assert t1.status == "DONE"
        assert t1.output["summary"] == "X is documented in the README"

    asyncio.run(go())


# ── Failure modes ───────────────────────────────────────────────────────────────

def test_a_planner_error_does_not_raise(ctx, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(ctx.replanner, "acompletion", boom)

    async def go():
        goal = await _goal_with_failed_task(ctx)
        assert await ctx.replanner.attempt_replan(goal.id, "t2", "boom") is False

        # A failed replan must change nothing: no new tasks, and no [replanned] flag —
        # otherwise the one retry the goal is entitled to gets silently consumed.
        refreshed = await ctx.db.get_goal(goal.id)
        assert "[replanned]" not in (refreshed.error or "")
        assert {t.id for t in await ctx.db.list_goal_tasks(goal.id)} == {"t1", "t2"}
        assert await ctx.replanner.should_replan(goal.id) is True

    asyncio.run(go())


def test_an_invalid_replan_is_rejected(ctx, monkeypatch):
    """A plan whose terminal does not exist must not be persisted."""
    async def bad_plan(*_a, **_k):
        return _msg([("submit_plan", {
            "tasks": [{"id": "r1", "agent": "writer", "description": "d",
                       "inputs": {}, "depends_on": []}],
            "terminal": "does_not_exist",
            "reasoning": "broken",
        })])

    monkeypatch.setattr(ctx.replanner, "acompletion", bad_plan)

    async def go():
        goal = await _goal_with_failed_task(ctx)
        assert await ctx.replanner.attempt_replan(goal.id, "t2", "boom") is False

        tasks = await ctx.db.list_goal_tasks(goal.id)
        assert {t.id for t in tasks} == {"t1", "t2"}, "a rejected plan leaked tasks into the DB"

    asyncio.run(go())


def test_no_tool_call_from_the_planner_is_handled(ctx, monkeypatch):
    async def no_call(*_a, **_k):
        return _msg(content="I am not going to answer.")

    monkeypatch.setattr(ctx.replanner, "acompletion", no_call)

    async def go():
        goal = await _goal_with_failed_task(ctx)
        assert await ctx.replanner.attempt_replan(goal.id, "t2", "boom") is False

    asyncio.run(go())
