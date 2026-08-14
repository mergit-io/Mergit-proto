"""The fallback chain must not lie about why a call failed.

Two defects motivated this file, both observed on the live deployment while Groq was
rate limiting:

  1. `_FALLBACKS` was walked without checking whether the fallback provider had a key.
     `groq/llama-3.3-70b-versatile` falls back to `anthropic/claude-haiku-4-5-20251001`;
     with no `ANTHROPIC_API_KEY` that raised `AuthenticationError`, which is neither a
     rate limit nor a missing model, so it propagated — and the Groq error that caused
     the fallback was discarded. Every goal failed with "Missing Anthropic API Key" on a
     deployment where the operator had deliberately configured only Groq.

  2. `model_health` was never wired to anything. Nothing called `mark_unhealthy`, so
     `GET /api/config/model-health` reported `all_healthy: true` while every model was
     failing.
"""
import asyncio
import types

import pytest

import llm
import model_health


class _Resp:
    def __init__(self, text="ok"):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=text, tool_calls=None))]


class Recorder:
    """Stands in for litellm.acompletion; replays a scripted outcome per model."""

    def __init__(self, outcomes: dict):
        self.outcomes = outcomes
        self.models: list[str] = []

    async def __call__(self, **kwargs):
        model = kwargs["model"]
        self.models.append(model)
        outcome = self.outcomes.get(model, _Resp())
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


GROQ = "groq/llama-3.3-70b-versatile"
#: Groq's configured fallback. The id changed once already — the catalogue carried the
#: dated form (`claude-haiku-4-5-20251001`) alongside two Claude 3.5 ids the provider had
#: since retired. `test_model_catalog.py` pins this list against `AVAILABLE_MODELS`.
CLAUDE = "anthropic/claude-haiku-4-5"

# Verbatim shapes of the two errors, as litellm raises them.
GROQ_DAILY = Exception(
    "litellm.RateLimitError: RateLimitError: GroqException - Rate limit reached for model "
    "`llama-3.3-70b-versatile`: Limit 100000, Used 100000, Requested 1200. "
    "Please try again in 24h0m0s. Limit tokens per day (TPD)."
)
ANTHROPIC_NO_KEY = Exception(
    "litellm.AuthenticationError: Missing Anthropic API Key - A call is being made to "
    "anthropic but no key is set either in the environment variables or via params."
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    model_health._cooldowns.clear()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    yield
    model_health._cooldowns.clear()


def _call(model=GROQ):
    return asyncio.run(llm.acompletion(model=model, messages=[{"role": "user", "content": "hi"}]))


# ── 1. never call a provider we have no key for ─────────────────────────────────

def test_fallback_to_a_provider_with_no_key_is_not_attempted(monkeypatch):
    rec = Recorder({GROQ: GROQ_DAILY, CLAUDE: ANTHROPIC_NO_KEY})
    monkeypatch.setattr(llm, "_acompletion", rec)

    with pytest.raises(Exception):
        _call()

    assert CLAUDE not in rec.models, (
        "called Anthropic with no ANTHROPIC_API_KEY set — the fallback chain must skip "
        f"providers that have no credentials. Models attempted: {rec.models}"
    )


def test_the_error_raised_is_the_real_cause_not_the_fallbacks(monkeypatch):
    """The operator must be told Groq is rate limited, not that Anthropic has no key."""
    rec = Recorder({GROQ: GROQ_DAILY, CLAUDE: ANTHROPIC_NO_KEY})
    monkeypatch.setattr(llm, "_acompletion", rec)

    with pytest.raises(Exception) as exc:
        _call()

    message = str(exc.value)
    assert "Missing Anthropic API Key" not in message, (
        "the surfaced error blames a provider the operator never configured; "
        f"got: {message[:200]}"
    )
    assert "rate limit" in message.lower() or "tpd" in message.lower(), (
        f"the real cause (Groq daily rate limit) was lost; got: {message[:200]}"
    )


def test_a_configured_fallback_is_still_used(monkeypatch):
    """The guard must not disable fallbacks — only unconfigured ones."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    rec = Recorder({GROQ: GROQ_DAILY, CLAUDE: _Resp("from claude")})
    monkeypatch.setattr(llm, "_acompletion", rec)

    resp = _call()

    assert rec.models == [GROQ, CLAUDE], rec.models
    assert resp.choices[0].message.content == "from claude"


def test_the_primary_model_is_always_attempted(monkeypatch):
    """Even with no key at all, the primary runs so its own error is what surfaces."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    rec = Recorder({GROQ: _Resp()})
    monkeypatch.setattr(llm, "_acompletion", rec)

    _call()

    assert rec.models[0] == GROQ


# ── 2. model_health must reflect reality ────────────────────────────────────────

def test_a_hard_rate_limit_marks_the_model_unhealthy(monkeypatch):
    """`GET /api/config/model-health` claimed all_healthy:true while nothing worked."""
    rec = Recorder({GROQ: GROQ_DAILY, CLAUDE: ANTHROPIC_NO_KEY})
    monkeypatch.setattr(llm, "_acompletion", rec)

    with pytest.raises(Exception):
        _call()

    status = model_health.get_status()
    assert GROQ in status, (
        f"a daily-quota failure left the model registered as healthy; status={status}"
    )
    assert status[GROQ] > 0


def test_an_unhealthy_model_is_skipped_while_cooling_down(monkeypatch):
    """model_health's docstring promises this; nothing implemented it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    model_health.mark_unhealthy(GROQ, 300)

    rec = Recorder({GROQ: GROQ_DAILY, CLAUDE: _Resp("from claude")})
    monkeypatch.setattr(llm, "_acompletion", rec)

    resp = _call()

    assert GROQ not in rec.models, (
        f"called a model that is cooling down; attempted {rec.models}"
    )
    assert resp.choices[0].message.content == "from claude"


def test_when_every_candidate_is_cooling_down_the_least_cold_is_tried(monkeypatch):
    """Cooldowns must degrade throughput, never deadlock the worker into never calling."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    model_health.mark_unhealthy(GROQ, 600)
    model_health.mark_unhealthy(CLAUDE, 90)

    rec = Recorder({GROQ: _Resp("groq"), CLAUDE: _Resp("claude")})
    monkeypatch.setattr(llm, "_acompletion", rec)

    resp = _call()

    assert rec.models, "no model was attempted at all — the chain deadlocked"
    assert rec.models[0] == CLAUDE, f"expected the least-cold model first, got {rec.models}"
    assert resp.choices[0].message.content == "claude"


def test_a_successful_call_does_not_mark_anything_unhealthy(monkeypatch):
    rec = Recorder({GROQ: _Resp()})
    monkeypatch.setattr(llm, "_acompletion", rec)

    _call()

    assert model_health.get_status() == {}


# ── the single-provider deployment ──────────────────────────────────────────────
# The live instance has GROQ_API_KEY and nothing else. Both filters therefore apply to
# the only model it can use, and if they can strip it away the deployment stops working
# entirely rather than degrading.

def test_a_groq_only_deployment_still_calls_groq_after_it_is_marked_unhealthy(monkeypatch):
    """Every fallback is unconfigured and the primary is cooling down. It must still run."""
    model_health.mark_unhealthy(GROQ, 3600)
    rec = Recorder({GROQ: _Resp("recovered")})
    monkeypatch.setattr(llm, "_acompletion", rec)

    resp = _call()

    assert rec.models == [GROQ], (
        f"the only usable model was filtered out and nothing was called: {rec.models}"
    )
    assert resp.choices[0].message.content == "recovered"


def test_a_groq_only_deployment_never_reaches_for_anthropic(monkeypatch):
    """The failure mode that produced 'Missing Anthropic API Key' in production."""
    rec = Recorder({GROQ: GROQ_DAILY})
    monkeypatch.setattr(llm, "_acompletion", rec)

    with pytest.raises(Exception) as exc:
        _call()

    assert rec.models == [GROQ], rec.models
    assert "anthropic" not in str(exc.value).lower()


def test_candidate_selection_never_returns_nothing(monkeypatch):
    """A structural guarantee: `raise first_err` assumes at least one attempt happened."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    for cooling in ([], [GROQ], [CLAUDE], [GROQ, CLAUDE]):
        model_health._cooldowns.clear()
        for m in cooling:
            model_health.mark_unhealthy(m, 300)
        assert llm._candidate_models(GROQ), f"no candidate when cooling={cooling}"


def test_a_soft_rate_limit_does_not_sideline_the_model(monkeypatch):
    """Only hard limits earn a cooldown; a per-minute throttle must not sideline a model
    for minutes when the right response is to wait a couple of seconds."""
    soft = Exception("litellm.RateLimitError: rate_limit_exceeded ... please try again in 1.2s")
    calls = {"n": 0}

    async def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise soft
        return _Resp("second try")

    monkeypatch.setattr(llm, "_acompletion", flaky)

    resp = _call()

    assert resp.choices[0].message.content == "second try"
    assert model_health.get_status() == {}, (
        "a transient per-minute throttle put the model into cooldown"
    )
