import os
from typing import Any

import litellm
from litellm import acompletion as _acompletion

from config import settings

# Set provider keys for LiteLLM
os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
os.environ.setdefault("GROQ_API_KEY", settings.groq_api_key)

litellm.drop_params = True  # ignore unsupported params per provider


async def acompletion(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: dict | str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> Any:
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"
    return await _acompletion(**kwargs)


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
