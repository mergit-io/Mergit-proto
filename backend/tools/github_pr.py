import asyncio
import logging
import re

import language
from tools.github_client import (
    TOKEN_MISSING,
    client as _client,
    credential_check,
    github_token,
    resolve_repo,
)

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


#: Language detection lives in `language.py` — `agent_runner` needs the same answers
#: for a different failure (a coder asked for Rust that submits Python).
_EXT_LANG = language.EXT_LANG
_LANG_EXT = language.LANG_EXT
_language_scores = language.language_scores


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
        actual = language.detect_language(f.get("content") or "", expected=expected)
        if actual is None:
            continue  # corroborated, unsignposted or ambiguous — say nothing
        problems.append(
            f"{path} is named as {expected} but the content is {actual} "
            f"(it belongs in a {_LANG_EXT[actual]} file)"
        )
    return problems


#: What a model writes when it has been asked to commit content it was never given.
_PLACEHOLDER_CONTENT = re.compile(
    r"(?:replace\s+(?:this\s+)?with|insert\s+the|your\s+\w+\s+here|"
    r"actual\s+(?:file\s+)?(?:content|code)|file\s+content\s+here|placeholder)", re.I)


def _placeholder_contents(files) -> list[str]:
    """Paths whose whole content is a note standing in for the content.

    Live failure, PR #35. The integrator was never handed the coder's Rust, so it
    committed the words it would have used to ask for it:

        auth.rs  +1 -0
        +TODO: replace with actual file content

    Nothing objected. It is not empty; it is a new file, so nothing is lost or displaced;
    and it shows no marker of any language, which `_language_mismatches` treats as "no
    opinion" by design — that silence is what stops it refusing real stubs.

    Only files SHORT enough to be nothing but the note are examined. A working file that
    happens to contain a TODO is ordinary — the original `auth.py` opens with one — so
    the phrase has to be essentially the entire file, not a line in it.
    """
    problems = []
    for f in files:
        lines = [ln.strip() for ln in (f.get("content") or "").splitlines() if ln.strip()]
        if not lines or len(lines) > 3:
            continue  # long enough to be real work; a TODO inside it is just a comment
        if any(_PLACEHOLDER_CONTENT.search(ln) for ln in lines):
            problems.append(f"{f['path']} contains only a placeholder: {lines[0][:60]!r}")
    return problems


#: A function body that exists only to say it was never written. The note "# TODO: fix
#: this later" is ordinary in working code and is deliberately NOT matched — only a call
#: that panics or raises the moment it runs.
_UNIMPLEMENTED = re.compile(r"\b(?:todo!|unimplemented!)\s*\(|"
                            r"\braise\s+NotImplementedError\b")


def _unimplemented_stubs(files) -> list[str]:
    """Paths whose content leaves functions unimplemented.

    Live failure, PR #39. Forty-seven lines of Rust that compile cleanly and run — the
    login path works because it never calls the three `todo!()` functions sitting beside
    it. `hash_password` and `validate_password_strength` are panics, on a goal that asked
    for the authentication to be made secure.

    Compiling is not the bar; a stub compiles. This is the placeholder guard one level
    deeper: there, the whole file stood in for content, here a function does.
    """
    problems = []
    for f in files:
        hits = _UNIMPLEMENTED.findall(f.get("content") or "")
        if hits:
            problems.append(f"{f['path']} leaves {len(hits)} function(s) unimplemented "
                            f"({hits[0].strip()})")
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


def _same_file_name(name: str) -> str:
    """A filename reduced to what an agent cannot plausibly have meant differently.

    `merge_sort.py`, `MergeSort.py` and `mergesort.py` all reduce to `mergesort.py`. Case
    and word separators are the two things a model changes while believing it is naming
    the same file; anything beyond that is a different name and none of this guard's
    business.
    """
    return name.lower().replace("_", "").replace("-", "").replace(" ", "")


def _find_by_name(repo, name: str, ref: str, exclude: str = "") -> str | None:
    """An existing root-level path that means the same filename as `name`.

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
    target = _same_file_name(name)
    for e in entries:
        if getattr(e, "type", "") != "file" or e.path == exclude:
            continue
        if _same_file_name(e.path) == target:
            return e.path
    return None


def _misplaced_new_files(repo, files, ref) -> list[str]:
    """Paths being CREATED that mean a file the repository already has.

    `_dropped_definitions` only protects files that already exist, so aiming at a path
    that does NOT exist slips past it entirely: the failure becomes a brand-new file
    rather than a truncated one, and the PR still opens green.

    Seen three times, and the first version of this guard only caught one of them. It
    compared filenames for equality, which catches `main/mergesort.py` beside the real
    `mergesort.py` — same name, invented directory — and nothing else. It did not catch
    `calculator.py` beside the `calc.py` that had the bug, and in PR #34 it did not catch
    `merge_sort.py` beside `mergesort.py`, twice over: the names are not equal, and the
    check skipped root-level files outright on the theory that a file already at the root
    could not mean a better location. That is true of the DIRECTORY and says nothing about
    the NAME.

    So the comparison now ignores case and word separators, and applies everywhere rather
    than only inside subdirectories. `calc`/`calculator` remains out of reach — that is a
    different word, not a different spelling of the same one.
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
        existing = _find_by_name(repo, name, ref, exclude=path)
        if existing:
            problems.append(f"{path} would be a NEW file, but {existing} already exists")
    return problems


def _guts_the_file(repo, files, ref) -> list[str]:
    """Existing files whose replacement throws away most of what they contain.

    `_dropped_definitions` asks the same question in Python only, by name. PR #34 asked
    for a merge sort fix and rewrote `README.md` from six lines describing the sandbox
    down to one sentence about merge sort. A README has no `def` and no `class`, so
    nothing registered as lost.

    Two conditions have to hold together, because a document being REWRITTEN is ordinary
    work and only a document being EMPTIED is the failure: the replacement keeps under
    half the lines that were there, AND it is under half the length. A rewrite of
    comparable size passes however different its wording. Files under four meaningful
    lines are left alone — there is no proportion worth measuring in three lines, and any
    percentage rule would fire on normal edits to them.
    """
    from github import GithubException
    problems = []
    for f in files:
        try:
            existing = repo.get_contents(f["path"], ref=ref)
        except GithubException:
            continue  # a new file cannot lose anything
        if isinstance(existing, list):
            continue
        try:
            before = existing.decoded_content.decode("utf-8", "replace")
        except Exception:
            continue
        before_lines = [ln.strip() for ln in before.splitlines() if ln.strip()]
        after_lines = [ln.strip() for ln in (f.get("content") or "").splitlines() if ln.strip()]
        if len(before_lines) < 4:
            continue
        kept = sum(1 for ln in before_lines if ln in set(after_lines))
        if kept * 2 < len(before_lines) and len(after_lines) * 2 < len(before_lines):
            problems.append(
                f"{f['path']} would drop from {len(before_lines)} lines to "
                f"{len(after_lines)}, keeping {kept} of them"
            )
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
    _missing = await credential_check(args)
    if _missing:
        return {**_missing,
                "message": _missing.get("message", "") + " (needed to open a pull request)"}

    from github import GithubException

    repo_name = resolve_repo(args)
    title = args["title"]
    body = args["body"]
    head_branch = args["head_branch"]
    files = args.get("files", []) or []

    # CI definitions are refused in code rather than by permission.
    #
    # The Mergit GitHub App deliberately does not declare `workflows:write`: granting every
    # installation the standing right to rewrite CI is a large blast radius for a rare
    # need, and a workflow file is the one thing in a repository that runs with the
    # repository's own secrets. GitHub would reject the commit anyway, but with a 422 that
    # says nothing useful — this says what happened and why.
    blocked = [f.get("path", "") for f in files
               if f.get("path", "").startswith(".github/workflows/")]
    if blocked:
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "refused": True,
                "error": "Mergit is not permitted to modify GitHub Actions workflow files "
                         f"({', '.join(blocked)}). Workflow files run with the repository's "
                         "own secrets, so changing them is left to a human. Put the rest of "
                         "the change in a PR and describe the workflow edit in the body."}

    # A PR with no file changes is rejected by GitHub as "No commits between <base> and
    # <head>" after the branch has already been created, leaving a stray branch behind.
    # Refusing up front keeps the repo clean and gives the agent a reason it can act on.
    if not files:
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": "files[] is empty — a pull request needs at least one changed file. "
                         "Pass files as [{\"path\": ..., \"content\": ...}]."}

    g = await _client(args)
    try:
        upstream = g.get_repo(repo_name)
    except GithubException as e:
        return {"action": "create_pr", "result": None, "url": None,
                "error": f"cannot access repo {repo_name}: {e}", "ok": False}

    base_branch = _resolve_base(upstream, args.get("base_branch"))
    base_sha = upstream.get_branch(base_branch).commit.sha

    # A pull request has to come from its own branch. PRs #35 and #36 were both opened
    # with head_branch="main", so the commits landed on the fork's default branch —
    # closing #35 did not remove its commit, and #36, opened from the same branch later,
    # still carried #35's auth.rs. Left alone, every PR inherits every earlier run's work
    # and the diff a reviewer sees stops being the change.
    if head_branch == base_branch:
        logger.warning("Refusing PR on %s — head branch equals base branch (%s)",
                       repo_name, base_branch)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": f"head_branch is '{head_branch}', which is the base branch. A pull "
                         "request needs its own branch, or the commits land on the default "
                         "branch and every later pull request carries them too. Use a "
                         "descriptive branch name such as 'fix/<what-you-changed>'."}

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

    placeholders = _placeholder_contents(files)
    if placeholders:
        logger.warning("Refusing PR on %s — placeholder content: %s", repo_name, placeholders)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": f"{'; '.join(placeholders)}. That is a note describing the content, "
                         "not the content. If you were not given the code to commit, say so "
                         "— do not open a pull request that asks the reader to fill it in."}

    stubs = _unimplemented_stubs(files)
    if stubs:
        logger.warning("Refusing PR on %s — unimplemented stubs: %s", repo_name, stubs)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": f"{'; '.join(stubs)}. A function that panics the moment it is "
                         "called is not an implementation, and compiling is not the bar — "
                         "a stub compiles. Write the body, or leave the function out of "
                         "the pull request entirely."}

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
    gutted = _guts_the_file(upstream, files, base_branch)
    if gutted:
        logger.warning("Refusing PR on %s — replacement empties the file: %s", repo_name, gutted)
        return {"action": "create_pr", "result": None, "url": None, "ok": False,
                "error": f"{'; '.join(gutted)}. files[].content replaces the ENTIRE file, and "
                         "most of what is in this one would simply disappear. If you meant to "
                         "change part of it, read the file and send it back complete with your "
                         "change applied. If you did not mean to touch it at all, leave it out "
                         "of the request."}

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

    # `g.get_user()` needs a token that HAS a user. An installation token does not — it
    # authenticates as the app, and this call fails against it. So the fork path (and only
    # the fork path) runs on the user-to-server token, which means a fork is attributed to
    # the human rather than to the Mergit app. That is worth stating in the UI: it is the
    # difference between "Mergit opened a PR" and "you opened a PR, via Mergit".
    #
    # Falls back to the same client when no separate user token is available, which is the
    # single-tenant PAT case where they are the same thing anyway.
    try:
        gu = await _client(args, as_user=True)
    except Exception:
        gu = g
    me = gu.get_user()
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
