"""The harness has to be trustworthy before its numbers mean anything.

A suite that grades an agent's claims against themselves agrees with every lie, and a
suite that reports a failure as a pass is worse than no suite. These tests pin the two
places where that could happen: how a run is classified, and how "did this artifact come
from *this* run" is decided.

No network. The checks that talk to GitHub, Slack, Linear and Notion are exercised against
the live services by `evals/run.py`; what is pinned here is the reasoning around them.
"""
import time

import pytest

from evals.checks import Check, _iso_after
from evals.run import (LOUD_FAILURE, PESSIMISTIC, SILENT_FAILURE, SUCCESS,
                       RunResult, classify, report)


def _passed(name: str = "c") -> Check:
    return Check(name, True, "held")


def _failed(name: str = "c") -> Check:
    return Check(name, False, "did not hold")


# ── Classification ───────────────────────────────────────────────────────────────

def test_completed_and_verified_is_a_success():
    assert classify("COMPLETED", [_passed(), _passed()]) == SUCCESS


def test_completed_but_unverified_is_a_silent_failure():
    """The result the suite exists to count.

    The system said it finished. The services say otherwise. This costs more than an
    ordinary failure, because it is the run nobody goes and checks.
    """
    assert classify("COMPLETED", [_passed(), _failed()]) == SILENT_FAILURE


def test_a_failure_that_says_so_is_not_silent():
    assert classify("FAILED", [_failed()]) == LOUD_FAILURE
    assert classify("TIMEOUT", [_failed()]) == LOUD_FAILURE
    assert classify("WAITING_CREDENTIAL", [_failed()]) == LOUD_FAILURE


def test_doing_the_work_and_reporting_failure_is_its_own_category():
    """Rare, and not a success: the artifacts exist but the run disowned them, so a human
    is told to redo work that is already done."""
    assert classify("FAILED", [_passed()]) == PESSIMISTIC


def test_a_run_with_no_checks_at_all_is_never_a_success():
    """An empty verdict list means nothing was verified. Calling that a pass is exactly
    the mistake this harness exists to avoid."""
    assert classify("COMPLETED", []) == SILENT_FAILURE


# ── Freshness ────────────────────────────────────────────────────────────────────

def test_an_unparseable_timestamp_is_not_treated_as_fresh():
    """A check that guessed would report last week's ticket as this run's work, which is
    the one mistake a harness must not make."""
    since = int(time.time())
    assert _iso_after(None, since) is False
    assert _iso_after("", since) is False
    assert _iso_after("not a date", since) is False


def test_freshness_compares_against_the_watermark():
    since = 1_700_000_000
    assert _iso_after("2023-11-14T22:15:00Z", since) is True     # after
    assert _iso_after("2020-01-01T00:00:00Z", since) is False    # before
    assert _iso_after("2023-11-14T22:15:00+00:00", since) is True


# ── Reporting ────────────────────────────────────────────────────────────────────

def test_the_silent_failure_rate_is_computed_over_counted_runs_only():
    """A scenario skipped for a missing credential is the operator's problem, not the
    agent's, and must not dilute the rate either way."""
    runs = [
        RunResult("a", 1, SUCCESS, checks=[{"name": "x", "passed": True, "detail": "",
                                            "evidence": {}}]),
        RunResult("a", 2, SILENT_FAILURE, checks=[{"name": "x", "passed": False,
                                                   "detail": "no PR", "evidence": {}}]),
        RunResult("b", 0, "skipped"),
    ]
    summary = report(runs)
    assert summary["success_rate"] == 0.5
    assert summary["silent_failure_rate"] == 0.5
    assert len(summary["runs"]) == 2, "skipped runs are not counted"


def test_scenarios_declare_the_apps_they_need():
    """A scenario whose apps are absent is skipped rather than failed — otherwise the
    suite reports an agent failure for a credential the operator never set."""
    from evals import scenarios

    assert {s.id for s in scenarios.ALL} == {
        "ship_the_fix", "crash_not_logic", "silent_data_loss", "already_correct",
        "report_only", "degraded"}
    for scenario in scenarios.ALL:
        assert scenario.needs, f"{scenario.id} declares no apps"
        assert "{repo}" in scenario.goal or "{channel}" in scenario.goal


def test_most_of_the_suite_is_not_the_happy_path():
    """A suite made only of happy paths measures whether the demo works, not the system.

    `ship_the_fix` is the only scenario where doing the obvious thing is the right answer.
    Every other one is a way of being wrong: a crash rather than a wrong value, a success
    that lost data, nothing to fix at all, a one-step goal, and a missing credential.
    """
    from evals import scenarios

    happy = {"ship_the_fix"}
    assert len(scenarios.ALL) - len(happy) >= 4
    assert happy <= {s.id for s in scenarios.ALL}


# ── Failing and saying so is not failing silently ────────────────────────────────

_ADMITTED = ('{"pr_url": "https://github.com/x/y/pull/49", "notion": "Notion incident note '
             'could not be created due to missing parent page configuration."}')


def test_an_admitted_shortfall_is_not_a_silent_failure():
    """Run dcaac2eb: the Notion page really was not created, and the integrator said so in
    as many words. The goal was still marked COMPLETED.

    Counting that as a silent failure would be wrong twice — it slanders an agent that was
    honest, and it hides the real defect, which is that COMPLETED does not mean what it
    says when a stated objective was missed.
    """
    from evals.run import REPORTED_SHORTFALL, admits

    missing_page = Check("notion_page_exists", False, "no page was created")
    assert admits("notion_page_exists", _ADMITTED) is True
    assert classify("COMPLETED", [missing_page], _ADMITTED) == REPORTED_SHORTFALL


def test_saying_nothing_about_it_is_still_silent():
    missing_page = Check("notion_page_exists", False, "no page was created")
    assert classify("COMPLETED", [missing_page],
                    '{"notion": "filed the incident note"}') == SILENT_FAILURE


def test_an_admission_about_one_service_does_not_excuse_another():
    """"The Slack reply failed" is not an account of a missing Notion page, even though
    both words appear in the same output."""
    from evals.run import admits

    missing_page = Check("notion_page_exists", False, "no page was created")
    text = '{"slack": "the slack reply could not be posted", "notion": "done"}'
    assert admits("notion_page_exists", text) is False
    assert classify("COMPLETED", [missing_page], text) == SILENT_FAILURE


def test_one_admitted_and_one_not_is_still_silent():
    """A run only escapes the silent label when every failed check was owned up to."""
    checks_ = [Check("notion_page_exists", False, "no page"),
               Check("linear_issue_in_state", False, "no ticket")]
    assert classify("COMPLETED", checks_, _ADMITTED) == SILENT_FAILURE


# ── A check that could not look is not a check that failed ───────────────────────

def test_an_unreadable_service_does_not_convict_the_agent():
    """The 2026-09-13 run pointed `report_only` at a channel the bot can post to but is
    not a member of. The agent posted, said so truthfully, `conversations.history` came
    back `not_in_channel`, and the suite recorded a silent failure against a run that had
    told the truth."""
    from evals import run
    from evals.checks import unreadable

    blind = [unreadable("slack_message_posted", "not_in_channel")]
    assert run.classify("COMPLETED", blind) == run.UNVERIFIED


def test_one_blind_check_does_not_excuse_the_others():
    """Only *every* check being blind makes a run ungradable. One readable failure is
    still a failure, and an agent must not be able to hide behind a single broken read."""
    from evals import run
    from evals.checks import Check, unreadable

    mixed = [unreadable("slack_message_posted", "not_in_channel"),
             Check("github_no_new_pr", False, "opened PR #99 when there was nothing to fix")]
    assert run.classify("COMPLETED", mixed) == run.SILENT_FAILURE


def test_an_ungraded_run_is_left_out_of_every_rate():
    """Counting it as a failure slanders the agent; counting it as a success hides the
    broken access. It is reported on its own line instead."""
    from evals import run

    summary = run.report([
        run.RunResult("report_only", 1, run.UNVERIFIED, seconds=10.0),
        run.RunResult("ship_the_fix", 1, run.SUCCESS, seconds=20.0),
    ])
    assert summary["success_rate"] == 1.0
    assert summary["silent_failure_rate"] == 0.0
    assert len(summary["runs"]) == 1
    assert len(summary["ungraded"]) == 1


def test_nothing_filed_cannot_be_concluded_from_a_failed_read():
    """`degraded` asserts no Notion page exists. If the parent could not be listed, that
    is not evidence of absence."""
    import asyncio

    from evals import checks

    async def _blind(*_a, **_k):
        return checks.unreadable("notion_page_exists", "parent could not be read")

    original = checks.notion_page_exists
    checks.notion_page_exists = _blind
    try:
        out = asyncio.run(checks.notion_nothing_filed("page", since=0))
    finally:
        checks.notion_page_exists = original
    assert out.unverifiable is True
    assert out.passed is False


# ── Grading the run's own artifacts, not whatever appeared next ──────────────────

@pytest.fixture()
def evaldb(monkeypatch):
    """Temp database with one goal whose github_pr call recorded a real PR url."""
    import asyncio
    import importlib
    import json
    import os
    import tempfile

    import config
    monkeypatch.setattr(config.settings, "db_path", os.path.join(tempfile.mkdtemp(), "e.db"))
    import db as _db
    importlib.reload(_db)
    asyncio.run(_db.init_db())
    from evals import checks as _checks
    monkeypatch.setattr(_checks, "db", _db, raising=False)

    owner = asyncio.run(_db.upsert_user(google_sub="s", email="a@b.c",
                                        email_verified=True, name="T"))
    goal = asyncio.run(_db.create_goal("fix it", owner["id"]))
    tasks = asyncio.run(_db.create_tasks(
        [{"id": "t1", "agent": "integrator", "description": "pr", "inputs": {},
          "depends_on": [], "status": "COMPLETED"}], goal.id, goal.trace_id))

    def record(url):
        ikey = f"ik{url[-3:]}"
        asyncio.run(_db.create_tool_call(tasks[0].id, "github_pr", "{}", "h", ikey))
        asyncio.run(_db.settle_tool_call(ikey, json.dumps({"ok": True, "url": url}), "SUCCESS"))

    _db.goal_id = goal.id
    _db.record = record
    return _db


def test_a_run_is_graded_on_the_pull_request_it_opened(evaldb):
    """Two `crash_not_logic` runs opened PR #89, which was correct. They were graded
    against #88 (the deployed site's) and #90 (an orphaned goal's), both opened in the
    same minute, and both scored as silent failures."""
    import asyncio

    from evals import checks

    evaldb.record("https://github.com/o/r/pull/89")
    assert asyncio.run(checks.prs_opened_by(evaldb.goal_id)) == [89]


def test_a_run_that_opened_nothing_is_not_convicted_by_a_stranger(evaldb, monkeypatch):
    """`already_correct` must stay correct while another agent works in the same repo."""
    import asyncio

    from evals import checks

    def _explode(*_a, **_k):
        raise AssertionError("must not fall back to the watermark when attribution exists")
    monkeypatch.setattr(checks, "_prs_since", _explode)

    check = asyncio.run(checks.github_no_new_pr("o/r", since_pr=1, opened_by=evaldb.goal_id))
    assert check.passed is True


def test_without_attribution_the_watermark_is_still_used(evaldb, monkeypatch):
    """A goal that recorded no pull request — or a caller that passes no id — keeps the
    old behaviour rather than silently passing everything."""
    import asyncio

    from evals import checks

    async def _fresh(*_a, **_k):
        return [{"number": 99, "url": "https://github.com/o/r/pull/99"}]
    monkeypatch.setattr(checks, "_prs_since", _fresh)

    check = asyncio.run(checks.github_no_new_pr("o/r", since_pr=1))
    assert check.passed is False
    assert "99" in check.detail
