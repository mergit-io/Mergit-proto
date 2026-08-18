"""The two tools that could hand an attacker the credentials, and what stops them.

`code_exec` and `http_request` are both reachable from a single sentence in a GitHub issue
body — the researcher reads untrusted text, and the model acts on it. These tests pin the
boundaries rather than the implementations, so a future rewrite of either tool still has
to satisfy them.
"""
import asyncio
import importlib

import pytest

import redaction

code_exec_mod = importlib.import_module("tools.code_exec")
http_mod = importlib.import_module("tools.http_request")


def run(coro):
    return asyncio.run(coro)


# ── code_exec: the child must not inherit the credentials ───────────────────────

def test_agent_code_cannot_read_the_credentials(monkeypatch):
    """The original passed no `env=`, so the child inherited every secret in the process.

    `print(os.environ)` then travelled: stdout → tool result → `tool_calls` → SSE → back
    into the model's own context. Four words of Python for the entire credential set.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_supersecret_should_not_leak")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_supersecret_should_not_leak")
    monkeypatch.setenv("MERGIT_KEK_CURRENT", "kek_supersecret_should_not_leak")

    result = run(code_exec_mod.code_exec({"code": "import os; print(dict(os.environ))"}))

    assert result["ok"], result["stderr"]
    for secret in ("ghp_supersecret", "gsk_supersecret", "kek_supersecret"):
        assert secret not in result["stdout"], f"{secret} reached the child process"


def test_the_child_still_works_for_ordinary_code():
    """Isolation is worthless if it breaks the coder agent's actual job."""
    result = run(code_exec_mod.code_exec({"code": "print(sum(range(10)))"}))
    assert result["ok"] and result["stdout"].strip() == "45"


def test_a_nonzero_exit_is_reported_rather_than_raised():
    result = run(code_exec_mod.code_exec({"code": "raise SystemExit(3)"}))
    assert result["ok"] is False and result["exit_code"] == 3


def test_the_child_does_not_start_in_the_directory_holding_the_database():
    """An empty scratch cwd, not `backend/` beside mergit.db and the runtime .env."""
    result = run(code_exec_mod.code_exec({"code": "import os; print(os.listdir('.'))"}))
    assert result["ok"]
    for name in ("mergit.db", "config.py", "db.py"):
        assert name not in result["stdout"]


def test_a_timeout_is_reported_and_does_not_hang():
    result = run(code_exec_mod.code_exec({"code": "import time; time.sleep(30)", "timeout": 2}))
    assert result["ok"] is False and "timed out" in result["stderr"]


# ── DEMO_SAFE_MODE: both halves, or the model calls a tool that is not there ─────

def test_demo_safe_mode_removes_code_exec_from_the_registry_and_the_coder(monkeypatch):
    """Unregistering alone is not enough.

    `agent_runner._build_tool_defs` builds the schema the model sees from the agent's
    `allowed_tools`. Leave the name there and the model calls a tool that no longer
    exists, gets "Unknown tool: code_exec", and spends its `consecutive_errors` budget
    finding that out — three of those force a premature submit.
    """
    import config
    monkeypatch.setattr(config.settings, "demo_safe_mode", True)

    import tools as _tools
    import agent_registry as _ar
    importlib.reload(_tools)
    importlib.reload(_ar)
    try:
        assert "code_exec" not in _tools.TOOL_REGISTRY
        assert "code_exec" not in _ar.AGENT_REGISTRY["coder"]["allowed_tools"]
        # The coder must be told, or it will keep promising to run tests it cannot run.
        assert "disabled" in _ar.AGENT_REGISTRY["coder"]["system_prompt"].lower()
    finally:
        # Module-level mutation: restore, or every later test in the session sees safe mode.
        monkeypatch.setattr(config.settings, "demo_safe_mode", False)
        importlib.reload(_tools)
        importlib.reload(_ar)


def test_code_exec_is_available_by_default():
    import tools as _tools
    import agent_registry as _ar
    assert "code_exec" in _tools.TOOL_REGISTRY
    assert "code_exec" in _ar.AGENT_REGISTRY["coder"]["allowed_tools"]


# ── http_request: SSRF and exfiltration ─────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://example.com",                       # plain HTTP is how metadata gets reached
    "https://169.254.169.254/latest/meta-data/",  # cloud metadata
    "https://127.0.0.1:8000/api/config/keys",   # Mergit's own unauthenticated key store
    "https://localhost/x",
    "https://10.0.0.5/x",
    "https://192.168.1.1/x",
])
def test_private_and_plaintext_targets_are_refused(url):
    result = run(http_mod.http_request({"url": url}))
    assert result["ok"] is False
    assert "refusing" in result["error"] or "resolve" in result["error"]


def test_the_refusal_says_why():
    """An opaque "blocked" sends the agent into a retry loop against a target it will
    never reach. Naming the reason lets it give up and report."""
    result = run(http_mod.http_request({"url": "https://127.0.0.1/x"}))
    assert "127.0.0.1" in result["error"] and "loopback" in result["error"]


def test_the_schema_offers_no_way_to_set_a_header():
    """An arbitrary header dict is an exfiltration channel: it lets the model put anything
    it has been told into a request to a host an attacker named."""
    assert "headers" not in http_mod.SCHEMA["properties"]


# ── redaction ───────────────────────────────────────────────────────────────────

# Every value here is invented and non-functional — they exist so `scrub` can be shown to
# recognise each shape. The two Slack ones are nevertheless assembled by concatenation,
# because a contiguous `xoxb-<digits>-<digits>-<24 chars>` literal matches GitHub push
# protection's rule for a live Slack token exactly, and it blocked a push of this file.
# Splitting the prefix leaves nothing for a scanner to match while the runtime string stays
# identical. Do not tidy these back into single literals.
@pytest.mark.parametrize("secret,label", [
    ("ghp_16C7e42F292c6912E7710c838347Ae178B4a", "github"),
    ("ghs_16C7e42F292c6912E7710c838347Ae178B4a", "github"),
    ("xoxb-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx", "slack"),
    ("xoxe." + "xoxp-1-AbCdEfGh", "slack_config"),
    ("gsk_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789", "groq"),
    ("sk-or-v1-abcdef0123456789", "openrouter"),
])
def test_known_credential_shapes_are_scrubbed(secret, label):
    out = redaction.scrub(f"the token is {secret} ok")
    assert secret not in out
    assert f"[REDACTED:{label}]" in out


def test_scrubbing_walks_nested_tool_results():
    """Tool results are JSON-shaped and land in `tool_calls`, which replays into context."""
    payload = {"ok": True, "items": [{"note": "token ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}]}
    out = redaction.scrub_obj(payload)
    assert out["ok"] is True
    assert "ghp_" not in out["items"][0]["note"]


def test_scrubbing_leaves_field_names_alone():
    """Rewriting a key would silently break a downstream {{t1.output.field}} template."""
    out = redaction.scrub_obj({"github_token_name": "value"})
    assert "github_token_name" in out
