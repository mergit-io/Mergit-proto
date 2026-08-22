"""Forking is a thing users ask for, so it has to be a thing an agent can do.

Goal 5981fe39 asked Mergit to "fork this repo and raise an issue then fix it with a PR".
The orchestrator planned a task that began "Fork the repository and…", and the integrator
had no fork action to call — of the 26 registered tools, none forked. Forking existed only
inside `github_pr`, as an automatic fallback for when the token lacks push access, so it
could not be asked for, only stumbled into.

These tests pin the tool's contract. The GitHub client is stubbed throughout: the point is
the tool's behaviour, and none of it should need the network.
"""
import asyncio

import pytest

import tools.github_ops as ops


class _FakeRepo:
    def __init__(self, full_name, default_branch="main"):
        self.full_name = full_name
        self.name = full_name.split("/")[1]
        self.default_branch = default_branch
        self.html_url = "https://github.com/" + full_name

    def get_branch(self, _name):
        return object()


class _FakeUser:
    def __init__(self, login):
        self.login = login
        self.forked = []

    def create_fork(self, upstream):
        self.forked.append(upstream.full_name)
        return _FakeRepo(f"{self.login}/{upstream.name}")


class _FakeGithub:
    """Repos that exist, plus a login.

    `appears` names a repo that does not exist yet and springs into being once it has been
    looked up `appears_after` times — GitHub's asynchronous fork, in miniature. The count
    is kept PER NAME: a single counter across all lookups made the upstream's own lookup
    advance the fork's clock, so the fork existed before it had been created and every run
    took the already-existed path.
    """

    def __init__(self, repos, login="bot", appears=None, appears_after=0):
        self._repos = dict(repos)
        self._appears = appears
        self._appears_after = appears_after
        self.lookups: dict[str, int] = {}
        self.user = _FakeUser(login)

    def get_user(self):
        return self.user

    def get_repo(self, full_name):
        self.lookups[full_name] = self.lookups.get(full_name, 0) + 1
        if (self._appears is not None and full_name == self._appears
                and self.lookups[full_name] > self._appears_after):
            self._repos[full_name] = _FakeRepo(full_name)
        if full_name not in self._repos:
            raise ops.GithubException(404, {"message": "Not Found"}, None)
        return self._repos[full_name]


@pytest.fixture()
def stub(monkeypatch):
    async def _no_credential_problem(_args):
        return None

    monkeypatch.setattr(ops, "_credential_check", _no_credential_problem)
    # Polling must not actually sleep.
    async def _instant(_s):
        return None
    monkeypatch.setattr(ops.asyncio, "sleep", _instant)

    def install(gh):
        async def _client(_args):
            return gh
        monkeypatch.setattr(ops, "_client", _client)
        return gh

    return install


def run(coro):
    return asyncio.run(coro)


# ── The happy path ──────────────────────────────────────────────────────────────

def test_forks_a_repo_and_returns_the_new_full_name(stub):
    # The fork appears on its second lookup: the first is the "does one already exist?"
    # check, which must miss so the fork is actually created.
    gh = stub(_FakeGithub({"upstream/proj": _FakeRepo("upstream/proj")},
                          appears="bot/proj", appears_after=1))
    out = run(ops.github_fork({"repo": "upstream/proj"}))

    assert out["ok"] is True
    assert out["fork"] == "bot/proj"
    assert out["url"] == "https://github.com/bot/proj"
    assert out["already_existed"] is False
    assert gh.user.forked == ["upstream/proj"]


def test_an_existing_fork_is_reported_not_refused(stub):
    """Re-running a goal must not fail because the first run already forked. The tool is
    asked for a fork to exist, not for a fork to be created."""
    gh = stub(_FakeGithub({
        "upstream/proj": _FakeRepo("upstream/proj"),
        "bot/proj": _FakeRepo("bot/proj"),
    }))
    out = run(ops.github_fork({"repo": "upstream/proj"}))

    assert out["ok"] is True
    assert out["already_existed"] is True
    assert out["fork"] == "bot/proj"
    assert gh.user.forked == []          # nothing was created a second time


def test_waits_for_an_async_fork_to_become_usable(stub):
    """GitHub creates forks asynchronously — the repo 404s for a moment after the call.
    Returning then would hand the next task a name it cannot push to."""
    gh = stub(_FakeGithub({"upstream/proj": _FakeRepo("upstream/proj")},
                          appears="bot/proj", appears_after=3))
    out = run(ops.github_fork({"repo": "upstream/proj"}))

    assert out["ok"] is True
    assert out["fork"] == "bot/proj"


# ── Failures ────────────────────────────────────────────────────────────────────

def test_a_fork_that_never_appears_is_an_error_not_a_success(stub):
    gh = stub(_FakeGithub({"upstream/proj": _FakeRepo("upstream/proj")}))
    out = run(ops.github_fork({"repo": "upstream/proj"}))

    assert out["ok"] is False
    assert "did not become ready" in out["error"]
    assert out.get("fork") is None


def test_an_unknown_upstream_is_an_error(stub):
    stub(_FakeGithub({}))
    out = run(ops.github_fork({"repo": "nobody/nothing"}))
    assert out["ok"] is False
    assert out.get("fork") is None


def test_missing_credentials_short_circuit(monkeypatch):
    async def _missing(_args):
        return {"ok": False, "error": "no github credential"}
    monkeypatch.setattr(ops, "_credential_check", _missing)
    out = run(ops.github_fork({"repo": "upstream/proj"}))
    assert out["ok"] is False


# ── Wiring ──────────────────────────────────────────────────────────────────────

def test_the_tool_is_registered_and_offered_to_the_integrator():
    import tools
    from agent_registry import AGENT_REGISTRY

    assert "github_fork" in tools.TOOL_REGISTRY
    assert "github_fork" in AGENT_REGISTRY["integrator"]["allowed_tools"]


def test_the_schema_only_demands_the_repo():
    assert ops.GITHUB_FORK_SCHEMA["required"] == ["repo"]
    assert "repo" in ops.GITHUB_FORK_SCHEMA["properties"]
