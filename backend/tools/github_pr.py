import asyncio
import logging
import re

from tools.github_client import TOKEN_MISSING, client as _client, github_token, resolve_repo

logger = logging.getLogger(__name__)

# A definition at column zero. Nested ones are indented and deliberately not matched —
# this is about what a file exports, not everything it contains.
_TOP_LEVEL_DEF = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", re.MULTILINE)


def _defined_names(source: str) -> set[str]:
    return set(_TOP_LEVEL_DEF.findall(source))


def _dropped_definitions(repo, files, ref) -> list[str]:
    """Paths whose replacement content silently deletes definitions they already have.

    files[].content replaces the WHOLE file. An agent that returns only the function it
    changed therefore fixes one thing and deletes everything else in that file, and the
    PR still opens green. Observed on llama-3.3-70b: it fixed spread() and dropped
    median() and the module docstring in the same commit.

    Checked against the base ref before anything is committed, so a refusal leaves no
    branch and no partial commit behind.
    """
    from github import GithubException
    problems = []
    for f in files:
        try:
            existing = repo.get_contents(f["path"], ref=ref)
        except GithubException:
            continue  # a path that does not exist yet cannot lose anything
        if isinstance(existing, list):
            continue  # a directory, not a file
        try:
            before = existing.decoded_content.decode("utf-8", "replace")
        except Exception:  # binary, or an API shape without content — nothing to compare
            continue
        lost = _defined_names(before) - _defined_names(f["content"])
        if lost:
            problems.append(f"{f['path']} would lose: {', '.join(sorted(lost))}")
    return problems


def _empty_contents(files) -> list[str]:
    """Paths whose content is empty or only whitespace.

    A fix is never an empty file. This shipped: a coder handed a path that did not exist
    submitted `code: ""`, the integrator interpolated it into `files[].content`, and the
    PR added an empty `main/mergesort.py` — green, and fixing nothing.
    """
    return [f["path"] for f in files if not (f.get("content") or "").strip()]


#: Syntax that only appears in one language, keyed by the language it belongs to. Used to
#: decide what a blob of source IS, never to decide whether it is any good.
_LANG_MARKERS: dict[str, tuple[re.Pattern, ...]] = {
    "Python": (
        re.compile(r"^\s*(?:async\s+)?def\s+\w+\s*\(", re.M),
        re.compile(r"^\s*class\s+\w+", re.M),
        re.compile(r"^\s*(?:import\s+\w|from\s+[\w.]+\s+import\s)", re.M),
        re.compile(r"^\s*print\(", re.M),
        re.compile(r"^\s*(?:if|for|while|with|elif|else|try|except)\b[^\n]*:\s*$", re.M),
    ),
    "Rust": (
        re.compile(r"^\s*use\s+[\w:]+\s*;", re.M),
        re.compile(r"\bfn\s+\w+\s*\("),
        re.compile(r"\blet\s+(?:mut\s+)?\w+\s*(?::|=)"),
        re.compile(r"^\s*(?:impl|pub\s+fn|#\[derive)", re.M),
        re.compile(r"\bprintln!\s*\("),
    ),
    "Go": (
        re.compile(r"^\s*package\s+\w+", re.M),
        re.compile(r"\bfunc\s+\w*\s*\("),
        re.compile(r"\w+\s*:=\s*"),
        re.compile(r"\bfmt\.\w+\("),
    ),
    "JavaScript": (
        re.compile(r"\bfunction\s+\w*\s*\("),
        re.compile(r"^\s*(?:const|let|var)\s+\w+\s*=", re.M),
        re.compile(r"=>"),
        re.compile(r"\b(?:module\.exports|console\.log)\b"),
    ),
    "Java": (
        re.compile(r"\b(?:public|private)\s+(?:static\s+)?(?:class|void|int|String)\b"),
        re.compile(r"\bSystem\.out\.print"),
        re.compile(r"^\s*package\s+[\w.]+\s*;", re.M),
    ),
}

#: Only extensions whose language is unambiguous. `.ts`, `.h` and friends are left out on
#: purpose — a wrong refusal costs more than a missed one.
_EXT_LANG = {".py": "Python", ".rs": "Rust", ".go": "Go", ".js": "JavaScript",
             ".mjs": "JavaScript", ".java": "Java"}

_LANG_EXT = {"Python": ".py", "Rust": ".rs", "Go": ".go",
             "JavaScript": ".js", "Java": ".java"}


def _language_scores(source: str) -> dict[str, int]:
    """How many distinct markers of each language the source shows."""
    return {lang: sum(1 for pat in pats if pat.search(source))
            for lang, pats in _LANG_MARKERS.items()}


def _language_mismatches(files) -> list[str]:
    """Paths whose content is confidently a different language than their extension.

    PR #32. The goal was "migrate auth.py to Rust", so the coder wrote Rust — and returned
    `path: "auth.py"`, the path it had been given. The integrator committed Rust source
    into a `.py` file, producing something that is neither runnable Python nor a buildable
    crate. Nothing else could catch it: the file exists, so it reads as a modification
    rather than a misplaced creation; the content is not empty; and the original was a flat
    script with no `def` or `class`, so no definition could be reported as lost.

    Refuses only on an unambiguous verdict — the extension maps to a language the file
    shows NO sign of, while exactly one other language shows at least two distinct markers.
    A stub, a constants file, an unknown extension, or a docstring quoting another language
    all fall short of that and are left alone.
    """
    problems = []
    for f in files:
        path = f["path"]
        dot = path.rfind(".")
        expected = _EXT_LANG.get(path[dot:].lower()) if dot > 0 else None
        if expected is None:
            continue
        scores = _language_scores(f.get("content") or "")
        if scores.get(expected, 0):
            continue  # it looks like what the name promises
        strong = [lang for lang, n in scores.items() if n >= 2 and lang != expected]
        if len(strong) != 1:
            continue  # no signal, or an ambiguous one — say nothing
        actual = strong[0]
        problems.append(
            f"{path} is named as {expected} but the content is {actual} "
            f"(it belongs in a {_LANG_EXT[actual]} file)"
        )
    return problems


def _significant(source: str) -> str:
    """The source with blank lines and trailing whitespace removed.

    Not a formatter and not a parser — just enough to tell "this diff means something"
    from "this diff is whitespace".
    """
    return "\n".join(line.rstrip() for line in source.splitlines() if line.strip())


def _changes_nothing(repo, files, ref) -> bool:
    """True when not one file in the request would gain a real change.

    Live failure, PR #33 on the sandbox. `mergesort.py` had already been fixed and merged.
    Asked to "check if the code is correct, if not fix it, raise a PR", the pipeline found
    nothing to fix and opened a PR anyway to satisfy the last clause — deleting a single
    blank line, `+0 -1`.

    Every other guard passed it, and each was right to: the content is not empty, it is
    Python under a `.py` path, the file exists so it is not a misplaced creation, and no
    definition is lost. None of them asked whether the diff changes anything, which is the
    one question a pull request has to answer.

    A new file, a missing path or anything unreadable counts as a real change — this only
    reports the case it is certain about. Only an ALL-nothing request is refused: an
    unchanged file resent alongside a genuine fix is untidy, not a lie.
    """
    from github import GithubException
    for f in files:
        try:
            existing = repo.get_contents(f["path"], ref=ref)
        except GithubException:
            return False  # a path that does not exist yet is a real addition
        if isinstance(existing, list):
            return False
        try:
            before = existing.decoded_content.decode("utf-8", "replace")
        except Exception:
            return False  # binary or an unreadable shape — do not second-guess it
        if _significant(before) != _significant(f.get("content") or ""):
            return False
    return True


def _find_by_name(repo, name: str, ref: str) -> str | None:
    """An existing root-level path whose filename is `name`, if there is one.

    Root listing only — one API call. A recursive walk would be more thorough and cost a
    request per directory on every PR; the root is where this mistake lands, because an
    agent that invents a location invents a shallow one.
    """
    from github import GithubException
    try:
        entries = repo.get_contents("", ref=ref)
    except GithubException:
        return None
    if not isinstance(entries, list):
        return None
    for e in entries:
        if getattr(e, "type", "") == "file" and e.path == name:
            return e.path
    return None


def _misplaced_new_files(repo, files, ref) -> list[str]:
    """Paths being CREATED whose filename already exists at the repo root.

    `_dropped_definitions` only protects files that already exist, so aiming at a path
    that does NOT exist slips past it entirely: the failure becomes a brand-new file
    rather than a truncated one, and the PR still opens green.

    Seen twice. `calculator.py` was created beside the `calc.py` that had the bug. Then a
    goal whose text contained a `/tree/main` URL made the orchestrator read the BRANCH as
    a directory, and the PR created `main/mergesort.py` beside the real `mergesort.py`.

    Matching on filename catches both, because an agent that invents a location keeps the
    filename. Only creations are inspected, so a path the agent got right is untouched.
    """
    from github import GithubException
    problems = []
    for f in files:
        path = f["path"]
        try:
            repo.get_contents(path, ref=ref)
            continue  # exists → a modification, not a misplaced creation
        except GithubException:
            pass
        name = path.rsplit("/", 1)[-1]
        if name == path:
            continue  # already at the root; there is no better location it could mean
        existing = _find_by_name(repo, name, ref)
        if existing:
            problems.append(f"{path} would be a NEW file, but {existing} already exists")
    return problems


def _commit_files(repo, files, head_branch, base_sha) -> dict[str, list[str]]:
    """Ensure head_branch exists (from base_sha) and commit files onto it.

    Reports which paths were added versus edited. A fix meant for an existing file that
    lands as an addition is the failure mode where the PR opens green, the issue gets a
    comment, and the bug is still there — untouched, beside a brand-new file. The caller
    surfaces this so the agent and the reviewer can both see it.
    """
    from github import GithubException
    try:
        repo.get_branch(head_branch)
    except GithubException:
        repo.create_git_ref(f"refs/heads/{head_branch}", base_sha)
    created: list[str] = []
    modified: list[str] = []
    for f in files:
        path, content = f["path"], f["content"]
        try:
            existing = repo.get_contents(path, ref=head_branch)
            repo.update_file(path, f"Fix {path}", content, existing.sha, branch=head_branch)
            modified.append(path)
        except GithubException:
            repo.create_file(path, f"Add {path}", content, branch=head_branch)
            created.append(path)
    return {"files_created": created, "files_modified": modified}


def _find_open_pr(upstream, head_label: str, base_branch: str):
    """The PR this call would have created, if a previous attempt already opened it."""
    from github import GithubException
    try:
        for pr in upstream.get_pulls(state="open", base=base_branch, head=head_label):
            return pr
    except GithubException:
        pass
    return None


def _resolve_base(upstream, requested: str | None) -> str:
    """The real base branch. Models routinely guess 'main' on a 'master' repo.

    Checked with a single branch lookup — the previous membership test walked every
    branch in the repository on every PR.
    """
    from github import GithubException
    if requested:
        try:
            upstream.get_branch(requested)
            return requested
        except GithubException:
            logger.info("base branch %r not found on %s — using default %r",
                        requested, upstream.full_name, upstream.default_branch)
    return upstream.default_branch


async def github_pr(args: dict) -> dict:
    if not github_token():
        return {**TOKEN_MISSING, "message": "GitHub personal access token required to create PRs"}

    from github import GithubException

    repo_name = resolve_repo(args)
    title = args["title"]
    body = args["body"]
    head_branch = args["head_branch"]
    files = args.get("files", []) or []

    # A PR with no file changes is rejected by GitHub as "No commits between <base> and
    # <head>" after the branch has already been created, leaving a stray branch behind.
    # Refusing up front keeps the repo clean and gives the agent a reason it can act on.
    if not files:
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": "files[] is empty — a pull request needs at least one changed file. "
                         "Pass files as [{\"path\": ..., \"content\": ...}]."}

    g = _client()
    try:
        upstream = g.get_repo(repo_name)
    except GithubException as e:
        return {"action": "create_pr", "result": None, "url": None,
                "error": f"cannot access repo {repo_name}: {e}", "ok": False}

    base_branch = _resolve_base(upstream, args.get("base_branch"))
    base_sha = upstream.get_branch(base_branch).commit.sha

    # Every check below runs BEFORE any commit, so a refusal leaves no branch and no
    # partial commit behind. Ordered cheapest first: the local ones need no API call.
    empty = _empty_contents(files)
    if empty:
        logger.warning("Refusing PR on %s — empty content for: %s", repo_name, empty)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": f"the content for {', '.join(empty)} is empty. A pull request that "
                         "adds an empty file fixes nothing. If you were handed no code, or "
                         "the file you were told to change does not exist, say that instead "
                         "of opening a pull request — do not commit a placeholder."}

    wrong_language = _language_mismatches(files)
    if wrong_language:
        logger.warning("Refusing PR on %s — content is not the language of the path: %s",
                       repo_name, wrong_language)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": f"{'; '.join(wrong_language)}. Committing one language under "
                         "another's extension leaves a file that neither toolchain can "
                         "build. If you are porting the code, put the new version at a "
                         "path with the right extension and leave the original where it "
                         "is — do not overwrite a file with a different language."}

    misplaced = _misplaced_new_files(upstream, files, base_branch)
    if misplaced:
        logger.warning("Refusing PR on %s — misplaced new file: %s", repo_name, misplaced)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": f"{'; '.join(misplaced)}. You are about to add a second copy of that "
                         "file in a new directory instead of changing the one that is already "
                         "there. Use the existing path. If a path was given to you that starts "
                         "with a branch name such as 'main/', drop that prefix — a branch is "
                         "not a directory."}

    # Refuse before committing anything, so a truncated fix leaves no branch behind.
    # The message names what would be lost because the agent has to send the whole file
    # to fix it, and "invalid content" would not tell it that.
    dropped = _dropped_definitions(upstream, files, base_branch)
    if dropped:
        logger.warning("Refusing PR on %s — replacement content drops definitions: %s",
                       repo_name, dropped)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": "files[].content replaces the ENTIRE file, and this content "
                         f"would delete code that is already there — {'; '.join(dropped)}. "
                         "Read the file, apply your change to it, and send the complete "
                         "file back. Do not send only the part you changed."}

    if _changes_nothing(upstream, files, base_branch):
        logger.warning("Refusing PR on %s — the content matches what is already there", repo_name)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": "every file in this request already contains exactly what you are "
                         "sending, give or take whitespace, so the pull request would change "
                         "nothing. If you checked the code and it is already correct, say that "
                         "— that is a complete and successful answer. A goal that asks for a "
                         "pull request does not require one to exist when there is no fix to "
                         "make."}

    me = g.get_user()
    login = me.login

    # ── Path 1: we have push access → branch + PR directly on the upstream ──
    if getattr(upstream.permissions, "push", False):
        # Seeded before the commit so the already-open-PR branch below can still report
        # what it wrote. The commit happens first; only create_pull fails on a re-run.
        touched: dict[str, list[str]] = {"files_created": [], "files_modified": []}
        try:
            touched = _commit_files(upstream, files, head_branch, base_sha)
            pr = upstream.create_pull(title=title, body=body, head=head_branch, base=base_branch)
            logger.info("PR created directly on %s: %s (added %s, edited %s)", repo_name,
                        pr.html_url, touched["files_created"], touched["files_modified"])
            return {"action": "create_pr", "result": pr.number, "url": pr.html_url,
                    "mode": "direct", "ok": True, **touched}
        except GithubException as e:
            # Re-running a task that already opened its PR must not read as a failure.
            existing = _find_open_pr(upstream, f"{upstream.owner.login}:{head_branch}", base_branch)
            if existing is not None:
                logger.info("PR already open on %s: %s (added %s, edited %s)", repo_name,
                            existing.html_url, touched["files_created"], touched["files_modified"])
                return {"action": "create_pr", "result": existing.number, "url": existing.html_url,
                        "mode": "direct", "existing": True, "ok": True, **touched}
            logger.warning("Direct PR on %s failed (%s) — falling back to fork", repo_name, e)

    # ── Path 2: no push access (or direct failed) → autonomous fork-and-PR ──
    fork_full = f"{login}/{upstream.name}"
    try:
        fork = g.get_repo(fork_full)
    except GithubException:
        logger.info("Forking %s → %s", repo_name, fork_full)
        me.create_fork(upstream)
        fork = None
        for _ in range(20):  # forks are async — poll until ready
            await asyncio.sleep(3)
            try:
                fork = g.get_repo(fork_full)
                fork.get_branch(fork.default_branch)
                break
            except GithubException:
                fork = None
        if fork is None:
            return {"action": "create_pr", "result": None, "url": None,
                    "error": f"fork {fork_full} did not become ready in time", "ok": False}

    touched = {"files_created": [], "files_modified": []}
    try:
        # Branch from the UPSTREAM base commit, not from the fork's own default branch.
        # A fork created weeks ago sits at whatever the upstream looked like then, so
        # branching off it produces a PR whose diff reverts every commit landed since.
        # Forks share an object store with the upstream, so the upstream sha is valid here.
        try:
            touched = _commit_files(fork, files, head_branch, base_sha)
        except GithubException:
            logger.warning("Could not branch %s from upstream sha %s — falling back to the "
                           "fork's own %s (the PR may show unrelated changes)",
                           head_branch, base_sha[:8], fork.default_branch)
            touched = _commit_files(fork, files, head_branch,
                                    fork.get_branch(fork.default_branch).commit.sha)

        # Cross-repo PR: head must be "forkowner:branch", opened on the upstream.
        head_label = f"{login}:{head_branch}"
        try:
            pr = upstream.create_pull(title=title, body=body, head=head_label, base=base_branch)
        except GithubException:
            existing = _find_open_pr(upstream, head_label, base_branch)
            if existing is None:
                raise
            logger.info("PR already open via fork %s: %s (added %s, edited %s)", fork_full,
                        existing.html_url, touched["files_created"], touched["files_modified"])
            return {"action": "create_pr", "result": existing.number, "url": existing.html_url,
                    "mode": "fork", "fork": fork_full, "existing": True, "ok": True, **touched}
        logger.info("PR created via fork %s → %s: %s (added %s, edited %s)", fork_full,
                    repo_name, pr.html_url, touched["files_created"], touched["files_modified"])
        return {"action": "create_pr", "result": pr.number, "url": pr.html_url,
                "mode": "fork", "fork": fork_full, "ok": True, **touched}
    except GithubException as e:
        return {"action": "create_pr", "result": None, "url": None,
                "error": f"fork PR failed: {e}", "ok": False}


SCHEMA = {
    "description": "Create a GitHub pull request. Commits files to a new branch, then opens a PR. "
                   "If the token lacks push access to the target repo, it AUTONOMOUSLY forks the "
                   "repo, pushes the branch to the fork, and opens a cross-repo PR upstream. "
                   "The base branch is auto-detected (handles main vs master). Requires at least "
                   "one file in files[]; if the PR already exists it is returned instead of failing.",
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "GitHub repo in 'owner/repo' format (uses GITHUB_DEFAULT_REPO if omitted)"},
        "title": {"type": "string", "description": "PR title"},
        "body": {"type": "string", "description": "PR description/body (markdown)"},
        "head_branch": {"type": "string", "description": "Branch name to create the PR from"},
        "base_branch": {"type": "string", "description": "Target branch (auto-detected from repo default if omitted/wrong)"},
        "files": {
            "type": "array",
            "description": "Files to commit before creating the PR (required, at least one)",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "required": ["title", "body", "head_branch", "files"],
}
