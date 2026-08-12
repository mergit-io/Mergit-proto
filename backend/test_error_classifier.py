"""Error classifier tests — the gate that decides whether self-heal fires.

A false positive files a bogus GitHub issue and burns an LLM run; a false negative means a
real bug goes unnoticed. This module had no tests at all before 2026-08-12.
"""
import pytest

import error_classifier

# (error string, expected is_bug, why)
CASES = [
    # ── External failures — never our bug ────────────────────────────────────────
    ("Rate limit reached for model llama-3.3-70b", False, "rate limit"),
    ("Error code: 429 - too many requests", False, "429"),
    ("Reached tokens per day (TPD) limit", False, "daily quota"),
    ("quota exceeded for this project", False, "quota"),
    ("invalid_api_key: incorrect API key provided", False, "bad key"),
    ("AuthenticationError: authentication failed", False, "auth"),
    ("Bad credentials", False, "github token"),
    ("Request timeout after 30s", False, "timeout"),
    ("Connection refused by upstream", False, "network"),
    ("SSL: CERTIFICATE_VERIFY_FAILED", False, "ssl"),
    ("agent researcher did not call submit_result", False, "model behaviour"),
    ("orchestrator failed after 5 attempts", False, "model behaviour"),
    ("Unknown tool: frobnicate", False, "bad plan, not a code bug"),
    ("interpolation failed: missing key t1.output.summary", False, "plan issue"),

    # ── Developer bugs — ours ────────────────────────────────────────────────────
    ('File "agent_runner.py", line 88, in run\n    AttributeError: no attribute', True, "our file"),
    ("KeyError: 'output' in interpolation.py", True, "our file"),
    ("TypeError: unsupported operand type(s) for +: 'int' and 'str'", True, "bug exception"),
    ("IndexError: list index out of range", True, "bug exception"),
    ("AssertionError", True, "bug exception"),
    ("NameError: name 'foo' is not defined", True, "bug exception"),
]


@pytest.mark.parametrize("error,expected,reason", CASES)
def test_classification(error, expected, reason):
    assert error_classifier.is_developer_error(error) is expected, (
        f"{reason}: {error!r} should classify as is_bug={expected}"
    )


def test_external_wins_over_bug_signature():
    """A rate-limited call whose traceback passes through our code is still not our bug."""
    error = 'File "agent_runner.py", line 12\nRateLimitError: rate limit exceeded'
    assert error_classifier.is_developer_error(error) is False


def test_empty_error_is_not_a_bug():
    assert error_classifier.is_developer_error("") is False
    assert error_classifier.is_developer_error(None) is False


def test_classify_returns_summary():
    result = error_classifier.classify("KeyError: 'output' in interpolation.py")
    assert result["is_bug"] is True
    assert result["summary"]
    assert len(result["summary"]) <= 200


def test_classify_summary_skips_file_lines():
    error = 'Traceback:\n  File "worker.py", line 3, in run\nValueError: bad value'
    assert error_classifier.classify(error)["summary"] == "ValueError: bad value"
