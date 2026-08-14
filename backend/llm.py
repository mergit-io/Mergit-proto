import asyncio
import logging
import os
import re
from typing import Any

import litellm
from litellm import acompletion as _acompletion

import model_health
from config import settings

logger = logging.getLogger(__name__)

# Set provider keys for LiteLLM — only set if non-empty to avoid "key=empty-string" confusion
def _setenv(var: str, val: str) -> None:
    if val and var not in os.environ:
        os.environ[var] = val

_setenv("ANTHROPIC_API_KEY", settings.anthropic_api_key)
_setenv("GROQ_API_KEY", settings.groq_api_key)
_setenv("OPENROUTER_API_KEY", settings.openrouter_api_key)

litellm.drop_params = True  # ignore unsupported params per provider

# Fallback chain: when a model hits a hard rate limit (TPD / daily quota),
# try these alternatives in order before giving up.
_FALLBACKS: dict[str, list[str]] = {
    # Groq Llama 4
    "groq/meta-llama/llama-4-maverick-17b-128e-instruct": [
        "groq/llama-3.3-70b-versatile",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "groq/meta-llama/llama-4-scout-17b-16e-instruct": [
        "groq/llama-3.3-70b-versatile",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    # Groq Llama 3.x
    "groq/llama-3.3-70b-versatile": [
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "groq/llama-3.2-90b-vision-preview": [
        "groq/llama-3.3-70b-versatile",
    ],
    "groq/llama-3.2-11b-vision-preview": [
        "groq/llama-3.2-90b-vision-preview",
        "groq/llama-3.3-70b-versatile",
    ],
    # Groq specialised
    "groq/deepseek-r1-distill-llama-70b": [
        "groq/llama-3.3-70b-versatile",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "groq/qwen-qwq-32b": [
        "groq/llama-3.3-70b-versatile",
    ],
    "groq/gemma2-9b-it": [
        "groq/llama-3.3-70b-versatile",
    ],
    # Anthropic
    "anthropic/claude-opus-4-7": [
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "anthropic/claude-sonnet-4-6": [
        "anthropic/claude-haiku-4-5-20251001",
        "groq/llama-3.3-70b-versatile",
    ],
    "anthropic/claude-haiku-4-5-20251001": [
        "groq/llama-3.3-70b-versatile",
    ],
    "anthropic/claude-3-5-sonnet-20241022": [
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "anthropic/claude-3-5-haiku-20241022": [
        "anthropic/claude-haiku-4-5-20251001",
        "groq/llama-3.3-70b-versatile",
    ],
    # OpenRouter — reached as a last resort, and chained to each other so the tier
    # is not a dead end either.
    "openrouter/meta-llama/llama-3.3-70b-instruct": [],
    "openrouter/anthropic/claude-haiku-4.5": [],
}

# Every chain above ends here. The first-party tiers share a failure mode: one key,
# one quota, and when a daily cap is gone every model behind that key is gone with
# it — which is exactly how a Groq-only deployment loses the ability to plan at all.
# OpenRouter fronts many providers behind a single key, so it is the fallback that
# survives that. Ordered same-family first: a Llama 3.3 deployment falling through
# to Llama 3.3 changes provider without changing the model's behaviour.
_OPENROUTER_LAST_RESORT = [
    "openrouter/meta-llama/llama-3.3-70b-instruct",
    "openrouter/anthropic/claude-haiku-4.5",
]

_FALLBACKS = {
    model: chain + [m for m in _OPENROUTER_LAST_RESORT if m != model and m not in chain]
    for model, chain in _FALLBACKS.items()
}

RETRY_AFTER_RE = re.compile(
    r"try again in ((?:\d+(?:\.\d+)?h)?(?:\d+(?:\.\d+)?m)?(?:\d+(?:\.\d+)?s)?)",
    re.IGNORECASE,
)
RETRY_DURATION_RE = re.compile(
    r"^(?:(?P<hours>[\d.]+)h)?(?:(?P<minutes>[\d.]+)m)?(?:(?P<seconds>[\d.]+)s)?$",
    re.IGNORECASE,
)


def _is_hard_rate_limit(err: Exception) -> bool:
    """True for daily/quota exhaustion — retrying the same model won't help."""
    msg = str(err).lower()
    return (
        "tokens per day" in msg
        or "tpd" in msg
        or "daily" in msg
        or ("rate_limit" in msg and "please try again in" not in msg)
        or "quota" in msg
        or "insufficient_quota" in msg
        or "resource_exhausted" in msg      # Gemini quota = 0
        or "model_not_found" in msg         # deprecated / removed model
        or ("not found" in msg and "model" in msg)
        or ("404" in msg and "model" in msg)
        or "unavailable" in msg             # Gemini 503 overload
        or "overloaded" in msg
    )


def _is_soft_rate_limit(err: Exception) -> bool:
    """True for per-minute throttling — a short wait is enough."""
    msg = str(err).lower()
    return (
        "tokens per minute" in msg
        or "tpm" in msg
        or "requests per minute" in msg
        or ("rate_limit" in msg and "please try again in" in msg)
        or "429" in str(err)
    )


def _rate_limit_delay(error: Exception, attempt: int) -> float:
    match = RETRY_AFTER_RE.search(str(error))
    if match:
        duration = match.group(1).strip()
        duration_match = RETRY_DURATION_RE.match(duration)
        if duration_match:
            hours = float(duration_match.group("hours") or 0)
            minutes = float(duration_match.group("minutes") or 0)
            seconds = float(duration_match.group("seconds") or 0)
            return hours * 3600 + minutes * 60 + seconds + 0.5
    return min(2 ** attempt, 30.0)


def _hard_limit_cooldown(err: Exception) -> float:
    """Estimate how long to cool down after a hard rate limit."""
    msg = str(err).lower()
    # Daily quota / tokens-per-day — will reset tomorrow; use 1 hour as practical cap
    if "tokens per day" in msg or "tpd" in msg or "daily" in msg:
        return 3600
    # Explicit retry-after header in the error message
    match = RETRY_AFTER_RE.search(str(err))
    if match:
        m = RETRY_DURATION_RE.match(match.group(1).strip())
        if m:
            secs = (
                float(m.group("hours") or 0) * 3600
                + float(m.group("minutes") or 0) * 60
                + float(m.group("seconds") or 0)
            )
            return max(secs + 5, 60)
    return 300  # 5-minute default for unknown hard limits


def _normalize_tool_choice(tool_choice: dict | str | None) -> dict | str | None:
    if (
        isinstance(tool_choice, dict)
        and tool_choice.get("type") == "function"
        and "name" in tool_choice
        and "function" not in tool_choice
    ):
        return {"type": "function", "function": {"name": tool_choice["name"]}}
    return tool_choice


# The env var each provider prefix authenticates with. A prefix that is absent here is
# one we cannot check, and an unknown provider is assumed usable rather than skipped.
_PROVIDER_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    # Without this entry has_credentials() falls through to True for every
    # openrouter/* id, so a keyless deployment would "fall back" to a model it
    # cannot call and replace a real rate-limit error with an auth error.
    "openrouter": "OPENROUTER_API_KEY",
}


def has_credentials(model: str) -> bool:
    """True when the provider behind `model` has an API key available."""
    provider = model.split("/", 1)[0] if "/" in model else ""
    env_var = _PROVIDER_KEY_ENV.get(provider)
    if env_var is None:
        return True
    return bool(os.environ.get(env_var, "").strip())


def _candidate_models(model: str) -> list[str]:
    """The models to try, in order.

    Two filters, both learned from production. Fallbacks whose provider has no key are
    dropped: calling one raises an authentication error that is neither a rate limit nor
    a missing model, so it escaped the retry logic entirely and replaced the real failure
    with "Missing Anthropic API Key" on a Groq-only deployment. Models cooling down after
    a hard rate limit are dropped too — that is what `model_health` was written for and
    what `GET /api/config/model-health` reports.

    The primary is always attempted regardless of either filter, so its own error is the
    one that surfaces. If every candidate is cooling down we take the least cold rather
    than returning nothing: a cooldown must slow the worker, never stop it.
    """
    fallbacks = [m for m in _FALLBACKS.get(model, []) if has_credentials(m)]

    healthy = [m for m in fallbacks if model_health.is_healthy(m)]
    if model_health.is_healthy(model):
        return [model] + healthy
    if healthy:
        return healthy + [model]  # primary is cooling down; keep it as a last resort
    return [model_health.get_least_cold([model] + fallbacks)]


async def acompletion(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> Any:
    models_to_try = _candidate_models(model)
    last_err: Exception | None = None
    # The first failure is the one that explains the run. Everything after it is a
    # consequence of falling back, and reporting a consequence as the cause is how
    # "Groq is rate limited" reached the operator as "Missing Anthropic API Key".
    first_err: Exception | None = None

    def record(exc: Exception) -> None:
        nonlocal last_err, first_err
        last_err = exc
        if first_err is None:
            first_err = exc

    for attempt_model in models_to_try:
        if attempt_model != model:
            logger.warning("Falling back from %s → %s", model, attempt_model)

        _no_temp = attempt_model in {
            "anthropic/claude-opus-4-7",
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-haiku-4-5-20251001",
        }
        kwargs: dict[str, Any] = dict(
            model=attempt_model,
            messages=messages,
            max_tokens=max_tokens,
        )
        if not _no_temp:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = _normalize_tool_choice(tool_choice) or "auto"

        for retry_attempt in range(3):
            try:
                resp = await _acompletion(**kwargs)
                if not getattr(resp, "choices", None):
                    record(ValueError(f"{attempt_model} returned empty response (no choices)"))
                    logger.warning("Empty choices from %s; trying next model", attempt_model)
                    break
                return resp
            except Exception as exc:
                if _is_hard_rate_limit(exc):
                    cooldown = _hard_limit_cooldown(exc)
                    # Register the outage so the next call skips this model instead of
                    # spending another request discovering the same limit, and so
                    # /api/config/model-health can report what is actually going on.
                    model_health.mark_unhealthy(attempt_model, cooldown)
                    logger.warning("Hard rate limit on %s: %s; cooling down %.0fs, trying next model",
                                   attempt_model, str(exc)[:120], cooldown)
                    record(exc)
                    break
                if _is_soft_rate_limit(exc) and retry_attempt < 2:
                    delay = _rate_limit_delay(exc, retry_attempt)
                    logger.warning("Soft rate limit on %s; retrying in %.2fs (attempt %d/3)", attempt_model, delay, retry_attempt + 1)
                    await asyncio.sleep(delay)
                    continue
                err_lower = str(exc).lower()
                if "not_found_error" in err_lower or "notfounderror" in err_lower or "model not found" in err_lower:
                    logger.warning("Model %s not found — trying next fallback", attempt_model)
                    record(exc)
                    break
                # An unexpected error on the primary model is the answer: raise it. On a
                # fallback it is noise, so move on and let the primary's error stand.
                record(exc)
                if attempt_model == model:
                    raise
                logger.warning("Fallback %s failed (%s); trying next", attempt_model, str(exc)[:120])
                break

    raise first_err or last_err  # type: ignore[misc]


def build_tool_defs(tool_registry: dict) -> list[dict]:
    """Convert TOOL_REGISTRY entries to LiteLLM-compatible function definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": entry["schema"].get("description", name),
                "parameters": entry["schema"],
            },
        }
        for name, entry in tool_registry.items()
    ]
