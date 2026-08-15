"""Telling what language a blob of source is, and what language a task asked for.

Used in two places for two different failures, both live:

* `tools/github_pr.py` — PR #32 committed Rust into `auth.py`, because nothing tied a
  file's contents to its extension.
* `agent_runner.py` — goal 4ad14cf1 asked the coder to migrate `auth.py` to Rust. Its
  only execution tool is `code_exec`, a Python interpreter, so it could not run Rust. It
  wrote PYTHON instead, ran that successfully, and submitted `success: True`.

Every judgement here is deliberately conservative. It answers "what is this, if it is
obvious" and returns nothing when it is not, because a wrong refusal costs a real fix and
a missed one costs a bad pull request that a human was going to read anyway.
"""
import re

#: Syntax that only appears in one language, keyed by the language it belongs to. Used to
#: decide what a blob of source IS, never to decide whether it is any good.
LANG_MARKERS: dict[str, tuple[re.Pattern, ...]] = {
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
EXT_LANG = {".py": "Python", ".rs": "Rust", ".go": "Go", ".js": "JavaScript",
            ".mjs": "JavaScript", ".java": "Java"}

LANG_EXT = {"Python": ".py", "Rust": ".rs", "Go": ".go",
            "JavaScript": ".js", "Java": ".java"}

#: How a task names a language it wants. `Go` is matched only with a capital G or as
#: "golang", because a lowercase "go" after "to" is the English verb far more often than
#: the language — "to go through the file" must not read as a port to Go.
_TRIGGER = r"\b(?:to|in|into|using|written\s+in|port\s+to|rewrite\s+in)\s+"

#: JavaScript first — otherwise the `java` branch matches its first four letters.
_ASK = re.compile(_TRIGGER + r"(javascript|rust|python|java|golang)\b", re.I)

#: Capital `Go` only, and never bare lowercase: "and go through the file" is English.
_ASK_GO = re.compile(_TRIGGER + r"(Go)\b")

_ASK_NAMES = {"rust": "Rust", "python": "Python", "java": "Java",
              "javascript": "JavaScript", "golang": "Go", "go": "Go"}


def language_scores(source: str) -> dict[str, int]:
    """How many distinct markers of each language the source shows."""
    return {lang: sum(1 for pat in pats if pat.search(source))
            for lang, pats in LANG_MARKERS.items()}


def detect_language(source: str, expected: str | None = None) -> str | None:
    """The language this source obviously is, or None when it is not obvious.

    `expected` is the language something else claims it should be — its extension, or the
    task that asked for it. When the source shows any sign of that language at all, this
    returns None: the claim is corroborated and there is nothing to report.
    """
    scores = language_scores(source)
    if expected and scores.get(expected, 0):
        return None
    strong = [lang for lang, n in scores.items() if n >= 2 and lang != expected]
    return strong[0] if len(strong) == 1 else None


def requested_language(text: str) -> str | None:
    """The language a task description asks for, when it names exactly one as a target.

    Only a language introduced by a trigger word counts — "to Rust", "in Python". So
    "convert the Python module to Rust" reads as Rust, because the source language is
    merely described while the target is the thing being asked FOR. Two different targets
    in one description ("in Python or in Rust") cannot be resolved and return None rather
    than a guess.
    """
    text = text or ""
    found = {_ASK_NAMES[m.group(1).lower()] for m in _ASK.finditer(text)}
    found |= {"Go" for _ in _ASK_GO.finditer(text)}
    return found.pop() if len(found) == 1 else None
