"""A goal that never did the work it planned must not report COMPLETED.

Live failure, goal 32d630f2. The plan was:

    researcher -> coder -> researcher (review) -> integrator (raise the PR)
                                              -> writer (terminal)

The review researcher FAILED. `promote_ready_tasks` only promotes a task when every
dependency is DONE, so the integrator — the task that was going to open the pull request
the goal explicitly asked for — sat at PENDING and could never run. The writer, being the
terminal task, then finished and `_after_task_done` marked the whole goal **COMPLETED**.

The goal asked for a pull request. No pull request exists. It reported success.

The writer's own text said "partially completed", so the prose was honest while the status
was not — and the status is what an API caller, the dashboard and any automation reads.
"""
import asyncio
import importlib
import os
import tempfile

import pytest


@pytest.fixture()
def stack(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "blocked.db"))

    import db as _db
    importlib.reload(_db)
    asyncio.run(_db.init_db())
    return _db


def _plan(db, tasks):
    async def build():
        goal = await db.create_goal("Migrate auth.py to Rust and raise a PR", user_id="usr_legacy_demo")
        rows = await db.create_tasks(tasks, goal.id, goal.trace_id)
        return goal, rows

    return asyncio.run(build())


THE_LIVE_PLAN = [
    {"id": "t1", "agent": "researcher", "description": "Read auth.py",
     "inputs": {}, "depends_on": []},
    {"id": "t2", "agent": "coder", "description": "Write the Rust",
     "inputs": {}, "depends_on": ["t1"]},
    {"id": "t3", "agent": "researcher", "description": "Review the Rust",
     "inputs": {}, "depends_on": ["t2"]},
    {"id": "t4", "agent": "integrator", "description": "Raise a PR",
     "inputs": {}, "depends_on": ["t3"]},
    {"id": "t5", "agent": "writer", "description": "Summarise",
     "inputs": {}, "depends_on": ["t2"]},
]


def test_a_task_whose_dependency_failed_is_reported_as_blocked(stack):
    """The plain fact nothing was measuring: t4 can never run once t3 has failed."""
    import worker

    goal, rows = _plan(stack, THE_LIVE_PLAN)
    by_id = {r.description: r for r in rows}

    async def scenario():
        await stack.settle_task(by_id["Read auth.py"].id, "DONE", output={"ok": 1})
        await stack.settle_task(by_id["Write the Rust"].id, "DONE", output={"ok": 1})
        await stack.settle_task(by_id["Review the Rust"].id, "FAILED", error="Unterminated string")
        return await worker.blocked_task_ids(goal.id)

    blocked = asyncio.run(scenario())
    assert by_id["Raise a PR"].id in blocked


def test_a_task_blocked_behind_another_blocked_task_counts_too(stack):
    """Blockage is transitive — a chain of three is dead from the first failure."""
    import worker

    goal, rows = _plan(stack, THE_LIVE_PLAN + [
        {"id": "t6", "agent": "writer", "description": "Report on the PR",
         "inputs": {}, "depends_on": ["t4"]},
    ])
    by_id = {r.description: r for r in rows}

    async def scenario():
        await stack.settle_task(by_id["Review the Rust"].id, "FAILED", error="boom")
        return await worker.blocked_task_ids(goal.id)

    blocked = asyncio.run(scenario())
    assert by_id["Raise a PR"].id in blocked
    assert by_id["Report on the PR"].id in blocked


def test_nothing_is_blocked_when_every_task_can_still_run(stack):
    import worker

    goal, rows = _plan(stack, THE_LIVE_PLAN)
    by_id = {r.description: r for r in rows}

    async def scenario():
        await stack.settle_task(by_id["Read auth.py"].id, "DONE", output={"ok": 1})
        return await worker.blocked_task_ids(goal.id)

    assert asyncio.run(scenario()) == []


def test_a_failed_task_that_was_replanned_around_does_not_block_anything(stack):
    """Replanning deliberately leaves a FAILED task behind and adds new ones that do not
    depend on it. That is a recovery, not a blockage, and must not fail the goal."""
    import worker

    goal, rows = _plan(stack, [
        {"id": "t1", "agent": "coder", "description": "First attempt",
         "inputs": {}, "depends_on": []},
        {"id": "t2", "agent": "writer", "description": "Replacement work",
         "inputs": {}, "depends_on": []},
    ])
    by_id = {r.description: r for r in rows}

    async def scenario():
        await stack.settle_task(by_id["First attempt"].id, "FAILED", error="boom")
        return await worker.blocked_task_ids(goal.id)

    assert asyncio.run(scenario()) == []


def test_the_goal_does_not_report_completed_while_work_is_blocked(stack):
    """The whole point. The terminal task produced a real answer, so its output is kept —
    but the status has to say the goal did not do what it planned."""
    import worker

    goal, rows = _plan(stack, THE_LIVE_PLAN)
    by_id = {r.description: r for r in rows}
    writer_task = by_id["Summarise"]

    async def scenario():
        await stack.settle_task(by_id["Review the Rust"].id, "FAILED", error="Unterminated string")
        await stack.set_goal_plan(goal.id, "{}", writer_task.id)
        await stack.settle_task(writer_task.id, "DONE", output={"text": "partially completed"})
        await worker._after_task_done(await stack.get_task(writer_task.id),
                                      {"text": "partially completed"})
        return await stack.get_goal(goal.id)

    done = asyncio.run(scenario())
    assert done.status != "COMPLETED", "a goal with permanently blocked work reported success"
    assert "Raise a PR" in (done.error or "") or "t4" in (done.error or "") or \
           str(by_id["Raise a PR"].id) in (done.error or ""), \
        "the failure must name the work that never ran"
    assert done.output is not None, "the terminal task's answer must not be thrown away"


def test_a_clean_run_still_reports_completed(stack):
    """The guard must not spoil the ordinary case."""
    import worker

    goal, rows = _plan(stack, [
        {"id": "t1", "agent": "researcher", "description": "Read", "inputs": {}, "depends_on": []},
        {"id": "t2", "agent": "writer", "description": "Write", "inputs": {}, "depends_on": ["t1"]},
    ])
    by_id = {r.description: r for r in rows}

    async def scenario():
        await stack.settle_task(by_id["Read"].id, "DONE", output={"ok": 1})
        await stack.set_goal_plan(goal.id, "{}", by_id["Write"].id)
        await stack.settle_task(by_id["Write"].id, "DONE", output={"text": "all done"})
        await worker._after_task_done(await stack.get_task(by_id["Write"].id), {"text": "all done"})
        return await stack.get_goal(goal.id)

    assert asyncio.run(scenario()).status == "COMPLETED"
