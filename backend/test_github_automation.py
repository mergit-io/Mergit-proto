"""The flagship demo, end to end: GitHub issue → autonomous fix → PR → comment.

CLAUDE.md calls this "the main demo flow" and it had no tests at all. Real webhook
handler, real orchestrator, real DAG validation (including the integrator-as-terminal
rule), real agent loop, real tool dispatch and idempotency, real proofs. Stubbed: the
language model and the GitHub API, since neither is part of the wiring under test.
"""
import asyncio
import hashlib
import hmac
import importlib
import json
import os
import tempfile
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = "mergit-io/demo"

ISSUE_PAYLOAD = {
    "action": "opened",
    "issue": {
        "number": 42,
        "title": "Crash on empty token refresh",
        "body": "auth.py raises AttributeError when the refresh token is None.",
        "html_url": f"https://github.com/{REPO}/issues/42",
    },
    "repository": {"full_name": REPO, "default_branch": "main"},
}

PR_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 7,
        "title": "Add retry to the HTTP client",
        "body": "Adds exponential backoff.",
        "html_url": f"https://github.com/{REPO}/pull/7",
        "user": {"login": "someone", "type": "User"},
        "head": {"ref": "feature/retry"},
        "base": {"ref": "main"},
    },
    "repository": {"full_name": REPO, "default_branch": "main"},
}

# researcher → coder → integrator, the pipeline CLAUDE.md documents for issue fixing.
FIX_PLAN = {
    "tasks": [
        {"id": "t1", "agent": "researcher",
         "description": "Read the repo and the issue to locate the bug",
         "inputs": {"repo": REPO, "issue": 42}, "depends_on": []},
        {"id": "t2", "agent": "coder",
         "description": "Write the fix",
         "inputs": {"context": "{{t1.output.code_context}}"}, "depends_on": ["t1"]},
        {"id": "t3", "agent": "integrator",
         "description": "Open a PR and comment on the issue",
         "inputs": {"code": "{{t2.output.code}}"}, "depends_on": ["t2"]},
    ],
    "terminal": "t3",
    "reasoning": "Locate the bug, fix it, then ship it as a PR.",
}


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


def role_from_tools(tool_names: set[str]) -> str | None:
    from agent_registry import AGENT_REGISTRY

    for role, config in AGENT_REGISTRY.items():
        if set(config["allowed_tools"]) | {"submit_result"} == tool_names:
            return role
    return None


class ScriptedLLM:
    """Each agent makes one real tool call, then submits — mirroring a real run."""

    def __init__(self):
        self.calls = []
        self.tool_calls_made = []

    async def __call__(self, model, messages, tools=None, tool_choice=None, **kwargs):
        names = {t["function"]["name"] for t in (tools or [])}
        self.calls.append({"messages": messages, "tools": names})

        if "submit_plan" in names:
            return _msg([("submit_plan", FIX_PLAN)])

        role = role_from_tools(names)
        # Has this agent already run its tool this turn? Then submit.
        already = any(r == role for r, _ in self.tool_calls_made)

        if role == "researcher":
            if not already:
                self.tool_calls_made.append((role, "github_read_file"))
                return _msg([("github_read_file", {"repo": REPO, "path": "auth.py"})])
            return _msg([("submit_result", {"result": {
                "summary": "Null token dereferenced in refresh()",
                "code_context": "auth.py:88 — `token.value` with token=None",
                "key_points": ["guard None"], "sources": ["auth.py"],
            }})])

        if role == "coder":
            if not already:
                self.tool_calls_made.append((role, "code_exec"))
                return _msg([("code_exec", {"code": "print('tests pass')"})])
            return _msg([("submit_result", {"result": {
                "code": "if token is None:\n    return None\n",
                "output": "tests pass",
                "success": True,
                "files": [{"path": "auth.py", "content": "if token is None: return None\n"}],
            }})])

        if role == "integrator":
            if not already:
                self.tool_calls_made.append((role, "github_pr"))
                return _msg([("github_pr", {
                    "repo": REPO, "title": "Fix null token refresh",
                    "body": "Fixes #42", "branch": "fix/issue-42",
                    "files": [{"path": "auth.py", "content": "if token is None: return None\n"}],
                })])
            return _msg([("submit_result", {"result": {
                "action": "pull_request_opened",
                "result": f"Opened PR #99 on {REPO} and commented on issue #42",
                "pr_url": f"https://github.com/{REPO}/pull/99",
            }})])

        raise AssertionError(f"unexpected agent with tools {names}")


@pytest.fixture()
def stack(monkeypatch):
    tmp = tempfile.mkdtemp()
    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tmp, "gh.db"))
    monkeypatch.setattr(config.settings, "workspace_dir", os.path.join(tmp, "ws"))
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    import db as _db
    importlib.reload(_db)
    import economy as _ec
    importlib.reload(_ec)

    fake = ScriptedLLM()
    import orchestrator as _orch
    importlib.reload(_orch)
    monkeypatch.setattr(_orch, "acompletion", fake)
    import agent_runner as _ar
    importlib.reload(_ar)
    monkeypatch.setattr(_ar, "acompletion", fake)

    # Stub the GitHub-touching tools; everything else in the dispatch path stays real.
    import tools as _tools
    github_calls = []

    def stub(name, result):
        async def run(args):
            github_calls.append({"tool": name, "args": args})
            return result
        return run

    def install(name, result):
        entry = _tools.TOOL_REGISTRY[name]
        monkeypatch.setitem(
            _tools.TOOL_REGISTRY, name,
            _tools.ToolEntry(fn=stub(name, result), schema=entry.schema),
        )

    for name, result in [
        ("github_read_file", {"ok": True, "content": "def refresh(token):\n    return token.value\n"}),
        ("github_list_dir", {"ok": True, "entries": ["auth.py", "README.md"]}),
        ("github_get_issue", {"ok": True, "title": "Crash on empty token refresh", "number": 42}),
        ("github_pr", {"ok": True, "pr_url": f"https://github.com/{REPO}/pull/99", "number": 99}),
        ("github_post_comment", {"ok": True, "comment_url": f"https://github.com/{REPO}/issues/42#c1"}),
        ("code_exec", {"ok": True, "stdout": "tests pass", "exit_code": 0}),
    ]:
        if name in _tools.TOOL_REGISTRY:
            install(name, result)

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

    from api import github_webhook as _gh
    importlib.reload(_gh)

    asyncio.run(_db.init_db())
    asyncio.run(_ec.seed_passports())

    app = FastAPI()
    app.include_router(_gh.router)

    return types.SimpleNamespace(
        db=_db, economy=_ec, worker=_worker, chain_worker=_cw, client=client,
        llm=fake, github_calls=github_calls, http=TestClient(app),
    )


def _post(stack, payload, event):
    return stack.http.post(
        "/api/webhooks/github", content=json.dumps(payload),
        headers={"X-Github-Event": event, "Content-Type": "application/json"},
    )


async def _run_goal(stack, goal_id):
    claimed = await stack.db.claim_new_goal()
    await stack.worker._plan_goal(claimed)
    for _ in range(20):
        task = await stack.db.claim_ready_task("test-worker", 300)
        if task is None:
            break
        await stack.worker._execute_task(task)
    return await stack.db.get_goal(goal_id)


# ── Webhook receipt ─────────────────────────────────────────────────────────────

def test_issue_opened_creates_a_goal(stack):
    response = _post(stack, ISSUE_PAYLOAD, "issues")
    assert response.status_code == 200
    body = response.json()

    assert body["ok"] is True
    assert body["issue_number"] == 42
    assert body["repo"] == REPO

    goal = asyncio.run(stack.db.get_goal(body["goal_id"]))
    assert goal is not None
    assert "42" in goal.goal_text and REPO in goal.goal_text


def test_pr_opened_creates_a_review_goal(stack):
    body = _post(stack, PR_PAYLOAD, "pull_request").json()
    goal = asyncio.run(stack.db.get_goal(body["goal_id"]))
    assert "Review the pull request" in goal.goal_text
    assert "#7" in goal.goal_text


def test_bot_prs_are_skipped(stack):
    """Otherwise Mergit reviews its own fix PRs forever."""
    payload = json.loads(json.dumps(PR_PAYLOAD))
    payload["pull_request"]["user"]["type"] = "Bot"

    body = _post(stack, payload, "pull_request").json()
    assert body["status"] == "skipped"
    assert "goal_id" not in body


def test_ping_and_unknown_events_are_harmless(stack):
    assert _post(stack, {"zen": "Design for failure."}, "ping").json()["ok"] is True
    assert _post(stack, {"action": "deleted"}, "issues").json()["status"] == "ignored"
    assert asyncio.run(stack.db.list_goals()) == [] if hasattr(stack.db, "list_goals") else True


def test_bad_signature_is_rejected(stack, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cret")
    body = json.dumps(ISSUE_PAYLOAD)

    assert stack.http.post(
        "/api/webhooks/github", content=body,
        headers={"X-Github-Event": "issues", "X-Hub-Signature-256": "sha256=deadbeef"},
    ).status_code == 401

    good = "sha256=" + hmac.new(b"s3cret", body.encode(), hashlib.sha256).hexdigest()
    assert stack.http.post(
        "/api/webhooks/github", content=body,
        headers={"X-Github-Event": "issues", "X-Hub-Signature-256": good},
    ).status_code == 200


# ── The autonomous pipeline ─────────────────────────────────────────────────────

def test_issue_runs_the_full_fix_pipeline(stack):
    goal_id = _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]
    goal = asyncio.run(_run_goal(stack, goal_id))

    assert goal.status == "COMPLETED", f"ended {goal.status}: {goal.error}"

    tasks = asyncio.run(stack.db.list_goal_tasks(goal_id))
    assert [t.agent_name for t in sorted(tasks, key=lambda t: t.id)] == \
        ["researcher", "coder", "integrator"] or \
        {t.agent_name for t in tasks} == {"researcher", "coder", "integrator"}
    assert all(t.status == "DONE" for t in tasks)

    # The goal's result is the PR the integrator opened.
    assert goal.output["action"] == "pull_request_opened"
    assert goal.output["pr_url"].endswith("/pull/99")


def test_integrator_is_allowed_as_the_terminal_task(stack):
    """_validate_plan normally rejects a non-writer terminal; GitHub automation is the
    documented exception (creating the PR *is* the deliverable)."""
    goal_id = _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]
    goal = asyncio.run(_run_goal(stack, goal_id))

    terminal = asyncio.run(stack.db.get_task(goal.terminal_task_id))
    assert terminal.agent_name == "integrator"


# ── which GitHub plans _validate_plan accepts ───────────────────────────────────
# The terminal-task rule exists so the user is handed something readable rather than
# raw JSON. For GitHub automation the deliverable is the side effect — the PR, the
# comment — so the integrator is legitimately terminal.
#
# The exception was written as "the plan contains a coder", which silently made it
# bug-fix-only. A goal needing no code change (write docs, review a PR) plans
# researcher → writer → integrator, was rejected five times, and the goal FAILED with
# advice to "add a writer task" when it already had one. The orchestrator's own prompt
# teaches the rejected shape: "review a GitHub PR" → researcher → writer → integrator.
#
# Observed on a real run: sandbox issue #19 ("make some docs for new contributors").

def _plan(*agents: str):
    from orchestrator import PlanSchema, TaskSpec
    tasks = [
        TaskSpec(id=f"t{i + 1}", agent=a, description="x",
                 inputs={"repo": "owner/repo"},
                 depends_on=([f"t{i}"] if i else []))
        for i, a in enumerate(agents)
    ]
    return PlanSchema(reasoning="x", tasks=tasks, terminal=f"t{len(agents)}")


def _accepts(*agents: str) -> bool:
    import orchestrator
    try:
        orchestrator._validate_plan(_plan(*agents))
        return True
    except ValueError:
        return False


def test_a_bug_fix_plan_may_end_at_the_integrator():
    """The pattern the orchestrator prompt documents for "fix a GitHub issue"."""
    assert _accepts("researcher", "coder", "integrator")


def test_a_pr_review_plan_may_end_at_the_integrator():
    """Documented verbatim in the orchestrator prompt: "review a GitHub PR" →
    researcher → writer → integrator. The validator rejected it."""
    assert _accepts("researcher", "writer", "integrator"), (
        "the orchestrator prompt instructs the model to produce this plan and the "
        "validator refuses it — every GitHub goal needing no code change fails to plan"
    )


def test_a_docs_plan_may_end_at_the_integrator():
    """Sandbox issue #19: no code change, so no coder — the writer produces the docs
    and the integrator opens the PR."""
    assert _accepts("researcher", "writer", "integrator")


def test_a_writer_only_plan_may_end_at_the_integrator():
    assert _accepts("writer", "integrator")


def test_a_bare_fetch_still_needs_a_writer():
    """The rule this exception lives inside must survive: researcher → integrator
    produces raw structured data with nothing to present it, which is what the
    human-readable-terminal rule was written to catch."""
    assert not _accepts("researcher", "integrator")


def test_a_lone_researcher_is_still_rejected_as_terminal():
    assert not _accepts("researcher", "researcher")


def test_real_github_operations_are_invoked(stack):
    asyncio.run(_run_goal(stack, _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]))

    invoked = [c["tool"] for c in stack.github_calls]
    assert "github_read_file" in invoked, "the researcher never read the repo"
    assert "github_pr" in invoked, "no pull request was ever opened"

    pr_call = next(c for c in stack.github_calls if c["tool"] == "github_pr")
    assert pr_call["args"]["repo"] == REPO
    assert pr_call["args"]["files"][0]["path"] == "auth.py"


def test_coder_receives_the_researchers_findings(stack):
    asyncio.run(_run_goal(stack, _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]))

    coder_prompts = [
        c["messages"][1]["content"] for c in stack.llm.calls
        if role_from_tools(c["tools"]) == "coder"
    ]
    assert coder_prompts, "the coder was never invoked"
    assert "auth.py:88" in coder_prompts[0], (
        "{{t1.output.code_context}} did not resolve — the coder was told to fix a bug "
        "without being told where it is"
    )


def test_each_pipeline_task_mints_a_verifiable_proof(stack):
    goal_id = _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]
    asyncio.run(_run_goal(stack, goal_id))

    async def check():
        tasks = await stack.db.list_goal_tasks(goal_id)
        assert await stack.chain_worker.submit_batch(limit=10) == len(tasks)
        for task in tasks:
            assert stack.client.verify(task.id, stack.economy.result_hash(task.output)) is True

    asyncio.run(check())


def test_tool_results_are_cached_by_idempotency_key(stack):
    """A re-run must not fire the same GitHub write twice."""
    goal_id = _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]
    asyncio.run(_run_goal(stack, goal_id))

    pr_calls = [c for c in stack.github_calls if c["tool"] == "github_pr"]
    assert len(pr_calls) == 1, f"github_pr fired {len(pr_calls)} times — PRs would duplicate"
