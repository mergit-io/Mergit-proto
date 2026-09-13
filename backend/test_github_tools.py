"""The GitHub write surface: merge guard, PR diffs, reviews, issues, and PR creation.

`test_github_automation.py` covers the wiring — webhook to DAG to tool dispatch — with
every GitHub tool stubbed. This file covers what those stubs stand in for: the decisions
each tool makes when GitHub answers. PyGithub is faked at the client boundary, so the
tool bodies under test are the real ones.
"""
import asyncio
import sys

import pytest
from github import GithubException

import tools.github_ops as ops
import tools.github_pr  # noqa: F401  — imported for the side effect of registering the module

# `tools/__init__.py` does `from tools.github_pr import github_pr`, which rebinds the
# attribute `tools.github_pr` from the module to the function. sys.modules still has
# the module itself, which is what needs patching.
gpr = sys.modules["tools.github_pr"]


# ── Fake PyGithub ────────────────────────────────────────────────────────────────

def _gh_error(status=422, message="unprocessable"):
    return GithubException(status, {"message": message}, None)


class FakeUser:
    def __init__(self, login="agentbot"):
        self.login = login


class FakeReview:
    def __init__(self, user, state, id=1):
        self.user, self.state, self.id = FakeUser(user), state, id


class FakeCheckRun:
    def __init__(self, name, status="completed", conclusion="success"):
        self.name, self.status, self.conclusion = name, status, conclusion


class FakeMergeResult:
    def __init__(self, merged=True, sha="deadbeef", message="Pull Request successfully merged"):
        self.merged, self.sha, self.message = merged, sha, message


class FakeFile:
    def __init__(self, filename, patch="@@ -1 +1 @@\n-old\n+new", status="modified",
                 additions=1, deletions=1):
        self.filename, self.patch, self.status = filename, patch, status
        self.additions, self.deletions = additions, deletions
        self.changes = additions + deletions
        self.previous_filename = None


class FakePR:
    def __init__(self, number=7, state="open", merged=False, mergeable=True,
                 mergeable_state="clean", draft=False, reviews=(), files=(),
                 head="fix/bug", base="main", author="agentbot"):
        self.number, self.state, self.merged = number, state, merged
        self.mergeable, self.mergeable_state, self.draft = mergeable, mergeable_state, draft
        self._reviews = list(reviews)
        self._files = list(files) or [FakeFile("calc.py")]
        self.head = type("H", (), {"ref": head, "sha": "headsha", "repo": None})()
        self.base = type("B", (), {"ref": base})()
        self.user = FakeUser(author)
        self.title, self.body = "fix: guard empty input", "Closes #1"
        self.commits, self.additions, self.deletions, self.changed_files = 1, 1, 1, 1
        self.labels = []
        self.html_url = f"https://github.com/o/r/pull/{number}"
        self.merge_commit_sha = "mergedsha"
        self.merge_calls = []
        self.review_calls = []
        self.self_review_blocked = False

    def get_reviews(self):
        return self._reviews

    def get_files(self):
        return self._files

    def merge(self, **kwargs):
        self.merge_calls.append(kwargs)
        return FakeMergeResult()

    def create_review(self, body, event):
        if self.self_review_blocked and event in ("APPROVE", "REQUEST_CHANGES"):
            raise _gh_error(422, "Can not approve your own pull request")
        self.review_calls.append(event)
        return type("R", (), {"id": 55, "state": event})()


class FakeRepo:
    def __init__(self, full_name="o/r", default_branch="main", push=True, pr=None,
                 check_runs=(), branches=("main",)):
        self.full_name, self.default_branch = full_name, default_branch
        self.name = full_name.split("/")[-1]
        self.owner = FakeUser(full_name.split("/")[0])
        self.permissions = type("P", (), {"push": push})()
        self._pr = pr or FakePR()
        self._check_runs = list(check_runs)
        self._branches = set(branches)
        self.created_refs, self.created_files, self.updated_files = [], [], []
        self.created_pulls, self.created_issues = [], []
        self.open_pulls = []
        self.create_pull_error = None

    # reads
    def get_pull(self, n):
        return self._pr

    def get_branch(self, name):
        if name not in self._branches:
            raise _gh_error(404, "Branch not found")
        return type("B", (), {"commit": type("C", (), {"sha": f"sha-{name}"})()})()

    def get_commit(self, sha):
        runs = self._check_runs
        return type("C", (), {"get_check_runs": lambda self=None: runs})()

    def get_contents(self, path, ref=None):
        raise _gh_error(404, "Not Found")

    def get_pulls(self, state="open", base=None, head=None):
        return [p for p in self.open_pulls
                if (base is None or p.base.ref == base)]

    # writes
    def create_git_ref(self, ref, sha):
        self.created_refs.append((ref, sha))
        self._branches.add(ref.removeprefix("refs/heads/"))

    def create_file(self, path, msg, content, branch=None):
        self.created_files.append((path, branch))

    def update_file(self, path, msg, content, sha, branch=None):
        self.updated_files.append((path, branch))

    def create_pull(self, title, body, head, base):
        if self.create_pull_error:
            raise self.create_pull_error
        self.created_pulls.append({"title": title, "head": head, "base": base})
        return self._pr

    def create_issue(self, title, body, labels):
        issue = type("I", (), {"number": 12, "html_url": "https://github.com/o/r/issues/12",
                               "title": title, "state": "open"})()
        self.created_issues.append(title)
        return issue


class FakeGithub:
    def __init__(self, repos, login="agentbot"):
        self._repos, self._login = repos, login

    def get_repo(self, name):
        if name not in self._repos:
            raise _gh_error(404, f"no repo {name}")
        return self._repos[name]

    def get_user(self):
        u = FakeUser(self._login)
        u.create_fork = lambda upstream: None
        return u


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_fake")


def run(coro):
    return asyncio.run(coro)


def install(monkeypatch, module, repos, login="agentbot"):
    monkeypatch.setattr(module, "_client", lambda: FakeGithub(repos, login))


# ── Bug 2: the token had two sources that disagreed ──────────────────────────────

def test_tools_accept_a_token_that_only_pydantic_settings_knows_about(monkeypatch):
    """A token in backend/.env reaches settings but never os.environ.

    github_pr read both sources, github_ops read only os.environ, so the documented
    setup left nine of ten tools reporting a missing credential.
    """
    import config
    from tools import github_client

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(config.settings, "github_token", "ghp_from_dotenv")

    assert github_client.github_token() == "ghp_from_dotenv"
    assert ops._require_token() == "ghp_from_dotenv"


def test_no_token_anywhere_still_parks_the_task(monkeypatch):
    import config
    from tools.credential_request import WAITING_CREDENTIAL_SENTINEL

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(config.settings, "github_token", "")

    for coro in (ops.github_merge_pr({"repo": "o/r", "pr_number": 1}),
                 gpr.github_pr({"title": "t", "body": "b", "head_branch": "h",
                                "files": [{"path": "a", "content": "b"}]})):
        assert run(coro)[WAITING_CREDENTIAL_SENTINEL] is True


# ── The merge guard ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs,expected_fragment", [
    ({"mergeable": False, "mergeable_state": "dirty"},          "conflict"),
    ({"mergeable_state": "blocked"},                            "required"),
    ({"mergeable_state": "unstable"},                           "failing or still running"),
    ({"mergeable_state": "behind"},                             "behind the base"),
    ({"draft": True},                                           "draft"),
])
def test_merge_refuses_and_names_the_blocker(monkeypatch, kwargs, expected_fragment):
    pr = FakePR(**kwargs)
    repo = FakeRepo(pr=pr)
    install(monkeypatch, ops, {"o/r": repo})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7}))

    assert result["ok"] is False and result["merged"] is False
    assert result["refused"] is True
    assert expected_fragment in result["reason"]
    assert pr.merge_calls == [], "refused merges must never call the GitHub merge endpoint"


def test_merge_refuses_when_changes_were_requested(monkeypatch):
    # mergeable_state stays "clean" on an unprotected repo even with a blocking review,
    # so the review verdict has to be checked separately or a rejected PR merges.
    pr = FakePR(mergeable_state="clean",
                reviews=[FakeReview("carol", "APPROVED"), FakeReview("dave", "CHANGES_REQUESTED")])
    repo = FakeRepo(pr=pr)
    install(monkeypatch, ops, {"o/r": repo})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7}))

    assert result["refused"] is True
    assert "dave" in result["reason"]
    assert pr.merge_calls == []


def test_merge_refusal_names_the_failing_check(monkeypatch):
    pr = FakePR(mergeable_state="unstable")
    repo = FakeRepo(pr=pr, check_runs=[FakeCheckRun("unit-tests", conclusion="failure"),
                                       FakeCheckRun("lint")])
    install(monkeypatch, ops, {"o/r": repo})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7}))

    assert "unit-tests" in result["reason"]
    assert result["checks"]["failing"] == ["unit-tests"]


def test_merge_proceeds_when_clean_and_defaults_to_squash(monkeypatch):
    pr = FakePR(mergeable_state="clean", reviews=[FakeReview("carol", "APPROVED")])
    repo = FakeRepo(pr=pr, check_runs=[FakeCheckRun("unit-tests")])
    install(monkeypatch, ops, {"o/r": repo})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7}))

    assert result["ok"] is True and result["merged"] is True
    assert result["sha"] == "deadbeef"
    assert pr.merge_calls == [{"merge_method": "squash"}]


def test_merge_honours_an_explicit_method(monkeypatch):
    pr = FakePR()
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7, "merge_method": "rebase"}))

    assert pr.merge_calls == [{"merge_method": "rebase"}]


def test_merge_rejects_an_unknown_method(monkeypatch):
    pr = FakePR()
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7, "merge_method": "yolo"}))

    assert result["ok"] is False and pr.merge_calls == []


def test_already_merged_pr_is_success_not_failure(monkeypatch):
    # The tool-call cache can replay a merge after a restart; a second run must agree
    # with the first rather than reporting the goal as failed.
    pr = FakePR(merged=True, state="closed")
    repo = FakeRepo(pr=pr)
    install(monkeypatch, ops, {"o/r": repo})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7}))

    assert result["ok"] is True and result["already_merged"] is True
    assert pr.merge_calls == []


def test_closed_unmerged_pr_is_refused(monkeypatch):
    pr = FakePR(state="closed", merged=False)
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7}))

    assert result["refused"] is True and "closed" in result["reason"]


def test_merge_waits_for_github_to_compute_mergeability(monkeypatch):
    """mergeable_state is "unknown" for a moment after a PR is opened."""
    pr = FakePR(mergeable_state="unknown")
    repo = FakeRepo(pr=pr)
    install(monkeypatch, ops, {"o/r": repo})

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        pr.mergeable_state = "clean"      # GitHub catches up during the wait

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7}))

    assert slept, "should have waited instead of refusing on 'unknown'"
    assert result["merged"] is True


# ── Reading a PR ─────────────────────────────────────────────────────────────────

def test_get_pr_files_returns_the_real_diff(monkeypatch):
    pr = FakePR(files=[FakeFile("calc.py", patch="@@\n-return sum(n)/len(n)\n+if not n: return 0"),
                       FakeFile("README.md", patch="@@\n+docs")])
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_get_pr_files({"repo": "o/r", "pr_number": 7}))

    assert result["ok"] is True
    assert [f["path"] for f in result["files"]] == ["calc.py", "README.md"]
    assert "+if not n: return 0" in result["files"][0]["patch"]
    assert result["total_changed_files"] == 2


def test_get_pr_files_truncates_a_huge_diff(monkeypatch):
    # An unbounded diff silently blows the model's context window and the agent then
    # reviews whatever survived truncation without knowing it was truncated.
    pr = FakePR(files=[FakeFile("big.py", patch="x" * 50_000)])
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_get_pr_files({"repo": "o/r", "pr_number": 7}))

    assert len(result["files"][0]["patch"]) < 50_000
    assert result["patches_truncated"] == ["big.py"]


def test_get_pr_files_budget_holds_across_several_huge_diffs(monkeypatch):
    # The single-file case above passes even when the budget arithmetic is wrong. It takes
    # a SECOND large file to expose it: charging the truncation marker to the budget drove
    # it negative, and `patch[:negative]` slices from the end of the string, so the second
    # file came back all but whole — while still being reported as truncated.
    pr = FakePR(files=[FakeFile("big1.py", patch="a" * 50_000),
                       FakeFile("big2.py", patch="b" * 50_000),
                       FakeFile("big3.py", patch="c" * 50_000)])
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_get_pr_files({"repo": "o/r", "pr_number": 7}))

    total = sum(len(f["patch"]) for f in result["files"])
    assert total < ops._MAX_PATCH_CHARS + 200, f"budget blown: {total} chars returned"
    assert "b" * 100 not in result["files"][1]["patch"]
    assert result["patches_truncated"] == ["big1.py", "big2.py", "big3.py"]


def test_get_pr_reports_checks_and_review_verdicts(monkeypatch):
    pr = FakePR(reviews=[FakeReview("carol", "APPROVED"),
                         FakeReview("dave", "CHANGES_REQUESTED")])
    repo = FakeRepo(pr=pr, check_runs=[FakeCheckRun("lint"),
                                       FakeCheckRun("e2e", status="in_progress", conclusion=None)])
    install(monkeypatch, ops, {"o/r": repo})

    result = run(ops.github_get_pr({"repo": "o/r", "pr_number": 7}))

    assert result["reviews"]["approved_by"] == ["carol"]
    assert result["reviews"]["changes_requested_by"] == ["dave"]
    assert result["checks"]["pending"] == ["e2e"]


# ── Reviewing ────────────────────────────────────────────────────────────────────

def test_review_pr_submits_the_requested_verdict(monkeypatch):
    pr = FakePR()
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_review_pr({"repo": "o/r", "pr_number": 7,
                                       "body": "LGTM", "event": "APPROVE"}))

    assert result["ok"] is True and pr.review_calls == ["APPROVE"]
    assert result["event_downgraded"] is False


def test_review_pr_downgrades_a_self_approval_and_says_so(monkeypatch):
    """GitHub rejects approving your own PR — the agent usually authored it."""
    pr = FakePR()
    pr.self_review_blocked = True
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_review_pr({"repo": "o/r", "pr_number": 7,
                                       "body": "LGTM", "event": "APPROVE"}))

    assert result["ok"] is True
    assert result["event_downgraded"] is True
    assert pr.review_calls == ["COMMENT"]


def test_review_pr_rejects_a_bogus_event(monkeypatch):
    pr = FakePR()
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_review_pr({"repo": "o/r", "pr_number": 7,
                                       "body": "x", "event": "LGTM"}))

    assert result["ok"] is False and pr.review_calls == []


# ── Issues ───────────────────────────────────────────────────────────────────────

def test_create_issue(monkeypatch):
    repo = FakeRepo()
    install(monkeypatch, ops, {"o/r": repo})

    result = run(ops.github_create_issue({"repo": "o/r", "title": "average() crashes on []",
                                          "body": "ZeroDivisionError", "labels": ["bug"]}))

    assert result["ok"] is True and result["number"] == 12
    assert repo.created_issues == ["average() crashes on []"]


# ── Bug 3: github_pr robustness ──────────────────────────────────────────────────

def test_pr_refuses_an_empty_file_list_before_creating_a_branch(monkeypatch):
    # GitHub rejects this as "No commits between" only AFTER the branch exists,
    # leaving a stray branch behind on every attempt.
    repo = FakeRepo()
    install(monkeypatch, gpr, {"o/r": repo})

    result = run(gpr.github_pr({"repo": "o/r", "title": "t", "body": "b",
                                "head_branch": "fix/x", "files": []}))

    assert result["ok"] is False
    assert "files[] is empty" in result["error"]
    assert repo.created_refs == [], "must not create a branch it cannot open a PR from"


def test_pr_returns_the_existing_pr_instead_of_failing_on_a_rerun(monkeypatch):
    existing = FakePR(number=99, base="main")
    repo = FakeRepo(pr=existing)
    repo.create_pull_error = _gh_error(422, "A pull request already exists for agentbot:fix/x.")
    repo.open_pulls = [existing]
    install(monkeypatch, gpr, {"o/r": repo})

    result = run(gpr.github_pr({"repo": "o/r", "title": "t", "body": "b",
                                "head_branch": "fix/x",
                                "files": [{"path": "a.py", "content": "x"}]}))

    assert result["ok"] is True and result["existing"] is True
    assert result["result"] == 99


def test_pr_falls_back_to_the_default_branch_when_the_base_is_wrong(monkeypatch):
    # Models guess "main" on repos whose default is "master".
    repo = FakeRepo(default_branch="master", branches=("master",))
    install(monkeypatch, gpr, {"o/r": repo})

    run(gpr.github_pr({"repo": "o/r", "title": "t", "body": "b", "head_branch": "fix/x",
                       "base_branch": "main", "files": [{"path": "a.py", "content": "x"}]}))

    assert repo.created_pulls[0]["base"] == "master"


def test_fork_pr_branches_from_the_upstream_head_not_the_stale_fork(monkeypatch):
    """A fork made weeks ago sits at an old commit.

    Branching off the fork's own default branch produces a PR whose diff reverts every
    upstream commit landed since the fork was taken.
    """
    upstream = FakeRepo("o/r", push=False, branches=("main",))
    fork = FakeRepo("agentbot/r", branches=("main",))
    upstream_pr = FakePR(number=5)
    upstream._pr = upstream_pr
    install(monkeypatch, gpr, {"o/r": upstream, "agentbot/r": fork})

    result = run(gpr.github_pr({"repo": "o/r", "title": "t", "body": "b",
                                "head_branch": "fix/x",
                                "files": [{"path": "a.py", "content": "x"}]}))

    assert result["ok"] is True and result["mode"] == "fork"
    assert fork.created_refs == [("refs/heads/fix/x", "sha-main")], \
        "the new branch must start from the upstream base commit"
    assert upstream.created_pulls[0]["head"] == "agentbot:fix/x"


# ── Registry wiring ──────────────────────────────────────────────────────────────

def test_every_tool_an_agent_may_call_actually_exists():
    from agent_registry import AGENT_REGISTRY
    from tools import TOOL_REGISTRY

    for role, cfg in AGENT_REGISTRY.items():
        for tool in cfg["allowed_tools"]:
            assert tool in TOOL_REGISTRY, f"{role} may call {tool}, which is not registered"


def test_the_integrator_can_merge_and_the_researcher_can_read_a_diff():
    from agent_registry import AGENT_REGISTRY

    assert "github_merge_pr" in AGENT_REGISTRY["integrator"]["allowed_tools"]
    assert "github_get_pr_files" in AGENT_REGISTRY["researcher"]["allowed_tools"]


def test_the_orchestrator_is_told_merging_exists():
    # An agent cannot be routed work the planner has never heard of.
    from orchestrator import SYSTEM_PROMPT

    assert "github_merge_pr" in SYSTEM_PROMPT
    assert "github_get_pr_files" in SYSTEM_PROMPT


def test_branch_cleanup_failure_never_unreports_a_completed_merge(monkeypatch):
    """The merge already landed; cleanup problems must not flip ok to False.

    FakeRepo has no get_git_ref, so the delete raises — as it would against a protected
    or already-deleted branch.
    """
    pr = FakePR()
    pr.head.repo = FakeRepo("o/r")          # same repo, so cleanup is attempted
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7, "delete_branch": True}))

    assert result["ok"] is True and result["merged"] is True
    assert result["branch_deleted"] is None
    assert "branch_delete_error" in result


def test_branch_cleanup_is_skipped_for_a_fork_head(monkeypatch):
    # pr.head.repo is None once the fork the branch lived in has been deleted.
    pr = FakePR()
    pr.head.repo = None
    install(monkeypatch, ops, {"o/r": FakeRepo(pr=pr)})

    result = run(ops.github_merge_pr({"repo": "o/r", "pr_number": 7, "delete_branch": True}))

    assert result["ok"] is True and result["merged"] is True
    assert "branch_delete_skipped" in result


# ── Plan validation: a merge plan has no coder ───────────────────────────────────

def _plan(tasks, terminal):
    from orchestrator import PlanSchema
    return PlanSchema(tasks=tasks, terminal=terminal, reasoning="t")


def _task(id, agent, description="do the thing", inputs=None, depends_on=()):
    return {"id": id, "agent": agent, "description": description,
            "inputs": inputs or {}, "depends_on": list(depends_on)}


def test_a_merge_plan_validates_even_though_it_has_no_coder():
    """Regression: "merge PR #3" failed before ever reaching GitHub.

    _validate_plan allowed a terminal integrator only when the plan ALSO had a coder —
    the issue-fix shape. A merge needs no coder, so every merge plan was rejected, the
    orchestrator burned all five attempts, and the goal failed with a validation error.
    Found by running the real goal against a real PR, not by the stubbed suite.
    """
    from orchestrator import _validate_plan

    _validate_plan(_plan(
        [_task("t1", "integrator", "Get pull request #3 details",
               {"repo": "o/r", "pr_number": 3}),
         _task("t2", "integrator", "Merge pull request #3",
               {"repo": "o/r", "pr_number": 3}, ["t1"])],
        "t2",
    ))


def test_the_issue_fix_shape_still_validates():
    from orchestrator import _validate_plan

    _validate_plan(_plan(
        [_task("t1", "researcher", "read the repo"),
         _task("t2", "coder", "write the fix", depends_on=["t1"]),
         _task("t3", "integrator", "open the PR", depends_on=["t2"])],
        "t3",
    ))


def test_an_integrator_that_only_fetches_data_still_needs_a_writer():
    # The rule this exemption carves out of must survive: raw API data is not an answer.
    from orchestrator import _validate_plan

    with pytest.raises(ValueError, match="raw data"):
        _validate_plan(_plan(
            [_task("t1", "researcher", "look up the weather"),
             _task("t2", "integrator", "call the weather API", depends_on=["t1"])],
            "t2",
        ))
