"""A result that did the work is not a failure because it named its own keys.

Live failure, goal 5981fe39. The integrator called `github_create_issue`, the tool
returned SUCCESS, and GitHub issue #36 exists to this day. The agent then submitted:

    {"issue_number": 36, "issue_title": "...", "status": "created",
     "url": "https://github.com/.../issues/36", ", ": ...}

The integrator schema requires ["action", "result"], neither was present, and the task
failed with `output: None`. The issue number and URL were discarded, the coder behind it
never learned what to fix, and the whole goal reported FAILED — over key names, while the
work sat completed on GitHub.

These tests pin the recovery and, just as importantly, its limits: wrapping only happens
when the payload carries an artifact the agent could not have invented, and the wrapped
object still has to pass every honesty guard. A payload that lies still fails.
"""
import agent_runner as ar

REQUIRED = ["action", "result"]
KNOWN = {"https://github.com/o/r/issues/36"}


def problem(result, known=None):
    return ar._submission_problem(result, REQUIRED, "open an issue about the bug", known)


# ── The recovery ────────────────────────────────────────────────────────────────

def test_payload_with_a_real_artifact_is_accepted():
    """The exact shape from goal 5981fe39."""
    assert problem({
        "issue_number": 36,
        "issue_title": "Biggest issue in the repo",
        "status": "created",
        "url": "https://github.com/o/r/issues/36",
    }, KNOWN) is None


def test_the_wrapped_result_keeps_every_original_field():
    payload = {"issue_number": 36, "url": "https://github.com/o/r/issues/36"}
    wrapped = ar._wrap_bare_payload(dict(payload), REQUIRED)
    assert wrapped is not None
    assert set(REQUIRED) <= set(wrapped)
    # Nothing may be dropped — the issue number is what the next task needs.
    assert wrapped["result"] == payload


def test_a_malformed_key_does_not_stop_the_recovery():
    """The live payload carried a literal ', ' key. The model was assembling the object
    badly, which is the whole reason the envelope was wrong — it is not a reason to bin
    a completed issue."""
    assert problem({
        "issue_number": 36,
        "url": "https://github.com/o/r/issues/36",
        ", ": "",
    }, KNOWN) is None


# ── Its limits ──────────────────────────────────────────────────────────────────

def test_no_artifact_still_fails():
    """Nothing here proves any work happened, so the envelope is all there is to go on."""
    assert problem({"status": "done", "notes": "finished the task"}) is not None


def test_a_wrapped_payload_still_has_to_pass_the_url_guard():
    """`_fabricated_urls` runs on the wrapped object exactly as before. A URL the agent
    invented is not evidence, so it must not buy its way past the envelope check."""
    assert problem({
        "issue_number": 99,
        "url": "https://github.com/o/r/issues/99",
    }, KNOWN) is not None


def test_a_wrapped_payload_still_has_to_pass_the_tool_failure_guard():
    assert problem({
        "url": "https://github.com/o/r/issues/36",
        "outcome": {"ok": False, "error": "404 Not Found"},
    }, KNOWN) is not None


def test_wrapping_does_not_blind_the_claimed_without_artifact_guard():
    """Synthesising an `action` must not read as a produce-action. If it did, a payload
    claiming a PR with no URL anywhere would be waved through by the very step meant to
    rescue honest work."""
    assert problem({"claim": "opened pull request", "pr_url": None}) is not None


def test_an_already_valid_envelope_is_left_alone():
    ok = {"action": "create_issue", "result": {"number": 36},
          "url": "https://github.com/o/r/issues/36"}
    assert ar._wrap_bare_payload(dict(ok), REQUIRED) is None
    assert problem(ok, KNOWN) is None


def test_a_non_dict_is_not_wrapped():
    assert ar._wrap_bare_payload("just a string", REQUIRED) is None
    assert ar._wrap_bare_payload(None, REQUIRED) is None
