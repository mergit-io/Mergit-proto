"""
Per-role model configuration. Defaults everything to Groq.
Persisted to model_config.json in the runtime config directory.
"""
import json
import logging
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(settings.runtime_config_dir) / "model_config.json"

#: The models the picker offers. Every id here was set on a live deployment and sent a
#: one-line goal; ids that answered `model_not_found` or "has been decommissioned" are
#: not in this list. Seven Groq entries and two Anthropic entries were removed that way —
#: eleven of the previous thirteen choices could not run, and `is_known_model` could not
#: catch it because it validates against this list.
#:
#: A model being listed here does not mean this deployment can use it: that depends on
#: whether the provider's API key is set, which `GET /api/config/models` reports
#: per request via `llm.has_credentials`.
AVAILABLE_MODELS = [
    # Groq — the only id on this account that serves traffic. The rest of the Groq
    # catalogue was either never accessible (Llama 4) or has since been decommissioned
    # (Qwen QwQ, DeepSeek R1 distill, Gemma 2, both Llama 3.2 vision previews).
    {"id": "groq/llama-3.3-70b-versatile",   "label": "Llama 3.3 70B",     "provider": "Groq", "tier": "fast"},
    # Anthropic — current generation.
    {"id": "anthropic/claude-opus-5",        "label": "Claude Opus 5",     "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-sonnet-5",      "label": "Claude Sonnet 5",   "provider": "Anthropic", "tier": "balanced"},
    {"id": "anthropic/claude-haiku-4-5",     "label": "Claude Haiku 4.5",  "provider": "Anthropic", "tier": "fast"},
    # Anthropic — previous generation, still served.
    {"id": "anthropic/claude-opus-4-7",      "label": "Claude Opus 4.7",   "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-sonnet-4-6",    "label": "Claude Sonnet 4.6", "provider": "Anthropic", "tier": "balanced"},
    # OpenRouter — the same Anthropic models reached through a reseller, so one key
    # covers them without an ANTHROPIC_API_KEY. Note the slugs use dots where
    # Anthropic's own API uses dashes; these were read from OpenRouter's /models
    # endpoint, and the dashed form does not resolve there.
    {"id": "openrouter/anthropic/claude-opus-5",     "label": "Claude Opus 5 (OpenRouter)",    "provider": "OpenRouter", "tier": "powerful"},
    {"id": "openrouter/anthropic/claude-sonnet-5",   "label": "Claude Sonnet 5 (OpenRouter)",  "provider": "OpenRouter", "tier": "balanced"},
    {"id": "openrouter/anthropic/claude-haiku-4.5",  "label": "Claude Haiku 4.5 (OpenRouter)", "provider": "OpenRouter", "tier": "fast"},
]

DEFAULTS: dict[str, str] = {
    "orchestrator": "groq/llama-3.3-70b-versatile",
    "researcher":   "groq/llama-3.3-70b-versatile",
    "writer":       "groq/llama-3.3-70b-versatile",
    "coder":        "groq/llama-3.3-70b-versatile",
    "integrator":   "groq/llama-3.3-70b-versatile",
}

_cache: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    if _CONFIG_FILE.exists():
        try:
            saved = json.loads(_CONFIG_FILE.read_text())
            # Drop any saved id the catalogue no longer offers. A model that was
            # selected before it was decommissioned would otherwise keep being sent to
            # the provider, failing every goal with an error naming a model the picker
            # no longer shows — invisible from the UI.
            usable = {}
            for role, model_id in saved.items():
                if is_known_model(model_id):
                    usable[role] = model_id
                else:
                    logger.warning(
                        "Saved model %r for role %r is no longer offered — falling back "
                        "to the default (%s)", model_id, role, DEFAULTS.get(role),
                    )
            # Merge with defaults so new roles always have a value
            _cache = {**DEFAULTS, **usable}
            return _cache
        except Exception as e:
            logger.warning("model_config.json unreadable (%s) — using defaults", e)
    _cache = dict(DEFAULTS)
    return _cache


def _save(config: dict[str, str]) -> None:
    global _cache
    _cache = config
    try:
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_FILE.write_text(json.dumps(config, indent=2))
    except Exception as e:
        logger.warning("Could not persist model config: %s", e)


def get_model(role: str) -> str:
    return _load().get(role, DEFAULTS.get(role, "groq/llama-3.3-70b-versatile"))


def get_all() -> dict[str, str]:
    return dict(_load())


def is_known_model(model_id: str) -> bool:
    return any(m["id"] == model_id for m in AVAILABLE_MODELS)


def update(updates: dict[str, str]) -> dict[str, str]:
    current = _load()
    for role, model_id in updates.items():
        if role not in DEFAULTS:
            continue  # silently skip stale/unknown roles
        if not model_id or not isinstance(model_id, str):
            raise ValueError(f"Model ID must be a non-empty string for role {role!r}")
        model_id = model_id.strip()
        # Rejected here rather than at call time: an unknown id saves cleanly and then
        # fails every goal with a provider error naming a model the operator never
        # chose. The endpoint that reaches this is unauthenticated.
        if not is_known_model(model_id):
            raise ValueError(
                f"Unknown model {model_id!r} for role {role!r}. "
                f"Choose one of: {', '.join(m['id'] for m in AVAILABLE_MODELS)}"
            )
        current[role] = model_id
    # Drop any stale keys that are no longer valid roles
    current = {r: m for r, m in current.items() if r in DEFAULTS}
    _save(current)
    return dict(current)
