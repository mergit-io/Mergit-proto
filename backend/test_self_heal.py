"""Self-heal tests — covering the gaps found in the 2026-08-12 audit.

Before this: no tests, no dedup (N failures → N identical GitHub issues), no recursion
guard (a failing fix-goal filed another issue → loop), no persistence, no UI surface, and a
silent no-op without GITHUB_TOKEN.
"""
import asyncio
import importlib
import os
import tempfile

import pytest


@pytest.fixture()
def ctx(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "test.db"))
    monkeypatch.setattr(config.settings, "github_token", "")   # offline by default
    monkeypatch.setenv("GITHUB_TOKEN", "")

    import db as _db
    importlib.reload(_db)
    import self_heal as _sh
    importlib.reload(_sh)
    asyncio.run(_db.init_db())

    class Ctx:
        db, self_heal = _db, _sh
    return Ctx()


BUG = 'File "agent_runner.py", line 88\nKeyError: \'output\''


def _goal(ctx, text="do a thing", source="user", heal_depth=0):
    return asyncio.run(ctx.db.create_goal(text, user_id="usr_legacy_demo", source=source, heal_depth=heal_depth))


def _trigger(ctx, goal, error=BUG, agent="coder", task_id="t1"):
    return asyncio.run(ctx.self_heal.trigger(
        goal_id=goal.id, goal_title=goal.title, failed_task_agent=agent,
        error=error, error_summary="KeyError: 'output'", task_id=task_id))


# ── Offline mode (gap 6): demoable with zero credentials ────────────────────────

def test_records_a_simulated_attempt_without_github_token(ctx):
    attempt = _trigger(ctx, _goal(ctx))

    assert attempt is not None, "self-heal must not silently no-op without a token"
    assert attempt["status"] == "simulated"
    assert attempt["issue_body"], "the issue it would have filed must be preserved"
    assert "KeyError" in attempt["issue_body"]


def test_simulated_attempt_is_persisted_and_listable(ctx):
    _trigger(ctx, _goal(ctx))
    attempts = asyncio.run(ctx.db.list_heal_attempts())

    assert len(attempts) == 1
    assert attempts[0]["agent_name"] == "coder"
    assert attempts[0]["classification"] == "bug"


# ── Dedup (gap 2): N identical failures must not file N issues ──────────────────

def test_identical_errors_dedupe_to_one_attempt(ctx):
    goal = _goal(ctx)
    first = _trigger(ctx, goal)
    second = _trigger(ctx, _goal(ctx))
    third = _trigger(ctx, _goal(ctx))

    assert second["status"] == "skipped_duplicate"
    assert third["status"] == "skipped_duplicate"
    assert len(asyncio.run(ctx.db.list_heal_attempts())) == 1

    stored = asyncio.run(ctx.db.get_heal_attempt(first["id"]))
    assert stored["recurrence_count"] == 3, "recurrences are counted, not discarded"


def test_different_errors_produce_separate_attempts(ctx):
    _trigger(ctx, _goal(ctx), error=BUG)
    _trigger(ctx, _goal(ctx), error='File "worker.py", line 4\nTypeError: nope')

    assert len(asyncio.run(ctx.db.list_heal_attempts())) == 2


def test_fingerprint_ignores_volatile_details(ctx):
    """The same bug reported with different line numbers, ids and timestamps is one bug."""
    a = ctx.self_heal.fingerprint("coder", 'File "agent_runner.py", line 88\nKeyError: x')
    b = ctx.self_heal.fingerprint("coder", 'File "agent_runner.py", line 1204\nKeyError: x')
    assert a == b

    different = ctx.self_heal.fingerprint("coder", 'File "worker.py", line 88\nKeyError: x')
    assert a != different


# ── Recursion guard (gap 3): a failing fix-goal must not spawn another ──────────

def test_heal_spawned_goal_never_triggers_another_heal(ctx):
    healed_goal = _goal(ctx, "fix the bug", source="self_heal", heal_depth=1)
    attempt = _trigger(ctx, healed_goal)

    assert attempt["status"] == "skipped_depth"
    assert asyncio.run(ctx.db.list_heal_attempts()) == []


def test_fix_goal_is_tagged_with_incremented_depth(ctx):
    attempt = _trigger(ctx, _goal(ctx))
    fix_goal = asyncio.run(ctx.db.get_goal(attempt["fix_goal_id"]))

    assert fix_goal.source == "self_heal"
    assert fix_goal.heal_depth == 1
    assert "KeyError" in fix_goal.goal_text


# ── Outcome tracking (gap 7) ────────────────────────────────────────────────────

def test_outcome_settles_when_the_fix_goal_finishes(ctx):
    attempt = _trigger(ctx, _goal(ctx))

    asyncio.run(ctx.self_heal.settle_outcome(attempt["fix_goal_id"], "COMPLETED"))
    assert asyncio.run(ctx.db.get_heal_attempt(attempt["id"]))["outcome"] == "fixed"


def test_failed_fix_goal_marks_attempt_failed(ctx):
    attempt = _trigger(ctx, _goal(ctx))

    asyncio.run(ctx.self_heal.settle_outcome(attempt["fix_goal_id"], "FAILED"))
    assert asyncio.run(ctx.db.get_heal_attempt(attempt["id"]))["outcome"] == "failed"


def test_settling_an_unrelated_goal_is_harmless(ctx):
    asyncio.run(ctx.self_heal.settle_outcome("some-random-goal", "COMPLETED"))  # must not raise


# ── Robustness (gap 8): never raise into the worker ─────────────────────────────

def test_trigger_survives_a_broken_database(ctx, monkeypatch):
    """A self-heal failure must never propagate into the worker's failure handler."""
    goal = _goal(ctx)   # created before the breakage is installed

    def explode(*_args, **_kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(ctx.db, "find_heal_attempt_by_fingerprint", explode)
    assert _trigger(ctx, goal) is None      # degrades to None, does not raise


def test_fix_goal_failure_still_records_the_attempt(ctx, monkeypatch):
    """If the fix goal cannot be spawned, the detection is still recorded and marked."""
    goal = _goal(ctx)

    def explode(*_args, **_kwargs):
        raise RuntimeError("cannot create goal")

    monkeypatch.setattr(ctx.db, "create_goal", explode)
    attempt = _trigger(ctx, goal)

    assert attempt is not None
    assert attempt["status"] == "simulated"
    stored = asyncio.run(ctx.db.get_heal_attempt(attempt["id"]))
    assert stored["outcome"] == "abandoned"


# ── Stats for the UI (gap 5) ────────────────────────────────────────────────────

def test_stats_summarise_attempts(ctx):
    _trigger(ctx, _goal(ctx))
    _trigger(ctx, _goal(ctx))                                       # duplicate
    _trigger(ctx, _goal(ctx), error='File "db.py", line 2\nValueError: x')

    stats = asyncio.run(ctx.db.heal_stats())
    assert stats["total"] == 2
    assert stats["recurrences"] >= 3
    assert stats["by_status"]["simulated"] == 2
