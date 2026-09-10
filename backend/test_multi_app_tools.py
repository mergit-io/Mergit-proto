"""Slack, Linear and Notion: the three services that made Mergit a multi-app agent.

GitHub was the only outside system Mergit could write to, and one app is not a workflow.
These tests pin the contract of the three that followed. Every one of them stubs the
network — the point is what the tools do with an answer, and none of that should need a
token or a workspace to check.

The failures being pinned are the ones each API actually produces, and each looks like
success if you only read the status code:

* Slack answers HTTP 200 with `{"ok": false, "error": "not_in_channel"}`.
* Linear answers HTTP 200 with `{"errors": [...]}`, and `success: false` inside a mutation
  is a third way to fail while looking fine.
* Notion answers 404 `object_not_found` when the page exists but was never shared with the
  integration — the single most common Notion integration failure, and the one whose own
  message does not say what to do about it.

The other half of the contract is the URL. `agent_runner._claimed_without_artifact`
rejects a submission that claims it produced something addressable without an address, so
every write tool here must hand back a real one or a real, successful action gets reported
as a failure.
"""
import asyncio
import json

import pytest

import tools.linear_ops as linear
import tools.notion_ops as notion
import tools.service_client as svc
import tools.slack_ops as slack


# ── Fake transport ───────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not JSON")
        return self._payload


class _FakeClient:
    """An httpx.AsyncClient stand-in that replays queued answers and records calls.

    Keyed on a substring of the URL rather than the whole thing, because the tools build
    their own URLs and pinning them exactly would make this a test of string formatting.
    """

    def __init__(self, routes, calls):
        self._routes = routes
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def _answer(self, method, url, kwargs):
        self.calls.append({"method": method, "url": url,
                           "json": kwargs.get("json"), "params": kwargs.get("params"),
                           "headers": kwargs.get("headers", {})})
        for fragment, answer in self._routes.items():
            if fragment in url:
                return answer() if callable(answer) else answer
        raise AssertionError(f"no fake route for {method} {url}")

    async def get(self, url, **kw):
        return self._answer("GET", url, kw)

    async def post(self, url, **kw):
        return self._answer("POST", url, kw)

    async def request(self, method, url, **kw):
        return self._answer(method, url, kw)


def _install(monkeypatch, module, routes):
    """Point `module.httpx.AsyncClient` at the fake and return the call log."""
    calls: list[dict] = []

    class _Factory:
        def __init__(self, *_a, **_kw):
            pass

        def __new__(cls, *_a, **_kw):
            return _FakeClient(routes, calls)

    monkeypatch.setattr(module.httpx, "AsyncClient", _Factory)
    return calls


@pytest.fixture(autouse=True)
def _deployment_tokens(monkeypatch):
    """Every test runs on the single-tenant path unless it says otherwise.

    Without this each tool would park on WAITING_CREDENTIAL before reaching the behaviour
    under test, and the suite would assert nothing except that the guard works.
    """
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test")
    monkeypatch.setenv("NOTION_API_KEY", "ntn_test")
    slack._CHANNEL_IDS.clear()
    linear._TEAM_IDS.clear()
    yield
    slack._CHANNEL_IDS.clear()
    linear._TEAM_IDS.clear()


# ── service_client ───────────────────────────────────────────────────────────────

def test_missing_credential_parks_rather_than_fails(monkeypatch):
    """No token anywhere is a park, not an error — the task resumes on the same run."""
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.setattr(svc.settings, "linear_api_key", "", raising=False)

    parked = asyncio.run(svc.credential_check("linear", {}))
    assert parked is not None
    assert parked["__WAITING_CREDENTIAL__"] is True
    assert parked["credential"] == "LINEAR_API_KEY"
    assert parked["provider"] == "linear"
    assert "connect=linear" in parked["connect_url"]


def test_deployment_token_satisfies_the_check():
    assert asyncio.run(svc.credential_check("slack", {})) is None
    assert asyncio.run(svc.token("slack", {})) == "xoxb-test"


def test_user_connection_wins_over_deployment_token(monkeypatch):
    """A deployment key left in .env must never override a real per-user connection."""
    async def _fake_stored(provider, args):
        return "xoxb-belongs-to-the-user" if args.get("_user_id") else ""

    monkeypatch.setattr(svc, "_stored_token", _fake_stored)
    assert asyncio.run(svc.token("slack", {"_user_id": "u1"})) == "xoxb-belongs-to-the-user"
    assert asyncio.run(svc.token("slack", {})) == "xoxb-test"


# ── Slack ────────────────────────────────────────────────────────────────────────

_SLACK_LIST = {"ok": True, "channels": [{"id": "C0ENGBUGS", "name": "eng-bugs", "is_member": True}],
               "response_metadata": {"next_cursor": ""}}


def test_slack_resolves_a_channel_name_to_an_id(monkeypatch):
    calls = _install(monkeypatch, slack, {
        "conversations.list": _Resp(_SLACK_LIST),
        "conversations.history": _Resp({"ok": True, "messages": [
            {"ts": "1694500000.000100", "user": "U1", "text": "login 500s", "reply_count": 2}]}),
    })
    out = asyncio.run(slack.slack_read_channel({"channel": "#eng-bugs"}))
    assert out["ok"] is True
    assert out["channel"] == "C0ENGBUGS"
    assert out["messages"][0]["ts"] == "1694500000.000100"
    history = [c for c in calls if "conversations.history" in c["url"]][0]
    assert history["params"]["channel"] == "C0ENGBUGS"


def test_slack_text_is_html_unescaped(monkeypatch):
    """Slack stores `&`, `<` and `>` escaped. A pasted Python session arrives as
    `&gt;&gt;&gt; largest(...)`, and the coder agent reproduces whatever it is handed."""
    _install(monkeypatch, slack, {
        "conversations.replies": _Resp({"ok": True, "messages": [
            {"ts": "1.1", "user": "U1",
             "text": "repro:\n\n&gt;&gt;&gt; largest([-5, -2, -9])\n0\n\nexpected -2 &amp; not 0"}]}),
    })
    out = asyncio.run(slack.slack_read_thread({"channel": "C0ENGBUGS", "thread_ts": "1.0"}))
    assert out["ok"] is True
    assert ">>> largest([-5, -2, -9])" in out["messages"][0]["text"]
    assert "-2 & not 0" in out["messages"][0]["text"]


def test_slack_channel_id_is_used_directly(monkeypatch):
    """An id must not trigger a channel listing — that is a wasted paginated call."""
    calls = _install(monkeypatch, slack, {
        "conversations.history": _Resp({"ok": True, "messages": []}),
    })
    out = asyncio.run(slack.slack_read_channel({"channel": "C0ENGBUGS"}))
    assert out["ok"] is True
    assert not any("conversations.list" in c["url"] for c in calls)


def test_slack_ok_false_is_an_error_not_a_success(monkeypatch):
    """HTTP 200 with ok:false is Slack's normal failure. Reading the status code alone is
    how an agent comes to believe it posted into a channel it was never invited to."""
    _install(monkeypatch, slack, {
        "chat.postMessage": _Resp({"ok": False, "error": "not_in_channel"}),
    })
    out = asyncio.run(slack.slack_post_message({"channel": "C0ENGBUGS", "text": "hi"}))
    assert out["ok"] is False
    assert "not_in_channel" in out["error"]
    assert "/invite" in out["error"]  # the error says what to do about it


def test_slack_reply_returns_a_permalink(monkeypatch):
    _install(monkeypatch, slack, {
        "chat.postMessage": _Resp({"ok": True, "ts": "1694500123.000200"}),
        "chat.getPermalink": _Resp({"ok": True, "permalink": "https://acme.slack.com/archives/C0ENGBUGS/p1694500123000200"}),
    })
    out = asyncio.run(slack.slack_reply_in_thread(
        {"channel": "C0ENGBUGS", "thread_ts": "1694500000.000100", "text": "PR is up"}))
    assert out["ok"] is True
    assert out["url"].startswith("https://acme.slack.com/archives/")
    assert out["thread_ts"] == "1694500000.000100"


def test_slack_permalink_falls_back_to_the_archive_url(monkeypatch):
    """A real post with no link is reported as a failure by the artifact guard, so losing
    chat.getPermalink must not lose the address."""
    _install(monkeypatch, slack, {
        "chat.postMessage": _Resp({"ok": True, "ts": "1694500123.000200"}),
        "chat.getPermalink": _Resp({"ok": False, "error": "method_not_supported"}),
        "auth.test": _Resp({"ok": True, "url": "https://acme.slack.com/"}),
    })
    out = asyncio.run(slack.slack_post_message({"channel": "C0ENGBUGS", "text": "hi"}))
    assert out["ok"] is True
    assert out["url"] == "https://acme.slack.com/archives/C0ENGBUGS/p1694500123000200"


def test_slack_reply_requires_a_thread(monkeypatch):
    _install(monkeypatch, slack, {})
    out = asyncio.run(slack.slack_reply_in_thread({"channel": "C0ENGBUGS", "text": "hi"}))
    assert out["ok"] is False
    assert "thread_ts" in out["error"]


def test_slack_unknown_channel_names_the_fix(monkeypatch):
    _install(monkeypatch, slack, {"conversations.list": _Resp(_SLACK_LIST)})
    out = asyncio.run(slack.slack_read_channel({"channel": "#nowhere"}))
    assert out["ok"] is False
    assert "invite" in out["error"].lower()


# ── Linear ───────────────────────────────────────────────────────────────────────

_TEAMS = {"data": {"teams": {"nodes": [{"id": "team-uuid-1", "key": "ENG", "name": "Engineering"}]}}}


def test_linear_personal_key_is_sent_raw_and_oauth_as_bearer():
    """Sending `Bearer lin_api_…` fails authentication. The prefix decides the format."""
    assert linear._auth_header("lin_api_abc") == "lin_api_abc"
    assert linear._auth_header("oauth-token") == "Bearer oauth-token"


def test_linear_create_issue_resolves_the_team_key_and_returns_a_url(monkeypatch):
    created = {"data": {"issueCreate": {"success": True, "issue": {
        "id": "issue-uuid", "identifier": "ENG-42", "title": "fix login 500",
        "url": "https://linear.app/acme/issue/ENG-42", "state": {"name": "Todo"}}}}}
    answers = [_Resp(_TEAMS), _Resp(created)]
    calls = _install(monkeypatch, linear, {"api.linear.app": lambda: answers.pop(0)})

    out = asyncio.run(linear.linear_create_issue(
        {"team": "ENG", "title": "fix login 500", "description": "see PR"}))
    assert out["ok"] is True
    assert out["identifier"] == "ENG-42"
    assert out["url"] == "https://linear.app/acme/issue/ENG-42"
    assert calls[-1]["json"]["variables"]["teamId"] == "team-uuid-1"


def test_linear_graphql_errors_arrive_with_http_200(monkeypatch):
    _install(monkeypatch, linear, {
        "api.linear.app": _Resp({"errors": [{"message": "Field 'nope' doesn't exist"}]}),
    })
    out = asyncio.run(linear.linear_create_issue({"team": "ENG", "title": "x"}))
    assert out["ok"] is False
    assert "doesn't exist" in out["error"]


def test_linear_success_false_is_not_a_created_issue(monkeypatch):
    """Linear's quiet refusal: no errors array, no issue, `success: false`."""
    answers = [_Resp(_TEAMS), _Resp({"data": {"issueCreate": {"success": False, "issue": None}}})]
    _install(monkeypatch, linear, {"api.linear.app": lambda: answers.pop(0)})
    out = asyncio.run(linear.linear_create_issue({"team": "ENG", "title": "x"}))
    assert out["ok"] is False
    assert "success=false" in out["error"]


def test_linear_resolves_an_identifier_to_an_id(monkeypatch):
    lookup = {"data": {"issues": {"nodes": [{"id": "issue-uuid", "identifier": "ENG-42"}]}}}
    read = {"data": {"issue": {
        "id": "issue-uuid", "identifier": "ENG-42", "title": "fix login 500",
        "description": "", "url": "https://linear.app/acme/issue/ENG-42",
        "state": {"name": "In Review", "type": "started"}, "team": {"key": "ENG"},
        "comments": {"nodes": []}}}}
    answers = [_Resp(lookup), _Resp(read)]
    calls = _install(monkeypatch, linear, {"api.linear.app": lambda: answers.pop(0)})

    out = asyncio.run(linear.linear_get_issue({"issue": "ENG-42"}))
    assert out["ok"] is True
    assert out["state"] == "In Review"
    assert calls[0]["json"]["variables"] == {"key": "ENG", "number": 42}


def test_linear_unknown_state_lists_the_real_ones(monkeypatch):
    """A refused state name must name the states that exist, or the agent guesses again."""
    states = {"data": {"team": {"states": {"nodes": [
        {"id": "s1", "name": "Todo", "type": "unstarted"},
        {"id": "s2", "name": "In Review", "type": "started"}]}}}}
    answers = [_Resp(_TEAMS), _Resp(states)]
    _install(monkeypatch, linear, {"api.linear.app": lambda: answers.pop(0)})

    out = asyncio.run(linear.linear_create_issue(
        {"team": "ENG", "title": "x", "state": "Reviewing"}))
    assert out["ok"] is False
    assert "In Review" in out["error"]


def test_linear_rejects_a_meaningless_identifier(monkeypatch):
    _install(monkeypatch, linear, {})
    out = asyncio.run(linear.linear_get_issue({"issue": "the login bug"}))
    assert out["ok"] is False
    assert "ENG-42" in out["error"]


# ── Notion ───────────────────────────────────────────────────────────────────────

def test_notion_accepts_an_id_a_dashed_id_or_a_url():
    bare = "24f1a2b3c4d5e6f70123456789abcdef"
    assert notion._page_id(bare) == bare
    assert notion._page_id("24f1a2b3-c4d5-e6f7-0123-456789abcdef") == bare
    assert notion._page_id(f"https://www.notion.so/Eng-Bugs-{bare}?v=9") == bare
    assert notion._page_id("not a page") == ""


def test_notion_markdown_becomes_typed_blocks():
    blocks = notion.markdown_to_blocks(
        "# Incident\n\n- login 500s\n\n```python\nx = 1\n```\n\n---\n\nFixed in PR #12")
    kinds = [b["type"] for b in blocks]
    assert kinds == ["heading_1", "bulleted_list_item", "code", "divider", "paragraph"]
    assert blocks[2]["code"]["language"] == "python"


def test_notion_unknown_code_language_does_not_400():
    """Notion validates `language` against a closed list and rejects anything else."""
    blocks = notion.markdown_to_blocks("```brainfuck\n+++\n```")
    assert blocks[0]["code"]["language"] == "plain text"


def test_notion_create_page_requires_a_parent(monkeypatch):
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    monkeypatch.setattr(notion.settings, "notion_parent_page_id", "", raising=False)
    _install(monkeypatch, notion, {})
    out = asyncio.run(notion.notion_create_page({"title": "Incident"}))
    assert out["ok"] is False
    assert "NOTION_PARENT_PAGE_ID" in out["error"]


def test_notion_create_page_returns_a_url(monkeypatch):
    parent = "24f1a2b3c4d5e6f70123456789abcdef"
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", parent)
    calls = _install(monkeypatch, notion, {
        "/v1/pages": _Resp({"id": "aa11bb22cc33dd44ee55ff6677889900",
                            "url": "https://www.notion.so/Incident-aa11bb22"}),
    })
    out = asyncio.run(notion.notion_create_page(
        {"title": "Incident: login 500s", "content": "## Root cause\n\n- off-by-one"}))
    assert out["ok"] is True
    assert out["url"] == "https://www.notion.so/Incident-aa11bb22"
    body = calls[0]["json"]
    assert body["parent"] == {"type": "page_id", "page_id": parent}
    assert body["children"][0]["type"] == "heading_2"
    assert calls[0]["headers"]["Notion-Version"] == notion.NOTION_VERSION


def test_notion_not_shared_error_says_how_to_share(monkeypatch):
    """404 object_not_found almost always means the page was never connected to the
    integration, and Notion's own message never says so."""
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "24f1a2b3c4d5e6f70123456789abcdef")
    _install(monkeypatch, notion, {
        "/v1/pages": _Resp({"code": "object_not_found", "message": "Could not find page"}, status=404),
    })
    out = asyncio.run(notion.notion_create_page({"title": "Incident"}))
    assert out["ok"] is False
    assert "Connections" in out["error"]


def test_notion_get_page_reads_title_and_text_back(monkeypatch):
    page = "aa11bb22cc33dd44ee55ff6677889900"
    _install(monkeypatch, notion, {
        f"/v1/pages/{page}": _Resp({
            "id": page, "url": "https://www.notion.so/Incident-aa11bb22", "archived": False,
            "properties": {"title": {"type": "title", "title": [{"plain_text": "Incident: login 500s"}]}}}),
        f"/v1/blocks/{page}/children": _Resp({"results": [
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "off-by-one in auth"}]}}]}),
    })
    out = asyncio.run(notion.notion_get_page({"page_id": page}))
    assert out["ok"] is True
    assert out["title"] == "Incident: login 500s"
    assert "off-by-one" in out["content"]


# ── Registry wiring ──────────────────────────────────────────────────────────────

def test_every_new_tool_is_registered_and_reachable_by_an_agent():
    """A tool that exists but is in no agent's allowed_tools can never be called, and a
    tool in allowed_tools but not the registry is shown to the model and then 404s."""
    from agent_registry import AGENT_REGISTRY
    from tools import TOOL_REGISTRY

    new_tools = {n for n in TOOL_REGISTRY
                 if n.split("_")[0] in ("slack", "linear", "notion")}
    assert len(new_tools) == 15

    reachable = set()
    for agent in AGENT_REGISTRY.values():
        reachable.update(agent["allowed_tools"])
    assert new_tools <= reachable, f"unreachable: {sorted(new_tools - reachable)}"
    assert reachable <= set(TOOL_REGISTRY) | {"code_exec"}, "an agent lists a tool that does not exist"


def test_the_planner_knows_the_new_services_exist():
    """The orchestrator picks agents from a written description, not from the registry, so
    a capability that is not in that text is a capability the planner will never use."""
    from orchestrator import AGENT_DESCRIPTIONS
    for needle in ("slack_read_thread", "slack_reply_in_thread",
                   "linear_create_issue", "notion_create_page"):
        assert needle in AGENT_DESCRIPTIONS, f"planner cannot see {needle}"


# ── Unfilled placeholders ────────────────────────────────────────────────────────

def test_a_self_referencing_template_never_reaches_linear(monkeypatch):
    """Run 0e9fefe4 planned `"issue_description": "Bug fix PR: {{0e9fefe4_t3.output.url}}"` —
    task t3 referring to its own output, which cannot resolve because t3 is the task being
    planned. A ticket carrying that text says nothing to whoever opens it."""
    _install(monkeypatch, linear, {})
    out = asyncio.run(linear.linear_create_issue(
        {"team": "ABH", "title": "fix largest()",
         "description": "Bug fix PR: {{0e9fefe4_t3.output.url}}"}))
    assert out["ok"] is False
    assert "{{0e9fefe4_t3.output.url}}" in out["error"]


def test_a_blank_never_reaches_a_slack_channel(monkeypatch):
    """And it is refused before the channel lookup — there is no reason to spend a
    paginated API call on a message that was never going to be sent."""
    calls = _install(monkeypatch, slack, {})
    out = asyncio.run(slack.slack_post_message(
        {"channel": "#eng-bugs", "text": "Fixed in PR #<pr_number>"}))
    assert out["ok"] is False
    assert "<pr_number>" in out["error"]
    assert calls == []


def test_a_blank_never_reaches_a_notion_page(monkeypatch):
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "24f1a2b3c4d5e6f70123456789abcdef")
    calls = _install(monkeypatch, notion, {})
    out = asyncio.run(notion.notion_create_page(
        {"title": "Incident", "content": "See {{t3.output.url}}"}))
    assert out["ok"] is False
    assert calls == []


def test_real_prose_is_not_mistaken_for_a_blank(monkeypatch):
    """`Vec<String>`, `<div>` and a bare URL have no underscore, so they are not blanks.
    A wrong refusal costs a real message."""
    from tools.placeholders import unfilled_placeholders
    assert unfilled_placeholders("use Vec<String> and <div>, see <https://example.com>") == []
    assert unfilled_placeholders("Fixed in PR #<PR_NUMBER>")  # casing does not save it


# ── The planner's view of what is connected ──────────────────────────────────────

def test_planner_is_told_which_apps_have_no_credential(monkeypatch):
    """Run 0e9fefe4 stalled at WAITING_CREDENTIAL on NOTION_API_KEY: the plan was right and
    produced nothing, because the planner could not know which app was uncredentialled."""
    import orchestrator

    class _Goal:
        id = "goal-under-test"

    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.setattr(orchestrator.settings, "notion_api_key", "", raising=False)

    note = asyncio.run(orchestrator.connected_apps_note(_Goal()))
    assert "slack" in note.split("NOT CONNECTED")[0]
    assert "linear" in note.split("NOT CONNECTED")[0]
    assert "NOT CONNECTED: notion" in note
    assert "Do NOT plan any step that uses notion" in note


def test_every_connected_app_means_no_warning(monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", "ntn_test")
    import orchestrator

    class _Goal:
        id = "goal-under-test"

    note = asyncio.run(orchestrator.connected_apps_note(_Goal()))
    assert "NOT CONNECTED" not in note


# ── The artifact guard, extended past GitHub ─────────────────────────────────────

def test_a_write_claim_must_carry_an_address_and_a_read_must_not():
    """`_claimed_without_artifact` asks "you say you made something — where is it?".

    A write verb is required, not merely a service name: "read the slack thread" is an
    ordinary integrator action that produces no address, and demanding one would fail a
    task that did exactly what it was asked.
    """
    from agent_runner import _claimed_without_artifact

    writes = ["posted a message to slack", "replied in thread", "created a Linear ticket",
              "created a notion page", "filed the incident in Notion", "opened a linear issue"]
    for action in writes:
        assert _claimed_without_artifact({"action": action, "result": "done", "url": None}) == action
        assert _claimed_without_artifact(
            {"action": action, "result": "done", "url": "https://x.slack.com/archives/C1/p1"}) is None

    for action in ["read the slack thread", "reviewed the linear board", "summarised the repo"]:
        assert _claimed_without_artifact({"action": action, "result": "done", "url": None}) is None
