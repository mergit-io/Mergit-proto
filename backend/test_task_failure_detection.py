"""An agent that reports failure must not settle its task as DONE.

Observed on a real goal (sandbox issue #19). The integrator could not push or fork —
the bot account's token has read-only access — and returned:

    {"action": "create_pr_with_fallback_fork", "result": "failed", "url": null,
     "error": "Resource not accessible by personal access token (403)", ...}

The task was marked DONE, the goal COMPLETED, that payload became the goal's final
output, and a proof was minted on-chain attesting to a pull request that was never
created. Nothing had shipped.

The cause is that success was inferred purely from control flow:

    output = await agent_run(task, resolved, emit=emit)
    await db.settle_task(task.id, TaskStatus.DONE, output=output)   # returned == success

The agents already declare their own outcome — `coder` has a required `success: bool`
and `integrator` a required `result` (see `agent_registry.py`) — and neither was read.
A green goal that shipped nothing is worse than a red one, and the proof layer was
attesting to it.
"""
import asyncio
import importlib
import os
import tempfile

import pytest


@pytest.fixture()
def wk(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "fail.db"))
    monkeypatch.setattr(config.settings, "workspace_dir", os.path.join(tmp, "ws"))
    import db as _db
    importlib.reload(_db)
    import worker as _worker
    importlib.reload(_worker)
    monkeypatch.setattr(_worker, "db", _db, raising=False)
    asyncio.run(_db.init_db())
    _worker.tmpdb = _db
    return _worker


# ── the declared-outcome reader ─────────────────────────────────────────────────

#: The exact payload the integrator returned on the real run.
REAL_INTEGRATOR_FAILURE = {
    "action": "create_pr_with_fallback_fork",
    "result": "failed",
    "url": None,
    "error": "Resource not accessible by personal access token (403)",
    "details": "Attempted to create a PR for issue #19 ...",
}


def test_the_real_integrator_failure_is_recognised(wk):
    assert wk._declared_failure(REAL_INTEGRATOR_FAILURE), (
        "the payload from the observed run declares result=failed and carries a 403, "
        "and was still settled as DONE"
    )


@pytest.mark.parametrize("payload", [
    {"action": "create_pr", "result": "failed"},
    {"action": "create_pr", "result": "FAILED"},
    {"action": "create_pr", "result": "failure"},
    {"code": "x", "output": "y", "success": False},
    {"action": "push", "result": {}, "error": "403 Forbidden"},
])
def test_declared_failures_are_recognised(wk, payload):
    assert wk._declared_failure(payload)


@pytest.mark.parametrize("payload", [
    {"action": "create_pr", "result": {"pr_number": 18}, "url": "https://…/pull/18"},
    {"code": "x", "output": "ok", "success": True},
    {"summary": "the repo does error handling badly", "sources": []},
    {"action": "create_pr", "result": "created", "error": None},
    {"action": "create_pr", "result": "ok", "error": ""},
    "a plain string output",
    None,
])
def test_successful_or_ambiguous_output_is_left_alone(wk, payload):
    """False positives here fail working goals, so anything short of an explicit
    declaration of failure must pass. Note the researcher summary that merely mentions
    the word "error" in prose, and the coder that reports success alongside an empty
    error field."""
    assert not wk._declared_failure(payload)


def test_a_success_flag_outranks_a_stray_error_field(wk):
    """A coder that reports success must not be failed by a leftover error key."""
    assert not wk._declared_failure({"code": "x", "output": "y", "success": True,
                                     "error": "warning: deprecated call"})


# ── what the worker does with it ────────────────────────────────────────────────

def test_a_declared_failure_settles_the_task_as_failed(wk, monkeypatch):
    async def go():
        goal = await wk.tmpdb.create_goal("open a PR for issue #19")
        await wk.tmpdb.create_tasks([{
            "id": "t1", "agent": "integrator", "description": "open a PR",
            "inputs": {"repo": "o/r"}, "depends_on": [],
        }], goal.id, "trace-1")

        async def fake_agent_run(task, resolved, emit=None):
            return REAL_INTEGRATOR_FAILURE

        monkeypatch.setattr(wk, "agent_run", fake_agent_run)

        task = await wk.tmpdb.claim_ready_task("worker-1", 300)
        await wk._execute_task(task)

        settled = await wk.tmpdb.get_task(task.id)
        assert settled.status != "DONE", (
            "the integrator reported result=failed and the task was still marked DONE; "
            "the goal reports COMPLETED and mints a proof for a PR that never existed"
        )
        assert settled.error, "no error was recorded for a declared failure"
        assert "403" in str(settled.error) or "failed" in str(settled.error).lower()

    asyncio.run(go())


def test_a_declared_failure_mints_no_proof(wk, monkeypatch):
    """The proof layer must not attest to work that did not happen."""
    minted = []

    async def fake_agent_run(task, resolved, emit=None):
        return REAL_INTEGRATOR_FAILURE

    async def spy_after_done(task, output):
        minted.append(task.id)

    async def go():
        goal = await wk.tmpdb.create_goal("open a PR for issue #19")
        await wk.tmpdb.create_tasks([{
            "id": "t1", "agent": "integrator", "description": "open a PR",
            "inputs": {"repo": "o/r"}, "depends_on": [],
        }], goal.id, "trace-1")
        monkeypatch.setattr(wk, "agent_run", fake_agent_run)
        monkeypatch.setattr(wk, "_after_task_done", spy_after_done)

        task = await wk.tmpdb.claim_ready_task("worker-1", 300)
        await wk._execute_task(task)

        assert not minted, "a proof was minted for a task that declared failure"

    asyncio.run(go())


def test_a_successful_task_still_settles_as_done(wk, monkeypatch):
    """The guard must not break the working path."""
    async def fake_agent_run(task, resolved, emit=None):
        return {"action": "create_pr", "result": {"pr_number": 18},
                "url": "https://github.com/o/r/pull/18"}

    async def go():
        goal = await wk.tmpdb.create_goal("open a PR")
        await wk.tmpdb.create_tasks([{
            "id": "t1", "agent": "integrator", "description": "open a PR",
            "inputs": {"repo": "o/r"}, "depends_on": [],
        }], goal.id, "trace-1")
        monkeypatch.setattr(wk, "agent_run", fake_agent_run)

        task = await wk.tmpdb.claim_ready_task("worker-1", 300)
        await wk._execute_task(task)

        assert (await wk.tmpdb.get_task(task.id)).status == "DONE"

    asyncio.run(go())
