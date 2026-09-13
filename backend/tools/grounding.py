"""Does the prose describe the diff it is attached to?

Every existing `github_pr` guard asks whether the *change* is real: is the content empty,
does it drop definitions, does it change anything at all. None of them asks whether the
*description* is true, and on run `0e067775` that turned out to be the gap.

The diff was correct — `biggest = 0` became `biggest = numbers[0]`, exactly the fix the
Slack thread asked for. The PR body said:

    ## Problem
    The `average` function did not handle empty lists properly

`average` was already correct and the diff does not touch it. Every tool returned
`ok: true`, every guard passed, the ticket moved to In Review, and a human reading the pull
request learns something false about why it exists. Nothing was fabricated — the artifact
was simply wrong about itself, which is the failure mode no fabrication guard can see.

What this checks is narrow on purpose, because a wrong refusal costs a real pull request:

* Only **backticked** tokens count. Models backtick code and do not backtick prose, so this
  never has to guess whether an English word was meant as an identifier.
* Only tokens that are the **nearest one before a claim verb** count. In "unlike `total`,
  `largest` now starts from the first element" the claim is about `largest`; `total` is
  context, and a rule that flagged it would be wrong.
* A symbol counts as supported when it is **named in a changed line, or encloses one**. The
  `def largest(...)` line itself is untouched by a fix inside its body, and a check that
  demanded otherwise would reject every real bug fix.
* When the before-content cannot be read for even one file, the check yields nothing. It
  reports only what it is certain of.
"""
import difflib
import re

#: A backticked token: `average`, `average(numbers)`, `calc.py`, `0.0`.
_BACKTICKED = re.compile(r"`([^`\n]{1,80})`")

#: What is left after `average(numbers)` loses its call parentheses.
_IDENTIFIER = re.compile(r"^[A-Za-z_]\w*$")

#: `calc.py`, `src/auth.rs` — a path, not a symbol, and checkable against files[].
_FILENAME = re.compile(r"^[\w./-]+\.[A-Za-z]{1,6}$")

#: A sentence containing one of these is asserting something about the change. Anything
#: else in a PR body is background, and background is allowed to mention untouched code.
_CLAIM_VERB = re.compile(
    r"\b(?:now|no longer|did not|does not|was not|were not|is not|"
    r"fixed|fixes|corrected|corrects|updated|updates|changed|changes|"
    r"added|adds|removed|removes|replaced|replaces)\b", re.I)

#: Backticked tokens that are never a claim about code: literals, types and the words a
#: model reaches for when it is describing a value rather than naming a thing.
_NOT_A_SYMBOL = {
    "true", "false", "none", "null", "ok", "nan", "inf", "self", "cls",
    "int", "str", "float", "bool", "list", "dict", "set", "tuple", "python",
}

#: A top-level definition and the line it starts on.
_DEF = re.compile(r"^(?:async\s+)?(?:def|class|fn|func|function)\s+([A-Za-z_]\w*)", re.M)


def _defs_by_line(source: str) -> list[tuple[int, str]]:
    """[(line index, name)] for every top-level definition, in file order."""
    out = []
    for i, line in enumerate(source.splitlines()):
        m = _DEF.match(line.lstrip())
        if m and (len(line) - len(line.lstrip())) == 0:
            out.append((i, m.group(1)))
    return out


def _enclosing(defs: list[tuple[int, str]], line_no: int) -> str | None:
    """The definition a line belongs to, or None if it sits above the first one."""
    found = None
    for start, name in defs:
        if start <= line_no:
            found = name
        else:
            break
    return found


def touched(before: str, after: str) -> tuple[set[str], set[str]]:
    """(symbols whose body changed, words appearing in changed lines).

    Both halves are needed. A fix inside `largest` never rewrites its `def` line, so the
    symbol has to come from what encloses the change; a renamed constant appears in the
    changed text and belongs to no definition at all.
    """
    b_lines, a_lines = before.splitlines(), after.splitlines()
    b_defs, a_defs = _defs_by_line(before), _defs_by_line(after)

    symbols: set[str] = set()
    words: set[str] = set()

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, b_lines, a_lines).get_opcodes():
        if tag == "equal":
            continue
        for i in range(i1, i2):
            name = _enclosing(b_defs, i)
            if name:
                symbols.add(name)
            words.update(re.findall(r"[A-Za-z_]\w*", b_lines[i]))
        for j in range(j1, j2):
            name = _enclosing(a_defs, j)
            if name:
                symbols.add(name)
            words.update(re.findall(r"[A-Za-z_]\w*", a_lines[j]))

    return symbols, words


def claimed_tokens(body: str) -> list[str]:
    """The backticked tokens this body asserts something about.

    One per claim verb: the backticked token nearest it in the same sentence, on either
    side. Both orders are ordinary English and both are claims — "`average` now returns
    0.0" puts the subject first, "corrected `stats.py`" puts the object after — so a rule
    that only looked backwards would miss half of them.

    Nearest, not all, is what keeps this from over-reporting: in "unlike `total`, `largest`
    now starts from the first element" the assertion is about `largest`, and flagging
    `total` as well would refuse a pull request for describing its own scope.
    """
    claims: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", body or ""):
        spans = [(m.start(), m.end(), m.group(1)) for m in _BACKTICKED.finditer(sentence)]
        if not spans:
            continue
        for verb in _CLAIM_VERB.finditer(sentence):
            def _distance(span, _v=verb):
                start, end, _text = span
                if end <= _v.start():
                    return _v.start() - end
                if start >= _v.end():
                    return start - _v.end()
                return 0  # the verb sits inside the backticks — treat it as touching
            claims.append(min(spans, key=_distance)[2])
    return claims


def normalise(token: str) -> tuple[str, str] | None:
    """(kind, name) for a claimed token — kind is "symbol" or "file" — or None to ignore."""
    token = token.strip()
    # `average(numbers)` and `average()` are claims about `average`.
    token = re.sub(r"\(.*\)$", "", token).strip()
    if not token or token.lower() in _NOT_A_SYMBOL:
        return None
    if _FILENAME.match(token):
        return ("file", token)
    if _IDENTIFIER.match(token):
        return ("symbol", token)
    return None


def unsupported_claims(body: str, before_after: list[tuple[str, str, str]]) -> list[str]:
    """Claims in `body` that the diff does not support.

    `before_after` is [(path, before, after)] for every file in the request. An empty list
    means nothing could be read, and nothing is reported.
    """
    if not before_after or not (body or "").strip():
        return []

    paths = {path for path, _, _ in before_after}
    basenames = {path.rsplit("/", 1)[-1] for path in paths}
    symbols: set[str] = set()
    words: set[str] = set()
    for _path, before, after in before_after:
        s, w = touched(before, after)
        symbols |= s
        words |= w

    problems: list[str] = []
    seen: set[str] = set()
    for token in claimed_tokens(body):
        kind_name = normalise(token)
        if not kind_name:
            continue
        kind, name = kind_name
        if name in seen:
            continue
        if kind == "file":
            if name not in paths and name not in basenames:
                seen.add(name)
                problems.append(
                    f"the description claims something about `{name}`, which this pull "
                    f"request does not change")
        elif name not in symbols and name not in words:
            seen.add(name)
            problems.append(
                f"the description claims something about `{name}`, which this diff does "
                f"not touch")
    return problems
