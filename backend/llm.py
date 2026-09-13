import asyncio
import logging
import os
import re
from typing import Any

import litellm
from litellm import acompletion as _acompletion

from config import settings

logger = logging.getLogger(__name__)

# Set provider keys for LiteLLM
os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
os.environ.setdefault("GROQ_API_KEY", settings.groq_api_key)

litellm.drop_params = True  # ignore unsupported params per provider

# Fallback chain: when a model hits a hard rate limit (TPD / daily quota),
# try these alternatives in order before giving up.
_FALLBACKS: dict[str, list[str]] = {
    "groq/llama-3.3-70b-versatile": [
        "groq/llama-3.1-8b-instant",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "groq/llama-3.1-70b-versatile": [
        "groq/llama-3.1-8b-instant",
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "groq/llama-3.1-8b-instant": [
        "anthropic/claude-haiku-4-5-20251001",
    ],
    "anthropic/claude-haiku-4-5-20251001": [
        "groq/llama-3.1-8b-instant",
        "groq/llama-3.3-70b-versatile",
    ],
    "anthropic/claude-sonnet-4-6": [
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
    models_to_try = [model] + _FALLBACKS.get(model, [])
    last_err: Exception | None = None

    for attempt_model in models_to_try:
        if attempt_model != model:
            logger.warning("Falling back from %s → %s (rate limit / quota)", model, attempt_model)

        kwargs: dict[str, Any] = dict(
            model=attempt_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = _normalize_tool_choice(tool_choice) or "auto"

        for retry_attempt in range(3):
            try:
                return await _acompletion(**kwargs)
            except Exception as exc:
                if _is_hard_rate_limit(exc):
                    logger.warning("Hard rate limit on %s: %s; trying next model", attempt_model, str(exc)[:120])
                    last_err = exc
                    break
                if _is_soft_rate_limit(exc) and retry_attempt < 2:
                    delay = _rate_limit_delay(exc, retry_attempt)
                    if delay > 60:
                        logger.warning("Soft rate limit wait is %.2fs for %s; trying next model", delay, attempt_model)
                        last_err = exc
                        break
                    logger.warning(
                        "Soft rate limit on %s; retrying in %.2fs (attempt %d/3)",
                        attempt_model,
                        delay,
                        retry_attempt + 1,
                    )
                    await asyncio.sleep(delay)
                    continue
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
