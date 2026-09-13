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
]

DEFAULTS: dict[str, str] = {
    "orchestrator": "groq/llama-3.3-70b-versatile",
    "researcher":   "groq/llama-3.3-70b-versatile",
    "writer":       "groq/llama-3.3-70b-versatile",
    "notifier":     "groq/llama-3.3-70b-versatile",
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


def update(updates: dict[str, str]) -> dict[str, str]:
    current = _load()
    for role, model_id in updates.items():
        if role not in DEFAULTS:
            raise ValueError(f"Unknown role: {role!r}")
        if not model_id or not isinstance(model_id, str):
            raise ValueError(f"Model ID must be a non-empty string for role {role!r}")
        current[role] = model_id.strip()
    _save(current)
    return dict(current)
