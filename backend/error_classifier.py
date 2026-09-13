"""
Classifies goal/task failures as developer errors (bugs in our code) vs
external errors (rate limits, bad credentials, user input problems).

Developer errors trigger auto-issue + self-heal PR.
External errors are logged but not escalated.
"""
import re

# Patterns that indicate the error came from our own code
_OUR_FILES = re.compile(
    r"(agent_runner|orchestrator|worker|interpolation|tool_call|github_ops|github_pr|"
    r"code_exec|file_ops|web_search|http_request|db\.py|events\.py|tracing\.py)",
    re.IGNORECASE,
)

# Patterns that are definitively external / not our bug
_EXTERNAL_PATTERNS = [
    r"rate.?limit",
    r"429",
    r"tokens per (day|minute)",
    r"tpd|tpm",
    r"daily (quota|limit)",
    r"quota exceeded",
    r"invalid.api.key",
    r"authentication failed",
    r"unauthorized",
    r"bad credentials",
    r"github token",
    r"timeout",
    r"connection (refused|reset|error)",
    r"network",
    r"dns",
    r"ssl",
    r"agent .* did not call submit_result",   # model behaviour, not our bug
    r"orchestrator failed after \d+ attempts", # model behaviour
    r"unknown tool",                           # bad orchestrator plan, not a code bug
    r"interpolation.*missing",                 # plan issue, not a code bug
]

_EXTERNAL_RE = re.compile("|".join(_EXTERNAL_PATTERNS), re.IGNORECASE)

# Python exception types that signal real bugs
_BUG_EXCEPTIONS = re.compile(
    r"(AttributeError|KeyError|IndexError|TypeError|ValueError|AssertionError|"
    r"NameError|ImportError|NotImplementedError|RecursionError|RuntimeError)",
)


def is_developer_error(error: str) -> bool:
    """Return True if the error looks like a bug in omniBox code."""
    if not error:
        return False
    # Anything that's clearly external → not our bug
    if _EXTERNAL_RE.search(error):
        return False
    # Stack trace mentioning our files → our bug
    if _OUR_FILES.search(error):
        return True
    # Python exception types in general (when not from external causes)
    if _BUG_EXCEPTIONS.search(error):
        return True
    return False


def classify(error: str) -> dict:
    """Return {is_bug: bool, reason: str} for the given error string."""
    is_bug = is_developer_error(error)
    if is_bug:
        # Try to extract the most informative line
        lines = error.strip().splitlines()
        summary = next(
            (l.strip() for l in reversed(lines) if l.strip() and not l.strip().startswith("File ")),
            lines[-1].strip() if lines else error[:120],
        )
        return {"is_bug": True, "summary": summary[:200]}
    return {"is_bug": False, "summary": error[:200]}
