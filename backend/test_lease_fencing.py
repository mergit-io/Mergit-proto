"""A worker that lost its lease must not settle the task anyway.

Live failure, goal 60d42a5f. The recorded end state was impossible on its face:

    coder      t2  FAILED     (3 attempts)
    integrator t3  DONE       depends_on = [t2]   ← ran anyway, opened PR #40
    writer     t4  DONE
    integrator t5  DONE       posted a review on PR #40
    goal           COMPLETED

`promote_ready_tasks` only promotes a task when every dependency is DONE, so t3 could
only have started while t2 was DONE — yet t2 ends FAILED.

The lease explains it. `settings.lease_seconds` is 300, and `reclaim_expired_leases`
flips a still-RUNNING task back to READY once its lease expires, without knowing whether
the original coroutine is still going. A long coder run therefore gets executed twice:

    worker A  runs t2 ............................ (>300s)
    reclaim   t2 RUNNING -> READY
    worker B  claims t2, runs it too
    worker A  finishes, settle_task(t2, DONE)  -> _after_task_done promotes t3
    worker B  finishes, settle_task(t2, FAILED) -> overwrites the DONE

`settle_task` writes by id alone: no worker check, no status check. Whoever finishes last
wins, including a worker whose lease was taken away.

This is also why goal 00605510's coder output changed between two reads of the same
completed goal — a second execution overwrote the first.
"""
import asyncio
import importlib
import os
import tempfile

import pytest


@pytest.fixture()
def dbmod(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "lease.db"))
    import db as _db
    importlib.reload(_db)
    asyncio.run(_db.init_db())
    return _db


async def _expire_lease(db, task_id):
    """Age the lease out, exactly as time passing would. No production helper needed."""
    async with db.get_conn() as conn:
        await conn.execute("UPDATE tasks SET lease_expires_at=1 WHERE id=?", (task_id,))
        await conn.commit()


def _one_task(db):
    async def build():
        goal = await db.create_goal("a goal")
        rows = await db.create_tasks(
            [{"id": "t1", "agent": "coder", "description": "work", "inputs": {}, "depends_on": []}],
            goal.id, goal.trace_id)
        return goal, rows[0]
    return asyncio.run(build())


def test_a_worker_whose_lease_was_reclaimed_cannot_settle(dbmod):
    """The exact race from goal 60d42a5f, in miniature."""
    goal, task = _one_task(dbmod)

    async def scenario():
        # Worker A claims and starts.
        claimed = await dbmod.claim_ready_task("worker-A", 300)
        assert claimed.id == task.id

        # Its lease expires and the reclaimer hands the task back to the pool.
        await _expire_lease(dbmod, task.id)
        assert (await dbmod.reclaim_expired_leases()) == 1

        # Worker B picks it up.
        b = await dbmod.claim_ready_task("worker-B", 300)
        assert b is not None and b.id == task.id

        # Worker A now finishes and tries to record its result. It no longer owns the task.
        await dbmod.settle_task(task.id, "DONE", output={"from": "A"}, worker_id="worker-A")
        return await dbmod.get_task(task.id)

    after = asyncio.run(scenario())
    assert after.status == "RUNNING", "a worker that lost its lease settled the task anyway"
    assert after.worker_id == "worker-B"
    assert after.output is None


def test_the_worker_that_holds_the_lease_settles_normally(dbmod):
    goal, task = _one_task(dbmod)

    async def scenario():
        await dbmod.claim_ready_task("worker-A", 300)
        await dbmod.settle_task(task.id, "DONE", output={"from": "A"}, worker_id="worker-A")
        return await dbmod.get_task(task.id)

    after = asyncio.run(scenario())
    assert after.status == "DONE"
    assert after.output == {"from": "A"}


def test_a_settled_task_is_not_overwritten_by_a_late_duplicate(dbmod):
    """The damaging half: t2 was DONE, downstream work started on that output, and a
    straggler turned it into FAILED afterwards."""
    goal, task = _one_task(dbmod)

    async def scenario():
        await dbmod.claim_ready_task("worker-A", 300)
        await _expire_lease(dbmod, task.id)
        await dbmod.reclaim_expired_leases()
        await dbmod.claim_ready_task("worker-B", 300)
        # B finishes first and the result is recorded.
        await dbmod.settle_task(task.id, "DONE", output={"from": "B"}, worker_id="worker-B")
        # A straggles in with a failure for the same task.
        await dbmod.settle_task(task.id, "FAILED", error="boom", worker_id="worker-A")
        return await dbmod.get_task(task.id)

    after = asyncio.run(scenario())
    assert after.status == "DONE", "a stale worker overwrote a completed task with a failure"
    assert after.output == {"from": "B"}


def test_settling_without_a_worker_id_still_works(dbmod):
    """Retry and requeue paths settle administratively rather than as a lease holder, and
    those must keep working."""
    goal, task = _one_task(dbmod)

    async def scenario():
        await dbmod.claim_ready_task("worker-A", 300)
        await dbmod.settle_task(task.id, "READY", error="retrying")
        return await dbmod.get_task(task.id)

    assert asyncio.run(scenario()).status == "READY"
