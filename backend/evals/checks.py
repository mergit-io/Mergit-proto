"""Assertions that read the service, not the agent's summary.

Each check answers one question about the outside world and returns a `Check` saying what
it looked for, what it found, and whether that counts. Nothing here consults the goal's
output, the task rows or the tool results — those are the claims under test, and a harness
that graded claims against themselves would agree with every lie.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    #: The service could not be read at all, so this check knows nothing either way.
    #:
    #: Not the same as failing, and the difference is the whole point. The eval run on
    #: 2026-09-13 pointed `report_only` at a channel the bot can post to but is not a
    #: member of: the agent posted correctly and said so, `conversations.history` came
    #: back `not_in_channel`, and the suite recorded a silent failure against a run that
    #: had told the truth. A missing permission is the operator's problem — the same rule
    #: the `needs` mechanism already applies to absent apps — and a harness that blames the
    #: agent for its own blind spot is worse than no harness, because its numbers are
    #: believed.
    unverifiable: bool = False

    def line(self) -> str:
        mark = "pass" if self.passed else ("????" if self.unverifiable else "FAIL")
        return f"  [{mark}] {self.name}: {self.detail}"


def unreadable(name: str, detail: str) -> Check:
    """A check that could not look. Neither a pass nor a failure."""
    return Check(name, False, f"could not verify — {detail}", unverifiable=True)


async def highest_pr_number(repo: str) -> int:
    """The watermark a run is measured against.

    `github_list_prs` returns no timestamp, and guessing which pull request belongs to this
    run would be the one mistake a harness must not make. Pull request numbers are
    monotonic per repository, so "higher than the highest before we started" is exact.
    """
    import tools.github_ops as gh

    prs = await gh.github_list_prs({"repo": repo, "state": "all", "limit": 20})
    if not prs.get("ok"):
        return -1
    return max((p["number"] for p in prs.get("items", [])), default=0)


async def _prs_since(repo: str, since_pr: int) -> list[dict]:
    import tools.github_ops as gh

    prs = await gh.github_list_prs({"repo": repo, "state": "all", "limit": 20})
    if not prs.get("ok"):
        return []
    return sorted((p for p in prs.get("items", []) if p["number"] > since_pr),
                  key=lambda p: p["number"])


async def github_pr_opened(repo: str, *, since_pr: int, must_touch: str,
                           body_must_mention: list[str],
                           body_must_not_mention: list[str] | None = None) -> Check:
    """A pull request exists, changes the right file, and describes the right bug.

    `body_must_not_mention` is the check run 0e067775 earned: PR #47's diff was correct and
    its body was about `average`, a function it never touched. A harness that only asked
    "is there a PR" would have scored that run a success.
    """
    import tools.github_ops as gh

    if since_pr < 0:
        return unreadable("github_pr_opened", "the repository could not be read")
    fresh = await _prs_since(repo, since_pr)
    if not fresh:
        return Check("github_pr_opened", False, "no pull request was opened")

    pr = fresh[0]
    files = await gh.github_get_pr_files({"repo": repo, "pr_number": pr["number"]})
    paths = [f.get("path", "") for f in files.get("files", [])] if files.get("ok") else []
    if must_touch and not any(must_touch in path for path in paths):
        return Check("github_pr_opened", False,
                     f"PR #{pr['number']} does not touch {must_touch} (touched {paths})",
                     {"pr": pr.get("url", "")})

    detail = await gh.github_get_pr({"repo": repo, "pr_number": pr["number"]})
    body = (detail.get("body") or "").lower() if detail.get("ok") else ""
    missing = [w for w in body_must_mention if w.lower() not in body]
    if missing:
        return Check("github_pr_opened", False,
                     f"PR #{pr['number']} body never mentions {missing} — it describes a "
                     f"different problem than the one reported",
                     {"pr": pr.get("url", "")})
    forbidden = [w for w in (body_must_not_mention or []) if w.lower() in body]
    if forbidden:
        return Check("github_pr_opened", False,
                     f"PR #{pr['number']} body claims {forbidden}, which is not this change",
                     {"pr": pr.get("url", "")})

    return Check("github_pr_opened", True, f"PR #{pr['number']} touches {must_touch}",
                 {"pr": pr.get("url", ""), "number": pr["number"]})


async def github_no_new_pr(repo: str, *, since_pr: int) -> Check:
    """No pull request was opened.

    The opposite failure, and a real one: asked to "check the code and fix it if it is
    wrong", an agent that finds nothing wrong can still open an empty pull request to
    satisfy the second clause. `github_pr._changes_nothing` refuses that; this proves the
    refusal reaches the outside world.
    """
    if since_pr < 0:
        return unreadable("github_no_new_pr", "the repository could not be read")
    fresh = await _prs_since(repo, since_pr)
    if fresh:
        # The number goes into evidence so cleanup can close it. Without that, the one
        # scenario whose failure *is* an unwanted pull request leaves it behind, and every
        # later run measures against a repository this suite dirtied.
        return Check("github_no_new_pr", False,
                     f"opened PR #{fresh[0]['number']} when there was nothing to fix",
                     {"pr": fresh[0].get("url", ""), "number": fresh[0]["number"]})
    return Check("github_no_new_pr", True, "no pull request, correctly")


async def linear_issue_in_state(team: str, *, since: int, state: str,
                                description_contains: str = "") -> Check:
    """A ticket exists on the board, in the state claimed, linking what it says it links."""
    import tools.linear_ops as linear

    res = await linear._gql(
        {},
        """query($key: String!) {
             issues(filter: { team: { key: { eq: $key } } }, first: 50) {
               nodes { identifier title description url createdAt state { name } }
             }
           }""",
        {"key": team.upper()},
    )
    if not res["ok"]:
        return unreadable("linear_issue_in_state", res["error"])

    # Sorted here rather than by the server: an `orderBy` whose direction is assumed is a
    # harness that grades last week's ticket as this run's work.
    fresh = sorted((n for n in res["data"]["issues"]["nodes"]
                    if _iso_after(n.get("createdAt"), since)),
                   key=lambda n: n["createdAt"])
    if not fresh:
        return Check("linear_issue_in_state", False, "no Linear issue was created")

    issue = fresh[-1]
    got = (issue.get("state") or {}).get("name", "")
    if got.lower() != state.lower():
        return Check("linear_issue_in_state", False,
                     f"{issue['identifier']} is in {got!r}, not {state!r}",
                     {"issue": issue["url"]})
    if description_contains and description_contains not in (issue.get("description") or ""):
        return Check("linear_issue_in_state", False,
                     f"{issue['identifier']} does not link {description_contains}",
                     {"issue": issue["url"]})
    return Check("linear_issue_in_state", True, f"{issue['identifier']} in {got}",
                 {"issue": issue["url"], "identifier": issue["identifier"]})


async def notion_page_exists(parent_page_id: str, *, since: int,
                             mentions: str = "") -> Check:
    """A page was filed under the parent, and it is about the right thing.

    `mentions` is checked against the title *or* the body. Requiring it in the title
    graded the model's choice of headline: run b502b792 filed a correct incident note
    called "Incident Note: Bug fix in mergit-e2e-sandbox", whose body named `largest`
    throughout, and a title-only check called that a miss.
    """
    import tools.notion_ops as notion

    res = await notion._call({}, "GET", f"/blocks/{notion._page_id(parent_page_id)}/children?page_size=100")
    if not res.get("ok"):
        return unreadable("notion_page_exists", res.get("error", "the parent could not be read"))

    children = [b for b in res.get("results", [])
                if b.get("type") == "child_page" and _iso_after(b.get("created_time"), since)]
    if not children:
        return Check("notion_page_exists", False, "no page was created under the parent")

    newest = sorted(children, key=lambda b: b.get("created_time") or "")[-1]
    title = (newest.get("child_page") or {}).get("title", "")
    page_id = newest.get("id", "")

    if mentions:
        body = await notion.notion_get_page({"page_id": page_id})
        haystack = f"{title}\n{body.get('content', '') if body.get('ok') else ''}".lower()
        if mentions.lower() not in haystack:
            return Check("notion_page_exists", False,
                         f"the page {title!r} never mentions {mentions!r}, so it is not "
                         f"about the bug that was reported",
                         {"page_id": page_id})
    return Check("notion_page_exists", True, f"page {title!r}", {"page_id": page_id})


async def notion_nothing_filed(parent_page_id: str, *, since: int) -> Check:
    """Nothing was written to Notion — for the degraded run, where it is unreachable."""
    check = await notion_page_exists(parent_page_id, since=since)
    if check.unverifiable:
        # "Nothing was filed" cannot be concluded from a page listing we failed to fetch.
        return unreadable("notion_nothing_filed", check.detail)
    if check.passed:
        return Check("notion_nothing_filed", False,
                     "a page was filed in a run where Notion was supposed to be unavailable")
    return Check("notion_nothing_filed", True, "nothing filed, correctly")


async def slack_replied_in_thread(channel: str, thread_ts: str, *, since: int,
                                  must_contain: list[str]) -> Check:
    """The thread that asked for the work carries the answer, with real links in it.

    `must_contain` holds substrings of URLs the run is supposed to have produced. A reply
    that says "done!" and links nothing is the failure this check exists for: the reporter
    still has to go and find out whether anything happened.
    """
    import tools.slack_ops as slack

    thread = await slack.slack_read_thread(
        {"channel": channel, "thread_ts": thread_ts, "limit": 200})
    if not thread.get("ok"):
        return unreadable("slack_replied_in_thread", thread.get("error", "the thread could not be read"))

    fresh = [m for m in thread["messages"] if float(m.get("ts") or 0) > since]
    if not fresh:
        return Check("slack_replied_in_thread", False, "no reply was posted in the thread")

    joined = "\n".join(m["text"] for m in fresh)
    missing = [w for w in must_contain if w not in joined]
    if missing:
        return Check("slack_replied_in_thread", False,
                     f"the reply does not carry {missing} — the reporter still has to go "
                     f"and find out whether anything happened")
    return Check("slack_replied_in_thread", True,
                 f"replied with {len(must_contain)} real links",
                 {"ts": fresh[-1]["ts"]})


async def slack_message_posted(channel: str, *, since: int, must_contain: list[str]) -> Check:
    import tools.slack_ops as slack

    res = await slack.slack_read_channel({"channel": channel, "limit": 30})
    if not res.get("ok"):
        return unreadable("slack_message_posted", res.get("error", "the channel could not be read"))
    fresh = [m for m in res["messages"] if float(m.get("ts") or 0) > since]
    if not fresh:
        return Check("slack_message_posted", False, "nothing was posted")
    joined = "\n".join(m["text"] for m in fresh)
    missing = [w for w in must_contain if w.lower() not in joined.lower()]
    if missing:
        return Check("slack_message_posted", False, f"the message does not mention {missing}")
    return Check("slack_message_posted", True, "posted")


def _iso_after(stamp: Any, since: int) -> bool:
    """True when an ISO-8601 timestamp is later than a unix `since`.

    Anything unparseable counts as *not* fresh. A check that guessed would report an old
    ticket as this run's work, which is the one mistake a harness must not make.
    """
    if not stamp:
        return False
    import datetime
    try:
        text = str(stamp).replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(text).timestamp() > since
    except Exception:
        return False
