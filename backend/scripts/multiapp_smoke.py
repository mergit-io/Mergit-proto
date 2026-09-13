"""Prove the four apps are actually connected, before an agent depends on them.

Every credential problem in a multi-app agent looks identical from the outside: the goal
runs, a task fails, and the log says something unhelpful about a token. This does the
boring half of that diagnosis up front — one read call per service, then, with --write,
one real write per service — and reports which of them a live goal can currently use.

    .venv/bin/python scripts/multiapp_smoke.py
    .venv/bin/python scripts/multiapp_smoke.py --write --channel '#eng-bugs' --team ENG

Read mode touches nothing. Write mode posts a real Slack message, creates a real Linear
issue and creates a real Notion page, and says so before it does it — run it against a
workspace you do not mind writing to.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools.linear_ops as linear  # noqa: E402
import tools.notion_ops as notion  # noqa: E402
import tools.service_client as svc  # noqa: E402
import tools.slack_ops as slack  # noqa: E402
from tools.credential_request import WAITING_CREDENTIAL_SENTINEL  # noqa: E402

OK, BAD, SKIP = "\033[32m  ok \033[0m", "\033[31m FAIL\033[0m", "\033[33m skip\033[0m"


def line(status: str, label: str, detail: str = "") -> None:
    print(f"[{status}] {label:<34} {detail}")


def _failed(result: dict) -> str:
    """The reason this result is not a success, or "" if it is one."""
    if result.get(WAITING_CREDENTIAL_SENTINEL):
        return f"no credential — {result.get('message', '')}"
    if not result.get("ok"):
        return str(result.get("error", "unknown error"))[:160]
    return ""


async def check_slack(write: bool, channel: str) -> bool:
    if not svc.deployment_token("slack"):
        line(SKIP, "slack", "SLACK_BOT_TOKEN not set (or connect Slack in the UI)")
        return False

    res = await slack.slack_list_channels({})
    err = _failed(res)
    if err:
        line(BAD, "slack list channels", err)
        return False
    names = ", ".join(c["name"] for c in res["channels"][:6]) or "none visible"
    line(OK, "slack list channels", f"{res['count']} visible: {names}")

    if not channel:
        return True
    read = await slack.slack_read_channel({"channel": channel, "limit": 5})
    err = _failed(read)
    if err:
        line(BAD, f"slack read {channel}", err)
        return False
    line(OK, f"slack read {channel}", f"{len(read['messages'])} recent messages")

    if write:
        posted = await slack.slack_post_message(
            {"channel": channel, "text": "Mergit smoke test — connection verified."})
        err = _failed(posted)
        if err:
            line(BAD, "slack post message", err)
            return False
        line(OK, "slack post message", posted.get("url") or "(posted, no permalink)")
    return True


async def check_linear(write: bool, team: str) -> bool:
    if not svc.deployment_token("linear"):
        line(SKIP, "linear", "LINEAR_API_KEY not set")
        return False

    res = await linear.linear_list_teams({})
    err = _failed(res)
    if err:
        line(BAD, "linear list teams", err)
        return False
    keys = ", ".join(t["key"] for t in res["teams"]) or "none"
    line(OK, "linear list teams", f"{keys}")

    team = team or (res["teams"][0]["key"] if res["teams"] else "")
    if not team:
        line(BAD, "linear", "the API key can see no teams")
        return False

    states = await linear.linear_list_states({"team": team})
    err = _failed(states)
    if err:
        line(BAD, f"linear states {team}", err)
        return False
    line(OK, f"linear states {team}", ", ".join(s["name"] for s in states["states"]))

    if write:
        made = await linear.linear_create_issue(
            {"team": team, "title": "Mergit smoke test",
             "description": "Created by scripts/multiapp_smoke.py. Safe to delete."})
        err = _failed(made)
        if err:
            line(BAD, "linear create issue", err)
            return False
        line(OK, "linear create issue", f"{made['identifier']} {made['url']}")

        back = await linear.linear_get_issue({"issue": made["identifier"]})
        err = _failed(back)
        if err:
            line(BAD, "linear read back", err)
            return False
        # The read-back is the whole point: a mutation that returns success and a row that
        # does not exist are distinguishable only from the other side of the API.
        line(OK, "linear read back", f"state={back['state']} title={back['title']!r}")
    return True


async def check_notion(write: bool) -> bool:
    if not svc.deployment_token("notion"):
        line(SKIP, "notion", "NOTION_API_KEY not set")
        return False

    res = await notion.notion_search({"limit": 5})
    err = _failed(res)
    if err:
        line(BAD, "notion search", err)
        return False
    if not res["results"]:
        line(BAD, "notion search",
             "0 results — nothing has been shared with the integration. Open the page, "
             "••• → Connections → add Mergit.")
        return False
    line(OK, "notion search", "; ".join(f"{r['title']!r}" for r in res["results"][:4]))

    if write:
        made = await notion.notion_create_page(
            {"title": "Mergit smoke test",
             "content": "## Connection check\n\n- Created by scripts/multiapp_smoke.py\n- Safe to delete"})
        err = _failed(made)
        if err:
            line(BAD, "notion create page", err)
            return False
        line(OK, "notion create page", made["url"])

        back = await notion.notion_get_page({"page_id": made["id"]})
        err = _failed(back)
        if err:
            line(BAD, "notion read back", err)
            return False
        line(OK, "notion read back", f"title={back['title']!r}")
    return True


async def check_github() -> bool:
    from tools.github_client import github_token
    if not github_token():
        line(SKIP, "github", "GITHUB_TOKEN not set (or connect the GitHub App in the UI)")
        return False
    import tools.github_ops as gh
    from config import settings
    repo = settings.github_default_repo
    if not repo or repo == "owner/repo":
        line(BAD, "github", "GITHUB_DEFAULT_REPO is unset or still the placeholder")
        return False
    res = await gh.github_list_dir({"repo": repo, "path": ""})
    err = _failed(res)
    if err:
        line(BAD, f"github read {repo}", err)
        return False
    line(OK, f"github read {repo}", f"{len(res['items'])} entries at the root")
    return True


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="also perform one real write per service")
    ap.add_argument("--channel", default="", help="Slack channel to read (and post to)")
    ap.add_argument("--team", default="", help="Linear team key, e.g. ENG")
    args = ap.parse_args()

    if args.write:
        print("WRITE MODE — this will post a real Slack message, create a real Linear "
              "issue and create a real Notion page.\n")

    results = {
        "github": await check_github(),
        "slack": await check_slack(args.write, args.channel),
        "linear": await check_linear(args.write, args.team),
        "notion": await check_notion(args.write),
    }
    live = [name for name, ok in results.items() if ok]
    print(f"\n{len(live)}/4 apps live: {', '.join(live) or 'none'}")
    # The hackathon brief asks for three. Three is the number that matters, so it is the
    # number the exit code is about.
    if len(live) < 3:
        print("The brief needs at least three. Fill in the missing credentials above.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
