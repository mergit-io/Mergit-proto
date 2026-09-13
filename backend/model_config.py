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

AVAILABLE_MODELS = [
    # Groq — Meta Llama 4
    {"id": "groq/meta-llama/llama-4-maverick-17b-128e-instruct", "label": "Llama 4 Maverick 17B", "provider": "Groq", "tier": "fast"},
    {"id": "groq/meta-llama/llama-4-scout-17b-16e-instruct",     "label": "Llama 4 Scout 17B",    "provider": "Groq", "tier": "instant"},
    # Groq — Meta Llama 3.x
    {"id": "groq/llama-3.3-70b-versatile",                       "label": "Llama 3.3 70B",        "provider": "Groq", "tier": "fast"},
    {"id": "groq/llama-3.2-90b-vision-preview",                  "label": "Llama 3.2 90B Vision", "provider": "Groq", "tier": "fast"},
    {"id": "groq/llama-3.2-11b-vision-preview",                  "label": "Llama 3.2 11B Vision", "provider": "Groq", "tier": "instant"},
    # Groq — DeepSeek / Qwen
    {"id": "groq/deepseek-r1-distill-llama-70b",                 "label": "DeepSeek R1 70B",      "provider": "Groq", "tier": "fast"},
    {"id": "groq/qwen-qwq-32b",                                  "label": "Qwen QwQ 32B",         "provider": "Groq", "tier": "fast"},
    {"id": "groq/gemma2-9b-it",                                  "label": "Gemma 2 9B",           "provider": "Groq", "tier": "instant"},
    # Anthropic — Claude 4
    {"id": "anthropic/claude-opus-4-7",                          "label": "Claude Opus 4.7",      "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-sonnet-4-6",                        "label": "Claude Sonnet 4.6",    "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-haiku-4-5-20251001",                "label": "Claude Haiku 4.5",     "provider": "Anthropic", "tier": "fast"},
    # Anthropic — Claude 3.5
    {"id": "anthropic/claude-3-5-sonnet-20241022",               "label": "Claude 3.5 Sonnet",    "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-3-5-haiku-20241022",                "label": "Claude 3.5 Haiku",     "provider": "Anthropic", "tier": "fast"},
    # OpenRouter — one key, many providers. Also the last-resort fallback tier in llm.py.
    # Listed here so the Models page can select them; PUT /api/config/models validates
    # against this list, so an id missing from it is rejected even when litellm supports it.
    {"id": "openrouter/meta-llama/llama-3.3-70b-instruct",       "label": "Llama 3.3 70B (OpenRouter)",    "provider": "OpenRouter", "tier": "fast"},
    {"id": "openrouter/anthropic/claude-haiku-4.5",              "label": "Claude Haiku 4.5 (OpenRouter)", "provider": "OpenRouter", "tier": "fast"},
    # GPT-class, and the default tier. Every id here was checked against OpenRouter's live
    # /api/v1/models: all three report tool support and a ~1M context, and gpt-4.1 is both
    # cheaper and larger-context than gpt-4o ($2/M vs $2.50/M in), so 4o is not listed.
    {"id": "openrouter/openai/gpt-4.1",                          "label": "GPT-4.1 (OpenRouter)",          "provider": "OpenRouter", "tier": "powerful"},
    {"id": "openrouter/openai/gpt-4.1-mini",                     "label": "GPT-4.1 Mini (OpenRouter)",     "provider": "OpenRouter", "tier": "fast"},
    {"id": "openrouter/openai/gpt-4.1-nano",                     "label": "GPT-4.1 Nano (OpenRouter)",     "provider": "OpenRouter", "tier": "instant"},
]

#: Llama 3.3 70B ran every role, and it is weak at the two things this system asks for
#: most: long multi-step tool loops, and emitting a tool call that matches a schema
#: exactly. Both failure modes were live — plans that ignored the goal's real shape, and
#: an integrator that created a GitHub issue and then submitted it under keys the schema
#: did not declare, failing the task and blocking everything downstream.
#:
#: GPT-4.1 is the default tier now, with Groq behind it in the fallback chain (see
#: llm.py), so a deployment with no OpenRouter key still runs exactly as before. The
#: split is by what the role actually does: planning, code and outside-world writes get
#: the full model, reading and prose get mini at a fifth of the price.
DEFAULTS: dict[str, str] = {
    "orchestrator": "openrouter/openai/gpt-4.1",       # plan quality decides everything after it
    "researcher":   "openrouter/openai/gpt-4.1-mini",  # many cheap tool calls
    "writer":       "openrouter/openai/gpt-4.1-mini",  # prose, no tools to speak of
    "coder":        "openrouter/openai/gpt-4.1",       # correctness matters more than price
    "integrator":   "openrouter/openai/gpt-4.1",       # strict tool use; this is where it broke
}

#: What DEFAULTS used to be. `PUT /api/config/models` writes every role on every save,
#: so a file holding exactly this is a snapshot of the old defaults, not a choice anybody
#: made — the Models page was opened and saved without changing a thing. Treating it as a
#: preference would pin those deployments to Llama for good and make the new defaults
#: above a no-op wherever the page had ever been touched.
_SUPERSEDED_DEFAULTS: dict[str, str] = {
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
            if saved == _SUPERSEDED_DEFAULTS:
                logger.info("model_config.json matches the superseded defaults verbatim — "
                            "treating it as unconfigured and using the current defaults")
                _cache = dict(DEFAULTS)
                return _cache
            # Merge with defaults so new roles always have a value
            _cache = {**DEFAULTS, **saved}
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
