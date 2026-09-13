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
    # Groq — Meta Llama 4
    {"id": "groq/meta-llama/llama-4-maverick-17b-128e-instruct", "label": "Llama 4 Maverick 17B", "provider": "Groq", "tier": "fast"},
    {"id": "groq/meta-llama/llama-4-scout-17b-16e-instruct",     "label": "Llama 4 Scout 17B",    "provider": "Groq", "tier": "instant"},
    # Groq — Meta Llama 3.x
    {"id": "groq/llama-3.3-70b-versatile",                       "label": "Llama 3.3 70B",        "provider": "Groq", "tier": "fast"},
    {"id": "groq/llama-3.1-70b-versatile",                       "label": "Llama 3.1 70B",        "provider": "Groq", "tier": "fast"},
    {"id": "groq/llama-3.1-8b-instant",                          "label": "Llama 3.1 8B",         "provider": "Groq", "tier": "instant"},
    {"id": "groq/llama-3.2-90b-vision-preview",                  "label": "Llama 3.2 90B Vision", "provider": "Groq", "tier": "fast"},
    {"id": "groq/llama-3.2-11b-vision-preview",                  "label": "Llama 3.2 11B Vision", "provider": "Groq", "tier": "instant"},
    {"id": "groq/llama-3.2-3b-preview",                          "label": "Llama 3.2 3B",         "provider": "Groq", "tier": "instant"},
    # Groq — DeepSeek / Qwen
    {"id": "groq/deepseek-r1-distill-llama-70b",                 "label": "DeepSeek R1 70B",      "provider": "Groq", "tier": "fast"},
    {"id": "groq/qwen-qwq-32b",                                  "label": "Qwen QwQ 32B",         "provider": "Groq", "tier": "fast"},
    # Groq — Mixtral / Gemma
    {"id": "groq/mixtral-8x7b-32768",                            "label": "Mixtral 8x7B",         "provider": "Groq", "tier": "fast"},
    {"id": "groq/gemma2-9b-it",                                  "label": "Gemma 2 9B",           "provider": "Groq", "tier": "instant"},
    # Anthropic — Claude 4
    {"id": "anthropic/claude-opus-4-7",                          "label": "Claude Opus 4.7",      "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-sonnet-4-6",                        "label": "Claude Sonnet 4.6",    "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-haiku-4-5-20251001",                "label": "Claude Haiku 4.5",     "provider": "Anthropic", "tier": "fast"},
    # Anthropic — Claude 3.5
    {"id": "anthropic/claude-3-5-sonnet-20241022",               "label": "Claude 3.5 Sonnet",    "provider": "Anthropic", "tier": "powerful"},
    {"id": "anthropic/claude-3-5-haiku-20241022",                "label": "Claude 3.5 Haiku",     "provider": "Anthropic", "tier": "fast"},
    # Anthropic — Claude 3
    {"id": "anthropic/claude-3-opus-20240229",                   "label": "Claude 3 Opus",        "provider": "Anthropic", "tier": "powerful"},
    # OpenAI — GPT-4o
    {"id": "openai/gpt-4o",                                      "label": "GPT-4o",               "provider": "OpenAI", "tier": "powerful"},
    {"id": "openai/gpt-4o-mini",                                 "label": "GPT-4o Mini",          "provider": "OpenAI", "tier": "fast"},
    # OpenAI — o-series reasoning
    {"id": "openai/o3",                                          "label": "o3",                   "provider": "OpenAI", "tier": "powerful"},
    {"id": "openai/o4-mini",                                     "label": "o4 Mini",              "provider": "OpenAI", "tier": "fast"},
    {"id": "openai/o3-mini",                                     "label": "o3 Mini",              "provider": "OpenAI", "tier": "fast"},
    {"id": "openai/o1",                                          "label": "o1",                   "provider": "OpenAI", "tier": "powerful"},
    # OpenAI — GPT-4 / GPT-3.5
    {"id": "openai/gpt-4-turbo",                                 "label": "GPT-4 Turbo",          "provider": "OpenAI", "tier": "powerful"},
    {"id": "openai/gpt-3.5-turbo",                               "label": "GPT-3.5 Turbo",        "provider": "OpenAI", "tier": "instant"},
    # Google — Gemini 2.5
    {"id": "gemini/gemini-2.5-pro",                              "label": "Gemini 2.5 Pro",       "provider": "Google", "tier": "powerful"},
    {"id": "gemini/gemini-2.5-flash",                            "label": "Gemini 2.5 Flash",     "provider": "Google", "tier": "fast"},
    # Google — Gemini 2.0
    {"id": "gemini/gemini-2.0-flash",                            "label": "Gemini 2.0 Flash",     "provider": "Google", "tier": "fast"},
    {"id": "gemini/gemini-2.0-flash-lite",                       "label": "Gemini 2.0 Flash Lite","provider": "Google", "tier": "instant"},
    # Google — Gemini 1.5
    {"id": "gemini/gemini-1.5-pro",                              "label": "Gemini 1.5 Pro",       "provider": "Google", "tier": "powerful"},
    {"id": "gemini/gemini-1.5-flash",                            "label": "Gemini 1.5 Flash",     "provider": "Google", "tier": "fast"},
    {"id": "gemini/gemini-1.5-flash-8b",                         "label": "Gemini 1.5 Flash 8B",  "provider": "Google", "tier": "instant"},
    # Mistral
    {"id": "mistral/mistral-large-latest",                       "label": "Mistral Large",        "provider": "Mistral", "tier": "powerful"},
    {"id": "mistral/mistral-medium-3",                           "label": "Mistral Medium 3",     "provider": "Mistral", "tier": "fast"},
    {"id": "mistral/mistral-small-3",                            "label": "Mistral Small 3",      "provider": "Mistral", "tier": "fast"},
    {"id": "mistral/codestral-latest",                           "label": "Codestral",            "provider": "Mistral", "tier": "fast"},
    {"id": "mistral/pixtral-large-latest",                       "label": "Pixtral Large",        "provider": "Mistral", "tier": "powerful"},
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
    current = _load()
    for role, model_id in updates.items():
        if role not in DEFAULTS:
            raise ValueError(f"Unknown role: {role!r}")
        if not model_id or not isinstance(model_id, str):
            raise ValueError(f"Model ID must be a non-empty string for role {role!r}")
        current[role] = model_id.strip()
    _save(current)
    return dict(current)
