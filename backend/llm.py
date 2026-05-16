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


async def acompletion(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> Any:
    all_candidates = [model] + _FALLBACKS.get(model, [])

    # Skip models currently cooling down from a hard rate limit.
    # Always keep at least one candidate (the least-cold if all are cooling).
    healthy = [m for m in all_candidates if model_health.is_healthy(m)]
    models_to_try = healthy if healthy else [model_health.get_least_cold(all_candidates)]

    if models_to_try[0] != model:
        logger.warning(
            "Auto-switching: %s is cooling down — starting with %s instead",
            model, models_to_try[0],
        )

    last_err: Exception | None = None

    for attempt_model in models_to_try:
        if attempt_model != model:
            logger.warning("Falling back from %s → %s (rate limit / quota)", model, attempt_model)

        # Claude 4 extended-thinking models don't accept `temperature`
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
                    last_err = ValueError(f"{attempt_model} returned empty response (no choices)")
                    logger.warning("Empty choices from %s; trying next model", attempt_model)
                    model_health.mark_unhealthy(attempt_model, 120)
                    break  # try next fallback model
                return resp
            except Exception as exc:
                if _is_hard_rate_limit(exc):
                    cooldown = _hard_limit_cooldown(exc)
                    model_health.mark_unhealthy(attempt_model, cooldown)
                    logger.warning(
                        "Hard rate limit on %s (cooldown %.0fs): %s; trying next model",
                        attempt_model, cooldown, str(exc)[:120],
                    )
                    last_err = exc
                    break
                if _is_soft_rate_limit(exc) and retry_attempt < 2:
                    delay = _rate_limit_delay(exc, retry_attempt)
                    # Threshold: if retry-after > 20s, skip to next fallback model instead of sleeping.
                    # This prevents a single model's rate limit from blocking for > 20s per call.
                    if delay > 20:
                        model_health.mark_unhealthy(attempt_model, delay)
                        logger.warning(
                            "Soft rate limit wait is %.2fs for %s — cooling down; trying next model",
                            delay, attempt_model,
                        )
                        last_err = exc
                        break
                    logger.warning(
                        "Soft rate limit on %s; retrying in %.2fs (attempt %d/3)",
                        attempt_model, delay, retry_attempt + 1,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Model not found / deprecated — mark unhealthy and try next fallback
                err_lower = str(exc).lower()
                if "not_found_error" in err_lower or "notfounderror" in err_lower or "model not found" in err_lower:
                    model_health.mark_unhealthy(attempt_model, 3600)
                    logger.warning("Model %s not found — marking unhealthy; trying next fallback", attempt_model)
                    last_err = exc
                    break
                raise

    raise last_err  # type: ignore[misc]


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
