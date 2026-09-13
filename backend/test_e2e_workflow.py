"""End-to-end workflow test: goal → plan → agents → tools → proofs → chain → verify.

Everything here is the REAL production code path — real orchestrator, real DAG validation,
real task claiming, real agent_runner tool loop, real interpolation between tasks, real
economy, real outbox, real EVM. The *only* thing stubbed is `llm.acompletion`, because a
language model is a non-deterministic third-party service, not part of the wiring under test.

This is what proves "Mergit actually does the job it is asked to do" without API keys.
"""
import asyncio
import importlib
import json
import os
import tempfile
import types

import pytest


# ── Fake LLM ────────────────────────────────────────────────────────────────────

def _msg(tool_calls=None, content=""):
    """Shape an object like the LiteLLM response the code reads."""
    calls = []
    for i, (name, args) in enumerate(tool_calls or []):
        calls.append(types.SimpleNamespace(
            id=f"call_{i}",
            function=types.SimpleNamespace(name=name, arguments=json.dumps(args)),
        ))
    message = types.SimpleNamespace(content=content, tool_calls=calls or None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


#: The DAG the orchestrator is expected to return for our goal.
PLAN = {
    "tasks": [
        {"id": "t1", "agent": "researcher",
         "description": "Find out what the README documents",
         "inputs": {"query": "mergit readme"}, "depends_on": []},
        {"id": "t2", "agent": "writer",
         "description": "Summarise the findings",
         "inputs": {"source": "{{t1.output.summary}}"}, "depends_on": ["t1"]},
    ],
    "terminal": "t2",
    "reasoning": "Research the README, then summarise it.",
}

AGENT_OUTPUTS = {
    "researcher": {"summary": "The README documents setup, dev and deploy.",
                   "key_points": ["setup", "dev", "deploy"], "sources": ["README.md"]},
    "writer": {"title": "README summary",
               "text": "Mergit's README covers setup, development and deployment."},
}


def role_from_tools(tool_names: set[str]) -> str | None:
    """Identify which agent is calling from the toolset it was given.

    The system prompts do not name their own role ("You are a research agent…"), so the
    allowed-tools set from AGENT_REGISTRY is the authoritative discriminator.
    """
    from agent_registry import AGENT_REGISTRY

    for role, config in AGENT_REGISTRY.items():
        if set(config["allowed_tools"]) | {"submit_result"} == tool_names:
            return role
    return None


class FakeLLM:
    """Records every call so the test can assert on what the pipeline actually asked for."""

    def __init__(self):
        self.calls = []

    async def __call__(self, model, messages, tools=None, tool_choice=None, **kwargs):
        self.calls.append({"model": model, "messages": messages, "tools": tools})

        tool_names = {t["function"]["name"] for t in (tools or [])}

        # The orchestrator is the only caller offering the planning tool.
        if "submit_plan" in tool_names:
            return _msg([("submit_plan", PLAN)])

        role = role_from_tools(tool_names)
        assert role in AGENT_OUTPUTS, f"unexpected agent invoked with tools {tool_names}"
        return _msg([("submit_result", {"result": AGENT_OUTPUTS[role]})])


# ── Fixture ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def stack(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "e2e.db"))
    monkeypatch.setattr(config.settings, "workspace_dir", os.path.join(tmp, "ws"))

    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)

    fake = FakeLLM()
    import llm
    monkeypatch.setattr(llm, "acompletion", fake)
    import orchestrator as _orch
    importlib.reload(_orch)
    monkeypatch.setattr(_orch, "acompletion", fake)
    import agent_runner as _ar
    importlib.reload(_ar)
    monkeypatch.setattr(_ar, "acompletion", fake)

    import worker as _worker
    importlib.reload(_worker)

    from chain.client import ChainClient, set_client
    from chain.deployer import deploy_all
    from chain.provider import LocalEvmProvider

    provider = LocalEvmProvider()
    client = ChainClient(provider, deploy_all(provider))
    set_client(client)

    import chain_worker as _cw
    importlib.reload(_cw)

    asyncio.run(_db.init_db())
    asyncio.run(_ec.seed_passports())

    return types.SimpleNamespace(db=_db, economy=_ec, worker=_worker, orch=_orch,
                                 chain_worker=_cw, client=client, llm=fake)


def _agent_calls(stack, role=None):
    """LLM calls made by agents, not the orchestrator, identified by their toolset."""
    calls = []
    for call in stack.llm.calls:
        names = {t["function"]["name"] for t in (call["tools"] or [])}
        if "submit_plan" in names:
            continue
        called_role = role_from_tools(names)
        if role is None or called_role == role:
            calls.append({**call, "role": called_role})
    return calls


async def _drive(stack, goal_text="Summarise the Mergit README"):
    """Run a goal the way the worker loops would, without the polling sleeps."""
    goal = await stack.db.create_goal(goal_text, user_id="usr_legacy_demo")

    claimed = await stack.db.claim_new_goal()
    assert claimed is not None and claimed.id == goal.id
    await stack.worker._plan_goal(claimed)

    # Execute tasks until none are left ready — same claim/execute path the loop uses.
    for _ in range(20):
        task = await stack.db.claim_ready_task("test-worker", 300)
        if task is None:
            break
        await stack.worker._execute_task(task)

    return await stack.db.get_goal(goal.id)


# ── The workflow itself ─────────────────────────────────────────────────────────

def test_goal_is_planned_into_a_real_task_dag(stack):
    async def go():
        goal = await _drive(stack)
        tasks = await stack.db.list_goal_tasks(goal.id)

        assert len(tasks) == 2, "orchestrator must persist both planned tasks"
        agents = {t.agent_name for t in tasks}
        assert agents == {"researcher", "writer"}

        # Dependencies survived the id-prefixing rewrite.
        writer = next(t for t in tasks if t.agent_name == "writer")
        researcher = next(t for t in tasks if t.agent_name == "researcher")
        assert writer.depends_on == [researcher.id]
        assert researcher.id.startswith(goal.id[:8])

    asyncio.run(go())


def test_goal_runs_to_completion(stack):
    async def go():
        goal = await _drive(stack)
        assert goal.status == "COMPLETED", f"goal ended {goal.status}: {goal.error}"

        tasks = await stack.db.list_goal_tasks(goal.id)
        assert all(t.status == "DONE" for t in tasks), [(t.agent_name, t.status) for t in tasks]

        # The terminal task's output became the goal's output.
        assert goal.output == AGENT_OUTPUTS["writer"]

    asyncio.run(go())


def test_output_of_one_task_feeds_the_next(stack):
    """Interpolation is what makes a DAG more than a list — prove it actually resolved."""
    async def go():
        await _drive(stack)

        writer_calls = _agent_calls(stack, "writer")
        assert writer_calls, "the writer agent was never invoked"

        user_message = writer_calls[0]["messages"][1]["content"]
        assert AGENT_OUTPUTS["researcher"]["summary"] in user_message, (
            "the writer did not receive the researcher's real output — "
            "{{t1.output.summary}} was not resolved"
        )
        assert "{{" not in user_message, "an unresolved template leaked into the prompt"

    asyncio.run(go())


def test_each_agent_only_gets_its_own_tools(stack):
    async def go():
        await _drive(stack)

        seen = set()
        for call in _agent_calls(stack):
            names = {t["function"]["name"] for t in (call["tools"] or [])}
            seen.add(call["role"])
            if call["role"] == "researcher":
                assert "web_search" in names
                assert "github_pr" not in names, "researcher must not be able to open PRs"
            if call["role"] == "writer":
                assert "file_ops" in names
                assert "code_exec" not in names, "writer must not be able to execute code"
        assert seen == {"researcher", "writer"}, f"unexpected agents invoked: {seen}"

    asyncio.run(go())


# ── Where the workflow meets the chain ──────────────────────────────────────────

def test_every_completed_task_mints_a_verifiable_proof(stack):
    async def go():
        goal = await _drive(stack)
        tasks = await stack.db.list_goal_tasks(goal.id)

        proofs = await stack.db.list_proofs()
        assert len(proofs) == len(tasks), "one proof per completed task"

        assert await stack.chain_worker.submit_batch(limit=10) == len(tasks)

        for task in tasks:
            entry = await stack.db.get_outbox_entry(task.id)
            assert entry["status"] == "confirmed"
            assert entry["tx_hash"].startswith("0x") and len(entry["tx_hash"]) == 66

            # The on-chain hash is the hash of this agent's real output.
            expected = stack.economy.result_hash(task.output)
            assert stack.client.verify(task.id, expected) is True

    asyncio.run(go())


def test_agent_reputation_moves_after_real_work(stack):
    async def go():
        await _drive(stack)

        for role in ("researcher", "writer"):
            rep = await stack.db.get_reputation(role)
            assert rep is not None, f"{role} has no reputation record"
            assert rep["composite"] > 0
            assert rep["success_rate"] == 1.0
            assert rep["badge"] in ("Gold", "Silver", "Bronze")

    asyncio.run(go())


def test_a_second_goal_reuses_the_same_agent_passports(stack):
    """Identity must persist across goals — that is the whole point of a passport."""
    async def go():
        await _drive(stack, "first goal")
        await stack.chain_worker.submit_batch(limit=10)
        first = stack.client.ensure_passport("researcher")

        await _drive(stack, "second goal")
        await stack.chain_worker.submit_batch(limit=10)
        second = stack.client.ensure_passport("researcher")

        assert first == second, "the researcher was issued a second passport"

        passport = stack.client._contracts["AgentPassport"].functions.getPassport(first).call()
        assert passport[4] == 2, "on-chain tasksCompleted should count both goals"

    asyncio.run(go())
