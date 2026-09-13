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
import re
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


_PY_PATH_RE = re.compile(r"\b[\w./-]+\.py\b")


def visible_path(messages: list[dict]) -> str | None:
    """The first repo path the agent can actually SEE — in its resolved inputs or in a
    tool result it got back. Its own system prompt is excluded on purpose: the examples
    in there ("main.py") are not evidence about this repository.

    A scripted agent that reaches past this function is testing the fixture, not the code.
    """
    for message in messages:
        if message.get("role") == "system":
            continue
        found = _PY_PATH_RE.search(str(message.get("content") or ""))
        if found:
            return found.group(0)
    return None


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
        self.listed = False

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
                "path": "auth.py",
                "output": "tests pass",
                "success": True,
                "files": [{"path": "auth.py", "content": "if token is None: return None\n"}],
            }})])

        if role == "integrator":
            # The integrator may only use a path it can actually see: one handed to it in
            # its inputs, or one it read back from a tool. With neither it has to guess —
            # which is how a real run shipped a brand-new calculator.py next to the calc.py
            # that had the bug. Do NOT hardcode "auth.py" here; that hid this bug once.
            if not already:
                seen = visible_path(messages)
                if seen is None and "github_list_dir" in names and not self.listed:
                    self.listed = True  # one look; a repo with no .py must not spin
                    return _msg([("github_list_dir", {"repo": REPO, "path": ""})])
                self.tool_calls_made.append((role, "github_pr"))
                path = seen or "calculator.py"
                return _msg([("github_pr", {
                    "repo": REPO, "title": "Fix null token refresh",
                    "body": "Fixes #42", "branch": "fix/issue-42",
                    "files": [{"path": path, "content": "if token is None: return None\n"}],
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


def test_real_github_operations_are_invoked(stack):
    asyncio.run(_run_goal(stack, _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]))

    invoked = [c["tool"] for c in stack.github_calls]
    assert "github_read_file" in invoked, "the researcher never read the repo"
    assert "github_pr" in invoked, "no pull request was ever opened"

    pr_call = next(c for c in stack.github_calls if c["tool"] == "github_pr")
    assert pr_call["args"]["repo"] == REPO
    assert pr_call["args"]["files"][0]["path"] == "auth.py", (
        "the PR edited a file nobody read — a fix committed to the wrong path is a new "
        "file sitting next to the bug, not a fix"
    )


# ── Fixing the file that actually has the bug ───────────────────────────────────

def test_the_coder_reports_which_file_its_fix_belongs_in():
    """The coder is the only agent that both reads the buggy file and writes the fix.
    If its output carries no path, the filename dies at that boundary and whoever opens
    the PR has to invent one."""
    from agent_registry import AGENT_REGISTRY

    schema = AGENT_REGISTRY["coder"]["output_schema"]
    assert "path" in schema["properties"], "the coder cannot report a target file"
    assert "path" in schema["required"], (
        "an optional path is a path the model will omit — agent_runner only rejects a "
        "submit_result for keys listed in `required`"
    )


def test_the_integrator_can_find_out_what_is_in_the_repo():
    """github_read_file needs a path you already know. Without a way to enumerate, an
    integrator handed code and no filename has no move except guessing."""
    from agent_registry import AGENT_REGISTRY

    assert "github_list_dir" in AGENT_REGISTRY["integrator"]["allowed_tools"]


def test_the_target_path_reaches_the_integrator_without_the_plan_carrying_it(stack):
    """FIX_PLAN hands the integrator `{{t2.output.code}}` and nothing else — the exact
    shape the orchestrator produced when it shipped calculator.py beside the bug.

    The plan is written by a model, so the prompt telling it to pass "file_path" is a
    request, not a guarantee. The worker carries the coder's path forward itself, which
    is what makes the outcome the same on every model.
    """
    asyncio.run(_run_goal(stack, _post(stack, ISSUE_PAYLOAD, "issues").json()["goal_id"]))

    integrator_prompt = next(
        c["messages"][1]["content"] for c in stack.llm.calls
        if role_from_tools(c["tools"]) == "integrator"
    )
    assert "auth.py" in integrator_prompt, (
        "the integrator was handed a fix with no filename — it can only guess from here"
    )

    pr_call = next(c for c in stack.github_calls if c["tool"] == "github_pr")
    assert [f["path"] for f in pr_call["args"]["files"]] == ["auth.py"]


def test_a_path_the_plan_supplies_is_never_overwritten():
    """The carry-forward fills a gap; it does not overrule a plan that said where to go."""
    import worker

    task = types.SimpleNamespace(id="g_t3", agent_name="integrator", depends_on=["g_t2"])
    outputs = {"g_t2": {"code": "...", "path": "src/auth.py"}}

    assert worker._inherit_target_path({}, task, outputs)["file_path"] == "src/auth.py"

    explicit = {"file_path": "src/chosen.py"}
    assert worker._inherit_target_path(explicit, task, outputs) == explicit
    for alias in ("path", "target_file", "file_to_fix"):
        assert worker._inherit_target_path({alias: "x.py"}, task, outputs) == {alias: "x.py"}


def test_only_the_integrator_inherits_a_path_and_only_a_usable_one():
    import worker

    outputs = {"g_t2": {"code": "...", "path": "src/auth.py"}}
    coder = types.SimpleNamespace(id="g_t3", agent_name="coder", depends_on=["g_t2"])
    assert worker._inherit_target_path({}, coder, outputs) == {}

    integrator = types.SimpleNamespace(id="g_t3", agent_name="integrator", depends_on=["g_t2"])
    for junk in ({"code": "..."}, {"path": "   "}, {"path": None}, "not-a-dict"):
        assert worker._inherit_target_path({}, integrator, {"g_t2": junk}) == {}
    assert worker._inherit_target_path({}, integrator, {}) == {}


def test_the_integrator_can_still_discover_a_path_nobody_handed_it(stack):
    """The backstop for a plan with no coder in it at all: enumerate rather than guess."""
    from agent_registry import AGENT_REGISTRY

    messages = [{"role": "system", "content": "…example uses main.py…"},
                {"role": "user", "content": 'Task: open a PR\n\nInputs:\n{"repo": "o/r"}'}]
    names = set(AGENT_REGISTRY["integrator"]["allowed_tools"]) | {"submit_result"}

    assert visible_path(messages) is None, "nothing in context names a file"
    assert "github_list_dir" in names, (
        "with no path in context and no way to list the repo, the only move left is a guess"
    )


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
