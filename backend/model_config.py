"""
Per-role model configuration. Defaults everything to Groq.
Persisted to model_config.json next to main.py.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).parent / "model_config.json"

AVAILABLE_MODELS = [
    {"id": "groq/llama-3.3-70b-versatile", "label": "Llama 3.3 70B", "provider": "Groq", "tier": "fast"},
    {"id": "groq/llama-3.1-70b-versatile", "label": "Llama 3.1 70B", "provider": "Groq", "tier": "fast"},
    {"id": "groq/llama-3.1-8b-instant",    "label": "Llama 3.1 8B",  "provider": "Groq", "tier": "instant"},
    {"id": "anthropic/claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "provider": "Anthropic", "tier": "fast"},
    {"id": "anthropic/claude-sonnet-4-6",  "label": "Claude Sonnet 4.6", "provider": "Anthropic", "tier": "powerful"},
]

DEFAULTS: dict[str, str] = {
    "orchestrator": "groq/llama-3.3-70b-versatile",
    "researcher":   "groq/llama-3.3-70b-versatile",
    "writer":       "groq/llama-3.3-70b-versatile",
    "notifier":     "groq/llama-3.1-8b-instant",
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
        _CONFIG_FILE.write_text(json.dumps(config, indent=2))
    except Exception as e:
        logger.warning("Could not persist model config: %s", e)


def get_model(role: str) -> str:
    return _load().get(role, DEFAULTS.get(role, "groq/llama-3.3-70b-versatile"))


def get_all() -> dict[str, str]:
    return dict(_load())


def update(updates: dict[str, str]) -> dict[str, str]:
    valid_ids = {m["id"] for m in AVAILABLE_MODELS}
    current = _load()
    for role, model_id in updates.items():
        if role not in DEFAULTS:
            raise ValueError(f"Unknown role: {role!r}")
        if model_id not in valid_ids:
            raise ValueError(f"Unknown model: {model_id!r}")
        current[role] = model_id
    _save(current)
    return dict(current)
