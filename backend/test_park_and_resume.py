"""What happens to a task that stops half-way and is started again.

A task parks when a tool declines to run: `WAITING_CREDENTIAL` when the credential it
needs is absent, `WAITING_WEBHOOK` when it is waiting for something to call in. Parking
was rare while the only way to trigger it was forgetting an env var, so three bugs sat in
this path unnoticed. Per-user OAuth makes parking the normal case — every "connect your
GitHub" prompt is a park — so each of them becomes a product defect:

  1. The idempotency key included `attempt_count`, which `claim_ready_task` increments on
     every claim. A resumed task therefore hashed to a different key for identical work,
     missed the cache, and re-fired every write it had already completed.
  2. Parking spent a retry, so a task that paused three times had none left for its first
     genuine failure.
  3. `find_orphaned_goals` counted a parked task as stalled and swept its goal to FAILED
     while the user was still reading the prompt.

Fixing (1) naively introduces a fourth: with the key no longer varying by attempt, a park
cached as a completed call replays on resume and the task parks again forever. The tests
below pin all four.

Everything here is the real path — real `agent_runner`, real `db`, real tools. Only the
language model and PyGithub are stubbed, because neither is part of the wiring under test.
"""
import asyncio
import importlib
import json
import os
import tempfile
import types

import pytest

from tools.credential_request import WAITING_CREDENTIAL_SENTINEL


# ── Stubs ───────────────────────────────────────────────────────────────────────

class FakeComment:
    def __init__(self, n):
        self.id = n
        self.html_url = f"https://github.com/o/r/issues/1#issuecomment-{n}"


class FakeIssue:
    def __init__(self, ledger):
        self._ledger = ledger

    def create_comment(self, body):
        self._ledger.append(body)
        return FakeComment(len(self._ledger))


class FakeRepo:
    def __init__(self, ledger):
        self._ledger = ledger

    def get_issue(self, number):
        return FakeIssue(self._ledger)


class FakeGithub:
    """Records every comment posted, so a duplicate side effect is visible."""

    def __init__(self, ledger):
        self._ledger = ledger

    def get_repo(self, name):
        return FakeRepo(self._ledger)


def _msg(tool_calls=None, content=""):
    """Shape an object like the LiteLLM response `agent_runner` reads."""
    calls = [
        types.SimpleNamespace(
            id=f"call_{i}",
            function=types.SimpleNamespace(name=name, arguments=json.dumps(args)),
        )
        for i, (name, args) in enumerate(tool_calls or [])
    ]
    message = types.SimpleNamespace(content=content, tool_calls=calls or None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


COMMENT_ARGS = {"repo": "o/r", "issue_number": 1, "body": "on it"}

INTEGRATOR_RESULT = {"action": "commented", "result": "posted a comment"}


class ScriptedLLM:
    """Replays a fixed turn sequence per run, so a resumed task takes the same path.

    A resumed agent restarts from message zero — that is exactly the behaviour that makes
    the idempotency cache load-bearing, so the script deliberately repeats itself.
    """

    def __init__(self, turns):
        #: turns[i] is the list of (tool, args) the model emits on its i-th turn of a run.
        self._turns = turns
        self.run = 0
        self.turn = 0

    def next_run(self):
        self.run += 1
        self.turn = 0

    async def __call__(self, model, messages, tools=None, tool_choice=None, **kwargs):
        script = self._turns[self.run]
        emitted = script[min(self.turn, len(script) - 1)]
        self.turn += 1
        return _msg(emitted)


# ── Fixture ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def stack(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "park.db"))
    monkeypatch.setattr(config.settings, "workspace_dir", os.path.join(tmp, "ws"))
    # The park under test must come from an absent credential, not a developer's real one.
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(config.settings, "github_token", "")

    import db as _db
    importlib.reload(_db)
    import agent_runner as _ar
    importlib.reload(_ar)
    monkeypatch.setattr(_ar, "db", _db)

    comments: list[str] = []
    from tools import github_ops
    # `_client` resolves per-user now, and is async. The credential *check* is left real:
    # these tests are precisely about what happens when it says "no credential".
    async def fake_client(args=None, *, as_user=False):
        return FakeGithub(comments)

    monkeypatch.setattr(github_ops, "_client", fake_client)

    asyncio.run(_db.init_db())

    return types.SimpleNamespace(db=_db, ar=_ar, comments=comments, tmp=tmp,
                                 config=config, monkeypatch=monkeypatch)


async def _seed_task(stack, agent="integrator"):
    goal = await stack.db.create_goal("comment on the issue", user_id="usr_legacy_demo")
    tasks = await stack.db.create_tasks(
        [{"id": "t1", "agent": agent, "description": "Comment on issue #1",
          "inputs": {}, "depends_on": []}],
        goal.id, goal.trace_id,
    )
    return goal, tasks[0]


async def _claim_and_run(stack, llm):
    """One turn of the worker's executor loop, without the polling sleep."""
    task = await stack.db.claim_ready_task("worker-test", 300)
    assert task is not None, "expected a READY task to claim"
    stack.monkeypatch.setattr(stack.ar, "acompletion", llm)
    try:
        output = await stack.ar.run(task, task.inputs)
        await stack.db.settle_task(task.id, "DONE", output=output)
        return output
    except stack.ar.WaitingCredentialSignal:
        return WAITING_CREDENTIAL_SENTINEL


async def _waiting_credential(stack, task_id):
    """The key the task is parked on. It is a column, not a `TaskRow` field.

    Worth asserting rather than inferring: per-user OAuth changes this from the env-var
    name `GITHUB_TOKEN` to a per-user `conn:github:{user_id}`, and `resume_credential_tasks`
    matches on it exactly.
    """
    async with stack.db.get_conn() as conn:
        row = await (
            await conn.execute("SELECT waiting_credential FROM tasks WHERE id=?", (task_id,))
        ).fetchone()
    return row["waiting_credential"]


def _grant_token(stack):
    """What `PUT /api/config/keys` does when the user supplies the credential."""
    stack.monkeypatch.setenv("GITHUB_TOKEN", "ghp_granted")


# ── The tests ───────────────────────────────────────────────────────────────────

def test_a_parked_tool_call_is_not_cached_as_success(stack):
    """The park is control flow, not a result, so it must leave no cache entry.

    Cached, it would replay on the very next claim and park the task again — and again,
    on every claim, no matter what the user connects. The goal would be permanently
    unrunnable, and the failure is silent: the task looks like it is politely waiting.
    """
    llm = ScriptedLLM({
        0: [[("github_post_comment", COMMENT_ARGS)]],
        1: [[("github_post_comment", COMMENT_ARGS)],
            [("submit_result", {"result": INTEGRATOR_RESULT})]],
    })

    async def scenario():
        _, task = await _seed_task(stack)

        assert await _claim_and_run(stack, llm) is WAITING_CREDENTIAL_SENTINEL
        parked = await stack.db.get_task(task.id)
        assert parked.status == "WAITING_CREDENTIAL"
        assert await _waiting_credential(stack, task.id) == "GITHUB_TOKEN"
        assert stack.comments == [], "nothing may have been posted while unauthorised"

        # The park must not be sitting in the cache dressed as a completed call.
        cached = await stack.db.get_tool_call_by_idempotency(
            stack.ar._idempotency_key(task.id, "github_post_comment",
                                      json.dumps(COMMENT_ARGS))
        )
        assert cached is None, "a park was cached and will replay forever on resume"

        _grant_token(stack)
        resumed = await stack.db.resume_credential_tasks("GITHUB_TOKEN")
        assert [r["id"] for r in resumed] == [task.id]

        llm.next_run()
        output = await _claim_and_run(stack, llm)

        assert output == INTEGRATOR_RESULT, "the task re-parked instead of finishing"
        assert stack.comments == ["on it"], "the tool never actually ran after the resume"

    asyncio.run(scenario())


def test_resume_replays_cached_tool_calls(stack):
    """Work already done before the park must not be done twice.

    The agent restarts from message zero on resume, so it re-issues every tool call it
    made before parking. Those are cache hits by design: the comment is posted once, and
    the second request is answered from `tool_calls` without the side effect firing.
    """
    llm = ScriptedLLM({
        0: [[("github_post_comment", COMMENT_ARGS)],
            [("wait_webhook", {"description": "wait for CI"})]],
        1: [[("github_post_comment", COMMENT_ARGS)],
            [("submit_result", {"result": INTEGRATOR_RESULT})]],
    })

    async def scenario():
        # The comment succeeds; the park comes from `wait_webhook` on the next turn.
        _grant_token(stack)
        _, task = await _seed_task(stack)

        claimed = await stack.db.claim_ready_task("worker-test", 300)
        stack.monkeypatch.setattr(stack.ar, "acompletion", llm)
        with pytest.raises(stack.ar.WaitingWebhookSignal):
            await stack.ar.run(claimed, claimed.inputs)

        assert stack.comments == ["on it"]
        parked = await stack.db.get_task(task.id)
        assert parked.status == "WAITING_WEBHOOK"

        resumed = await stack.db.resume_webhook_task(parked.wait_token, {"ok": True})
        assert resumed is not None

        llm.next_run()
        output = await _claim_and_run(stack, llm)

        assert output == INTEGRATOR_RESULT
        assert stack.comments == ["on it"], (
            "the comment was posted twice — the resumed task missed the idempotency cache"
        )

    asyncio.run(scenario())


def test_parking_does_not_burn_retries(stack):
    """Waiting for a human is not a failure, and must not spend the retry budget.

    `attempt_count` still counts claims — it is what makes lease reclaim crash-safe — so
    it climbs with every resume. `failure_count` is the budget, and only a real exception
    moves it.
    """
    llm = ScriptedLLM({0: [[("github_post_comment", COMMENT_ARGS)]]})

    async def scenario():
        _, task = await _seed_task(stack)

        for _ in range(3):
            assert await _claim_and_run(stack, llm) is WAITING_CREDENTIAL_SENTINEL
            await stack.db.resume_credential_tasks("GITHUB_TOKEN")

        parked = await stack.db.get_task(task.id)
        assert parked.attempt_count == 3, "claims are still counted"
        assert parked.failure_count == 0, "parking spent a retry it should not have"
        assert parked.failure_count < parked.max_attempts, "no budget left for a real failure"
        assert parked.status == "READY"

    asyncio.run(scenario())


def test_a_goal_waiting_on_the_user_is_not_swept_away(stack):
    """A parked task is progress. The orphan sweeper used to disagree.

    `find_orphaned_goals` feeds a loop that marks goals FAILED with "All tasks failed — no
    progress possible". A goal parked on "connect your GitHub account" met that condition,
    so the goal died while the prompt was still on screen.
    """
    llm = ScriptedLLM({0: [[("github_post_comment", COMMENT_ARGS)]]})

    async def scenario():
        goal, task = await _seed_task(stack)
        await stack.db.update_goal_status(goal.id, "RUNNING")
        await stack.db.set_goal_plan(goal.id, json.dumps({"terminal": task.id}), task.id)

        assert await _claim_and_run(stack, llm) is WAITING_CREDENTIAL_SENTINEL
        assert (await stack.db.get_task(task.id)).status == "WAITING_CREDENTIAL"

        orphans = await stack.db.find_orphaned_goals()
        assert goal.id not in [o["id"] for o in orphans], (
            "a goal waiting on the user was about to be marked FAILED"
        )

    asyncio.run(scenario())
