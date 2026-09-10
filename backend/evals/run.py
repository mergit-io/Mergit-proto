"""Run the scenario suite and report what the services say happened.

    .venv/bin/python -m evals.run --runs 3
    .venv/bin/python -m evals.run --scenario ship_the_fix --runs 5
    .venv/bin/python -m evals.run --runs 3 --no-cleanup

Needs a Mergit server running (`EVAL_BASE_URL`, default http://localhost:8010).

The headline number is the **silent-failure rate** — runs the system called COMPLETED that
the services say did not happen. It is reported separately from ordinary failure because
the two cost different things: a loud failure costs a retry, a silent one costs the
ability to believe any run at all.

Every run creates real artifacts. Cleanup is on by default: pull requests are closed and
their branches deleted, Linear issues are cancelled, Notion pages archived. Slack messages
are left alone — deleting them needs a scope this app deliberately does not hold, so the
thread accumulates replies and that is stated rather than hidden.
"""
import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from evals import scenarios as sc  # noqa: E402
from evals.checks import Check  # noqa: E402

#: A goal that has not reached a terminal state by now is counted as a timeout, which is a
#: failure — an agent that never finishes is not distinguishable from one that cannot.
GOAL_TIMEOUT_S = 300
POLL_S = 5

#: What a run can turn out to be. `silent_failure` is the one the suite exists to count.
SUCCESS = "success"
SILENT_FAILURE = "silent_failure"
REPORTED_SHORTFALL = "reported_shortfall"
LOUD_FAILURE = "loud_failure"
PESSIMISTIC = "pessimistic"
SKIPPED = "skipped"

#: Words a run uses when it is owning up to something it could not do.
_ADMISSION = re.compile(
    r"could not|couldn'?t|cannot|can'?t|unable|failed|was not|were not|not created|"
    r"missing|skipped|no .{0,24}(?:was|were) created", re.I)

#: Which service a failed check is about, so an admission can be matched to it. A run that
#: admits a Slack problem has not thereby excused a missing Notion page.
_SUBJECT = {
    "notion": r"notion",
    "linear": r"linear",
    "slack": r"slack",
    "github": r"github|pull request|\bpr\b",
}


def admits(check_name: str, text: str) -> bool:
    """True when `text` owns up to the thing `check_name` found missing.

    Run dcaac2eb is why this exists. The Notion page really was not created, and the
    integrator said so in as many words — "Notion incident note could not be created due to
    missing parent page configuration" — and the goal was still marked COMPLETED. Counting
    that as a silent failure would be wrong twice over: it slanders an agent that was
    honest, and it hides the real defect, which is that a goal reports COMPLETED when a
    stated objective was not met.

    Matched within a segment rather than across the whole blob, so "the PR failed" does not
    excuse a missing Notion page that is mentioned three lines away.
    """
    subject = next((pattern for prefix, pattern in _SUBJECT.items()
                    if check_name.startswith(prefix)), "")
    if not subject:
        return False
    for segment in re.split(r"[.\n]|\",", text or ""):
        if re.search(subject, segment, re.I) and _ADMISSION.search(segment):
            return True
    return False


@dataclass
class RunResult:
    scenario: str
    run: int
    outcome: str
    goal_id: str = ""
    goal_status: str = ""
    seconds: float = 0.0
    checks: list[dict] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[dict]:
        return [c for c in self.checks if not c["passed"]]


async def live_apps() -> set[str]:
    """Which apps a goal could actually use right now, by the same rule the tools use."""
    import tools.service_client as svc
    from tools.github_client import app_configured, github_token

    live = set()
    if github_token() or app_configured():
        live.add("github")
    for provider in ("slack", "linear", "notion"):
        if svc.deployment_token(provider) or svc.oauth_configured(provider):
            live.add(provider)
    return live


async def find_thread(cfg: sc.Config) -> str:
    """The newest thread in the channel, so the suite does not need one pasted in."""
    import tools.slack_ops as slack

    res = await slack.slack_read_channel({"channel": cfg.channel, "limit": 50})
    if not res.get("ok"):
        return ""
    threaded = [m for m in res["messages"] if m.get("reply_count")]
    return threaded[0]["ts"] if threaded else ""


async def reported_text(cfg: sc.Config, goal_id: str) -> str:
    """Everything the run said about itself — the goal output and every task output.

    Read only to tell an honest shortfall from a silent one. It is never used to decide
    whether an artifact exists; that is what the services are for.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        state = (await client.get(f"{cfg.base_url}/api/goals/{goal_id}")).json()
    parts = [str(state.get("output") or ""), str(state.get("error") or "")]
    parts += [str(t.get("output") or "") for t in state.get("tasks", [])]
    return "\n".join(parts)


async def submit_and_wait(cfg: sc.Config, goal: str) -> tuple[str, str, float]:
    """(goal_id, terminal status, seconds). Status is TIMEOUT if it never settles."""
    started = time.time()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{cfg.base_url}/api/goals", json={"goal": goal})
        resp.raise_for_status()
        goal_id = resp.json()["goal_id"]

        while time.time() - started < GOAL_TIMEOUT_S:
            await asyncio.sleep(POLL_S)
            state = (await client.get(f"{cfg.base_url}/api/goals/{goal_id}")).json()
            status = state.get("status", "")
            if status in ("COMPLETED", "FAILED"):
                return goal_id, status, time.time() - started
            # A goal every one of whose tasks is parked will never move on its own, and
            # waiting out the full timeout for it teaches nobody anything.
            tasks = state.get("tasks", [])
            if tasks and all(t["status"] == "WAITING_CREDENTIAL" for t in tasks):
                return goal_id, "WAITING_CREDENTIAL", time.time() - started

    return goal_id, "TIMEOUT", time.time() - started


def classify(goal_status: str, results: list[Check], reported: str = "") -> str:
    """What this run turned out to be.

    The distinction that matters is between a run that failed and said so, and a run that
    failed and reported success. Both are failures; only the second one is dangerous,
    because it is the one nobody goes and checks.

    `reported` is what the run said about itself. A COMPLETED goal that missed an objective
    *and named the one it missed* is a `reported_shortfall`, not a silent failure — the
    defect there is the status, not the honesty.
    """
    if goal_status == "COMPLETED" and not results:
        # Nothing was verified, so nothing is known. Calling that a pass — or an honest
        # shortfall — is the mistake this harness exists to avoid.
        return SILENT_FAILURE

    everything_held = all(c.passed for c in results) if results else False
    if goal_status == "COMPLETED":
        if everything_held:
            return SUCCESS
        unexplained = [c for c in results if not c.passed and not admits(c.name, reported)]
        return SILENT_FAILURE if unexplained else REPORTED_SHORTFALL
    return PESSIMISTIC if everything_held else LOUD_FAILURE


async def cleanup(cfg: sc.Config, results: list[Check]) -> list[str]:
    """Undo what a run created, so the next one starts from the same place."""
    import tools.github_ops as gh
    import tools.linear_ops as linear
    import tools.notion_ops as notion

    done = []
    for check in results:
        pr_number = check.evidence.get("number")
        if pr_number:
            closed = await gh.github_update_pr(
                {"repo": cfg.repo, "pr_number": pr_number, "state": "closed"})
            done.append(f"closed PR #{pr_number}" if closed.get("ok")
                        else f"could not close PR #{pr_number}")
        identifier = check.evidence.get("identifier")
        if identifier:
            moved = await linear.linear_update_issue(
                {"issue": identifier, "state": "Canceled"})
            done.append(f"cancelled {identifier}" if moved.get("ok")
                        else f"could not cancel {identifier}")
        page_id = check.evidence.get("page_id")
        if page_id:
            archived = await notion._call({}, "PATCH", f"/pages/{page_id}",
                                          {"archived": True})
            done.append(f"archived notion {page_id[:8]}" if archived.get("ok")
                        else f"could not archive notion {page_id[:8]}")
    return done


async def run_one(cfg: sc.Config, scenario: sc.Scenario, run_no: int,
                  *, do_cleanup: bool) -> RunResult:
    goal = scenario.goal.format(repo=cfg.repo, channel=cfg.channel, team=cfg.team)
    before = await scenario.before(cfg)

    goal_id, status, seconds = await submit_and_wait(cfg, goal)
    verdicts = await scenario.verify(cfg, before)
    said = await reported_text(cfg, goal_id)

    result = RunResult(
        scenario=scenario.id, run=run_no, outcome=classify(status, verdicts, said),
        goal_id=goal_id, goal_status=status, seconds=round(seconds, 1),
        checks=[asdict(v) for v in verdicts],
    )
    if do_cleanup:
        for line in await cleanup(cfg, verdicts):
            print(f"      cleanup: {line}")
    return result


def report(results: list[RunResult]) -> dict:
    by_scenario: dict[str, list[RunResult]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario, []).append(r)

    print("\n" + "=" * 78)
    print(f"{'scenario':<18}{'runs':>5}{'ok':>5}{'silent':>8}{'said so':>9}{'loud':>6}"
          f"{'median s':>10}")
    print("-" * 78)
    for name, runs in by_scenario.items():
        counted = [r for r in runs if r.outcome != SKIPPED]
        ok = sum(1 for r in counted if r.outcome == SUCCESS)
        silent = sum(1 for r in counted if r.outcome == SILENT_FAILURE)
        said = sum(1 for r in counted if r.outcome == REPORTED_SHORTFALL)
        loud = sum(1 for r in counted if r.outcome == LOUD_FAILURE)
        times = sorted(r.seconds for r in counted) or [0]
        print(f"{name:<18}{len(counted):>5}{ok:>5}{silent:>8}{said:>9}{loud:>6}"
              f"{times[len(times) // 2]:>10.1f}")

    counted = [r for r in results if r.outcome != SKIPPED]
    total = len(counted) or 1
    silent = sum(1 for r in counted if r.outcome == SILENT_FAILURE)
    ok = sum(1 for r in counted if r.outcome == SUCCESS)
    print("-" * 78)
    said = sum(1 for r in counted if r.outcome == REPORTED_SHORTFALL)
    print(f"success rate         {ok}/{len(counted)}  ({100 * ok / total:.0f}%)")
    print(f"SILENT-FAILURE RATE  {silent}/{len(counted)}  ({100 * silent / total:.0f}%)"
          "   ← reported COMPLETED, services say otherwise, run never said so")
    print(f"reported shortfall   {said}/{len(counted)}  ({100 * said / total:.0f}%)"
          "   ← missed an objective and named it; the bug is the COMPLETED status")

    for r in counted:
        if r.failed_checks:
            print(f"\n  {r.scenario} run {r.run} [{r.outcome}] goal={r.goal_id[:8]} "
                  f"status={r.goal_status}")
            for c in r.failed_checks:
                print(f"      {c['name']}: {c['detail']}")

    return {
        "runs": [asdict(r) for r in counted],
        "success_rate": ok / total,
        "silent_failure_rate": silent / total,
        "reported_shortfall_rate": said / total,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=1, help="repetitions per scenario")
    ap.add_argument("--scenario", default="", help="run only this scenario id")
    ap.add_argument("--no-cleanup", action="store_true",
                    help="leave the pull requests, tickets and pages behind")
    ap.add_argument("--out", default="evals/last_run.json")
    args = ap.parse_args()

    cfg = sc.Config()
    chosen = [sc.BY_ID[args.scenario]] if args.scenario else sc.ALL
    live = await live_apps()
    print(f"apps live: {', '.join(sorted(live)) or 'none'}")

    if not cfg.thread_ts and "slack" in live:
        cfg.thread_ts = await find_thread(cfg)
        print(f"thread under test: {cfg.thread_ts or '(none found)'}")

    results: list[RunResult] = []
    for scenario in chosen:
        missing = [a for a in scenario.needs if a not in live]
        if missing:
            print(f"\n-- {scenario.id}: SKIPPED, needs {missing}")
            results.append(RunResult(scenario.id, 0, SKIPPED))
            continue
        present = [a for a in scenario.absent if a in live]
        if present:
            print(f"\n-- {scenario.id}: SKIPPED, only means something while {present} "
                  f"{'is' if len(present) == 1 else 'are'} unreachable")
            results.append(RunResult(scenario.id, 0, SKIPPED))
            continue
        for run_no in range(1, args.runs + 1):
            print(f"\n-- {scenario.id} run {run_no}/{args.runs}")
            result = await run_one(cfg, scenario, run_no, do_cleanup=not args.no_cleanup)
            print(f"   goal={result.goal_status} in {result.seconds}s -> {result.outcome}")
            for c in result.checks:
                print(Check(**c).line())
            results.append(result)

    summary = report(results)
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\nwritten to {args.out}")
    # A silent failure is the one result that must not be shrugged off by a script.
    return 1 if summary["silent_failure_rate"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
