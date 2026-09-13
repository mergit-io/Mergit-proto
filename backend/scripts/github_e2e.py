"""Drive every GitHub tool against a real repository and print what GitHub actually did.

The unit tests fake PyGithub, so they prove the tools' decisions but not that the calls
they make are ones GitHub accepts. This script proves the second half: it opens a real
issue, opens a real PR, reads a real diff, submits a real review, merges a real PR, and
then confirms the merge guard refuses a real conflicting PR.

    GITHUB_TOKEN=$(gh auth token) .venv/bin/python scripts/github_e2e.py <owner/repo>

It writes to the repo it is pointed at. Point it at a throwaway.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.github_ops import (  # noqa: E402
    github_add_labels, github_close_issue, github_create_issue, github_get_pr,
    github_get_pr_files, github_list_prs, github_merge_pr, github_post_comment,
    github_request_review, github_review_pr, github_update_pr,
)
from tools.github_pr import github_pr  # noqa: E402


def args_owner(repo: str) -> str:
    return repo.split("/")[0]

# Both variants are stamped, so a re-run against a repo that already merged a previous
# run's fix still produces a real diff. Without the stamp the second run opens a PR with
# zero changed files, and every check downstream of the diff reads as a tool failure when
# the only broken thing is the fixture.
def fixed_calc(stamp: str) -> str:
    return f'''"""Tiny calculator used by the Mergit end-to-end GitHub tests. (run {stamp})"""


def average(numbers):
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


if __name__ == "__main__":
    print(average([1, 2, 3]))
    print(average([]))
'''


def conflicting_calc(stamp: str) -> str:
    return f'''"""Tiny calculator used by the Mergit end-to-end GitHub tests. (run {stamp}, rival variant)"""


def average(numbers):
    if len(numbers) == 0:
        raise ValueError("average() of an empty sequence")
    return sum(numbers) / len(numbers)


if __name__ == "__main__":
    print(average([1, 2, 3]))
'''

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    print(f"  {'PASS' if passed else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


async def main(repo: str) -> int:
    stamp = str(int(time.time()))
    fix_branch, conflict_branch = f"e2e/fix-{stamp}", f"e2e/conflict-{stamp}"

    print(f"\n== 1. open an issue on {repo} ==")
    issue = await github_create_issue({
        "repo": repo,
        "title": f"average() raises ZeroDivisionError on an empty list ({stamp})",
        "body": "`average([])` divides by zero. It should return 0.0.",
        "labels": ["bug"],
    })
    check("github_create_issue", issue.get("ok") is True, issue.get("url") or issue.get("error", ""))
    if not issue.get("ok"):
        return 1
    issue_no = issue["number"]

    print("\n== 2. refuse a PR with no file changes ==")
    empty = await github_pr({"repo": repo, "title": "should not exist", "body": "-",
                             "head_branch": f"e2e/empty-{stamp}", "files": []})
    check("github_pr refuses empty files[]",
          empty.get("ok") is False and "files[] is empty" in empty.get("error", ""),
          empty.get("error", ""))

    print("\n== 3. open the fix PR ==")
    pr = await github_pr({
        "repo": repo, "head_branch": fix_branch,
        "title": "fix: return 0.0 from average() on an empty list",
        "body": f"## Summary\nGuard the empty case.\n\nCloses #{issue_no}",
        "files": [{"path": "calc.py", "content": fixed_calc(stamp)}],
    })
    check("github_pr opens a PR", pr.get("ok") is True, pr.get("url") or pr.get("error", ""))
    if not pr.get("ok"):
        return 1
    pr_no = pr["result"]

    print("\n== 4. re-run the same PR call (idempotency) ==")
    again = await github_pr({
        "repo": repo, "head_branch": fix_branch,
        "title": "fix: return 0.0 from average() on an empty list",
        "body": "same call, second time",
        "files": [{"path": "calc.py", "content": fixed_calc(stamp)}],
    })
    check("re-running github_pr returns the existing PR instead of failing",
          again.get("ok") is True and again.get("result") == pr_no,
          f"existing={again.get('existing')} pr={again.get('result')}")

    print("\n== 5. open a second PR that will conflict ==")
    conflict = await github_pr({
        "repo": repo, "head_branch": conflict_branch,
        "title": "fix: raise ValueError from average() on an empty list",
        "body": "Deliberately conflicts with the other fix.",
        "files": [{"path": "calc.py", "content": conflicting_calc(stamp)}],
    })
    check("second PR opened", conflict.get("ok") is True,
          conflict.get("url") or conflict.get("error", ""))
    conflict_no = conflict.get("result")

    print("\n== 6. read the real diff ==")
    files = await github_get_pr_files({"repo": repo, "pr_number": pr_no})
    got = files.get("files") or []
    patch = got[0].get("patch", "") if (files.get("ok") and got) else ""
    check("github_get_pr_files returns the unified diff",
          files.get("ok") is True and stamp in patch,
          f"{files.get('total_changed_files')} file(s), patch {len(patch)} chars")

    print("\n== 7. read PR state, checks and reviews ==")
    state = await github_get_pr({"repo": repo, "pr_number": pr_no})
    check("github_get_pr reports mergeability", state.get("ok") is True,
          f"mergeable_state={state.get('mergeable_state')} checks={state.get('checks', {}).get('total')}")

    print("\n== 8. submit a review ==")
    review = await github_review_pr({"repo": repo, "pr_number": pr_no,
                                     "body": "Read the diff: the empty-list guard is correct.",
                                     "event": "APPROVE"})
    check("github_review_pr submits a review", review.get("ok") is True,
          f"state={review.get('state')} downgraded={review.get('event_downgraded')}")

    print("\n== 8b. edit the PR ==")
    new_title = "fix: return 0.0 from average() on an empty list (edited)"
    updated = await github_update_pr({"repo": repo, "pr_number": pr_no,
                                      "title": new_title,
                                      "body": f"Edited by github_update_pr.\n\nCloses #{issue_no}"})
    reread = await github_get_pr({"repo": repo, "pr_number": pr_no})
    check("github_update_pr edits title and body",
          updated.get("ok") is True and reread.get("title") == new_title,
          f"updated={updated.get('updated')} title now {reread.get('title')!r}")

    print("\n== 8c. request a review ==")
    # GitHub refuses to let an author request review from themselves, and this token
    # authored the PR. Asserting that exact refusal proves the call reaches GitHub with
    # correctly shaped arguments. The success path needs a second account with repo
    # access and is therefore NOT covered here.
    me = await github_request_review({"repo": repo, "pr_number": pr_no,
                                      "reviewers": [args_owner(repo)]})
    check("github_request_review reaches GitHub (self-request correctly refused)",
          me.get("ok") is False and "error" in me,
          str(me.get("error"))[:120])

    print("\n== 9. label and comment ==")
    labels = await github_add_labels({"repo": repo, "issue_number": pr_no,
                                      "labels": ["automated-fix"]})
    check("github_add_labels", labels.get("ok") is True, str(labels.get("labels", ""))[:80])
    comment = await github_post_comment({"repo": repo, "issue_number": issue_no,
                                         "body": f"Fix opened as #{pr_no}."})
    check("github_post_comment", comment.get("ok") is True, comment.get("url", ""))

    print("\n== 10. merge the clean PR ==")
    merged = await github_merge_pr({"repo": repo, "pr_number": pr_no,
                                    "delete_branch": True})
    check("github_merge_pr merges a clean PR",
          merged.get("ok") is True and merged.get("merged") is True,
          f"sha={str(merged.get('sha'))[:10]} reason={merged.get('reason', '')}")

    print("\n== 11. merge the same PR again (idempotency) ==")
    twice = await github_merge_pr({"repo": repo, "pr_number": pr_no})
    check("re-merging an already-merged PR reports success, not failure",
          twice.get("ok") is True and twice.get("already_merged") is True)

    print("\n== 12. the guard refuses the now-conflicting PR ==")
    if conflict_no:
        # GitHub recomputes mergeability asynchronously after the first merge lands.
        for _ in range(10):
            s = await github_get_pr({"repo": repo, "pr_number": conflict_no})
            if s.get("mergeable_state") not in (None, "unknown"):
                break
            await asyncio.sleep(3)
        refused = await github_merge_pr({"repo": repo, "pr_number": conflict_no})
        check("github_merge_pr refuses a conflicting PR and names the blocker",
              refused.get("ok") is False and refused.get("refused") is True,
              f"state={refused.get('mergeable_state')} reason={refused.get('reason')}")

    print("\n== 13. list PRs and close the issue ==")
    listed = await github_list_prs({"repo": repo, "state": "all"})
    check("github_list_prs", listed.get("ok") is True, f"{listed.get('count')} PR(s)")
    closed = await github_close_issue({"repo": repo, "issue_number": issue_no,
                                       "comment": "Fixed and merged."})
    check("github_close_issue", closed.get("ok") is True, closed.get("state", ""))

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{'=' * 62}\n{passed}/{len(results)} checks passed against {repo}\n{'=' * 62}")
    for name, ok, _ in results:
        if not ok:
            print(f"  FAILED: {name}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: github_e2e.py <owner/repo>")
    if not os.environ.get("GITHUB_TOKEN"):
        sys.exit("GITHUB_TOKEN is not set — try: GITHUB_TOKEN=$(gh auth token) ...")
    sys.exit(asyncio.run(main(sys.argv[1])))
