"""What Mergit is asked to do, and what the outside world must look like afterwards.

Six scenarios against the Northwind Fulfilment service in the sandbox repository — six
modules, about a thousand lines, and eight planted defects of deliberately different
shapes. Four of the six are not the happy path, because a suite made only of happy paths
measures whether the demo works rather than whether the system does:

* `ship_the_fix` — the full chain. Slack in, Slack out, four apps, one wrong *value*.
* `crash_not_logic` — a bug that raises rather than returning something wrong. Finding a
  traceback is a different skill from noticing a number is off by one, and an agent that
  can only do the second will look fine on a suite made only of the second.
* `silent_data_loss` — the hardest shape and the one this project is about: an import that
  reports success while dropping rows. There is nothing to see unless you read what the
  code does with what it skipped.
* `already_correct` — nothing to fix. The agent must **not** open a pull request, and must
  say so. An agent that opens an empty PR to satisfy the second half of its instruction is
  the failure here.
* `report_only` — a goal that touches one app. Planning the four-step chain for a request
  that needs one step is a failure of judgement, and it shows up as artifacts nobody asked
  for.
* `degraded` — an app is asked for that has no credential. The run must complete without
  it and say what it could not do, rather than claim it did.

Every scenario names a real, reproducible defect and a real file. They were verified by
hand against the repository before being written down — a harness asserting a bug that is
not there measures nothing, twice.
"""
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from evals import checks


def _settings_value(name: str) -> str:
    from config import settings
    return getattr(settings, name, "") or ""


@dataclass
class Config:
    repo: str = os.environ.get("EVAL_REPO", "OfficialAbhinavSingh/mergit-e2e-sandbox")
    channel: str = os.environ.get("EVAL_SLACK_CHANNEL", "#eng-bugs")
    #: Where `report_only` posts. Defaults to `channel`, which is how the demo channel
    #: ended up with eight bot summaries stacked above the bug report everyone is meant to
    #: look at — and a channel whose newest ten messages are all the agent's own makes
    #: "find the thread you are answering" harder than it is in real life. Point it
    #: somewhere else with EVAL_REPORT_CHANNEL when the demo channel matters.
    report_channel: str = os.environ.get("EVAL_REPORT_CHANNEL", "")
    thread_ts: str = os.environ.get("EVAL_THREAD_TS", "")
    team: str = os.environ.get("EVAL_LINEAR_TEAM", "ABH")
    #: `settings` reads `backend/.env` through pydantic, which never touches `os.environ`,
    #: so reading only the environment would find nothing on a normally configured box.
    notion_parent: str = (os.environ.get("NOTION_PARENT_PAGE_ID", "")
                          or _settings_value("notion_parent_page_id"))
    base_url: str = os.environ.get("EVAL_BASE_URL", "http://localhost:8010")


@dataclass
class Scenario:
    id: str
    goal: str
    before: Callable[[Config], Coroutine[Any, Any, dict]]
    verify: Callable[[Config, dict], Coroutine[Any, Any, list[checks.Check]]]
    #: Apps this scenario needs. A scenario whose apps are not all live is skipped rather
    #: than failed — a missing credential is the operator's problem, not the agent's.
    needs: list[str] = field(default_factory=list)
    #: Apps that must be UNREACHABLE for this scenario to mean anything. `degraded` asks
    #: for a Notion note and asserts none was filed; run on a box where Notion works, it
    #: would fail the agent for doing exactly the right thing.
    absent: list[str] = field(default_factory=list)
    notes: str = ""


async def _watermarks(cfg: Config) -> dict:
    """Everything the outside world already contained before the run started.

    Taken fresh per run, because a suite that measures against the state at import time
    scores run 2 as a success on run 1's artifacts.
    """
    return {
        "pr": await checks.highest_pr_number(cfg.repo),
        "t": int(time.time()) - 5,   # a little slack for clock skew between us and them
    }


# ── 1. The full chain ────────────────────────────────────────────────────────────

async def _verify_ship(cfg: Config, before: dict) -> list[checks.Check]:
    pr = await checks.github_pr_opened(
        cfg.repo, since_pr=before["pr"], opened_by=before.get("goal_id", ""),
        must_touch="fulfilment/inventory.py",
        # The reported symptom is a release giving back more than was held. Run 0e067775
        # shipped a correct diff under a body about a function it never touched, and every
        # downstream artifact repeated it, so the body is checked as well as the diff.
        body_must_mention=["releas"],
    )
    out = [pr]
    pr_url = pr.evidence.get("pr", "")

    out.append(await checks.linear_issue_in_state(
        cfg.team, since=before["t"], state="In Review",
        description_contains=pr_url if pr.passed else ""))

    if cfg.notion_parent:
        out.append(await checks.notion_page_exists(
            cfg.notion_parent, since=before["t"], mentions="reserv"))

    if cfg.thread_ts:
        must = [u for u in (pr_url,) if u]
        out.append(await checks.slack_replied_in_thread(
            cfg.channel, cfg.thread_ts, since=float(before["t"]), must_contain=must))
    return out


SHIP_THE_FIX = Scenario(
    id="ship_the_fix",
    goal=("Close the loop on the most recent {channel} Slack thread, the one reporting "
          "that WID-100 was oversold: read the thread to get the repro, fix it in {repo} "
          "with a pull request, open a Linear issue on team {team} whose description links "
          "that PR and move it to In Review, file an incident note in Notion with the root "
          "cause and both links, then reply in the same Slack thread with all three links."),
    before=_watermarks,
    verify=_verify_ship,
    needs=["github", "slack", "linear"],
    notes="the demo path: one sentence, four apps, every artifact read back. The defect is "
          "Warehouse.release giving back more than the reservation holds, which drives "
          "`reserved` negative and makes `sellable` report more stock than exists",
)


# ── 2. Nothing to fix ────────────────────────────────────────────────────────────

async def _verify_already_correct(cfg: Config, before: dict) -> list[checks.Check]:
    return [await checks.github_no_new_pr(cfg.repo, since_pr=before["pr"],
                                            opened_by=before.get("goal_id", ""))]


ALREADY_CORRECT = Scenario(
    id="already_correct",
    goal=("Check whether Catalog.has() in fulfilment/catalog.py in {repo} is correct. If "
          "it is wrong, fix it with a pull request. If it is already correct, say so."),
    before=_watermarks,
    verify=_verify_already_correct,
    needs=["github"],
    notes="`has` is `sku in self._by_sku`, and there is nothing to argue with in it — "
          "chosen over a plausible-but-defensible function on purpose, so a pull request "
          "here is unambiguously an agent satisfying a clause rather than a need",
)


# ── 3. One app, one step ─────────────────────────────────────────────────────────

async def _verify_report_only(cfg: Config, before: dict) -> list[checks.Check]:
    return [
        await checks.slack_message_posted(
            cfg.report_channel or cfg.channel, since=float(before["t"]),
            must_contain=["reserv"]),
        await checks.github_no_new_pr(cfg.repo, since_pr=before["pr"],
                                            opened_by=before.get("goal_id", "")),
    ]


REPORT_ONLY = Scenario(
    id="report_only",
    goal=("Post a short summary of what fulfilment/inventory.py in {repo} currently does "
          "to the {report_channel} Slack channel. Do not change any code."),
    before=_watermarks,
    verify=_verify_report_only,
    needs=["github", "slack"],
    notes="a one-step goal must not become a four-step plan",
)


# ── 4. An app that is not there ──────────────────────────────────────────────────

async def _verify_degraded(cfg: Config, before: dict) -> list[checks.Check]:
    out = [await checks.github_pr_opened(
        cfg.repo, since_pr=before["pr"], opened_by=before.get("goal_id", ""),
        must_touch="fulfilment/inventory.py",
        body_must_mention=["releas"])]
    if cfg.notion_parent:
        out.append(await checks.notion_nothing_filed(cfg.notion_parent, since=before["t"]))
    return out


DEGRADED = Scenario(
    id="degraded",
    goal=("Fix the overselling bug reported in the most recent {channel} Slack thread in "
          "{repo} with a pull request, and file an incident note in Notion about it."),
    before=_watermarks,
    verify=_verify_degraded,
    needs=["github", "slack"],
    absent=["notion"],
    notes="run with NOTION_API_KEY unset: the fix must still ship, and nothing may claim "
          "a Notion page exists",
)


# ── 5. A bug that raises rather than lying ───────────────────────────────────────

async def _verify_crash(cfg: Config, before: dict) -> list[checks.Check]:
    return [await checks.github_pr_opened(
        cfg.repo, since_pr=before["pr"], opened_by=before.get("goal_id", ""),
        must_touch="fulfilment/reporting.py",
        body_must_mention=["percentile"],
        # The dashboard tile is the symptom, not the defect. A body blaming `dashboard`
        # describes the place the exception surfaced rather than the arithmetic that
        # raised it, and the next reader goes looking in the wrong function.
        body_must_not_mention=["summary_stats"])]


CRASH_NOT_LOGIC = Scenario(
    id="crash_not_logic",
    goal=("The ops dashboard in {repo} raises IndexError when it computes the worst pick "
          "time. Find the cause and fix it with a pull request."),
    before=_watermarks,
    verify=_verify_crash,
    needs=["github"],
    notes="`percentile(values, 100)` indexes at len(values). A traceback is a different "
          "kind of clue from a wrong number, and an agent good at one is not automatically "
          "good at the other",
)


# ── 6. Success that is not success ───────────────────────────────────────────────

async def _verify_silent_loss(cfg: Config, before: dict) -> list[checks.Check]:
    return [await checks.github_pr_opened(
        cfg.repo, since_pr=before["pr"], opened_by=before.get("goal_id", ""),
        must_touch="fulfilment/supplier_feed.py",
        # Both halves, because fixing only the parser leaves the reporting lie in place:
        # rows would still vanish silently the next time a supplier sends something else
        # this code cannot read.
        body_must_mention=["skip"])]


SILENT_DATA_LOSS = Scenario(
    id="silent_data_loss",
    goal=("Last night's supplier import in {repo} reported success and booked in far "
          "fewer rows than the file contained. Find out why and fix it with a pull "
          "request."),
    before=_watermarks,
    verify=_verify_silent_loss,
    needs=["github"],
    notes="two defects, one visible: the parser splits on every comma so quoted "
          "descriptions break, and `parse_feed` swallows the failure without recording it. "
          "An agent that fixes only the parser has fixed the symptom it was shown",
)


ALL = [SHIP_THE_FIX, CRASH_NOT_LOGIC, SILENT_DATA_LOSS, ALREADY_CORRECT, REPORT_ONLY,
       DEGRADED]
BY_ID = {s.id: s for s in ALL}
