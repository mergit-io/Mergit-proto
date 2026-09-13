from typing import Any

AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "researcher": {
        "name": "researcher",
        "model": "groq/llama-3.3-70b-versatile",
        "system_prompt": (
            "You are a research agent. Your job is to gather comprehensive, accurate information "
            "on the given topic using web search and HTTP requests. Search from multiple angles. "
            "Synthesize findings into a coherent response. "
            "Always return a JSON object with exactly these keys: "
            "summary (str), key_points (list of str), sources (list of URL strings). "
            "Call submit_result when you have gathered sufficient information."
        ),
        "allowed_tools": ["web_search", "http_request"],
        "output_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "key_points": {"type": "array", "items": {"type": "string"}},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "key_points", "sources"],
        },
        "max_iterations": 8,
    },
    "writer": {
        "name": "writer",
        "model": "groq/llama-3.3-70b-versatile",
        "system_prompt": (
            "You are a content synthesis and writing agent. Take the provided research or data "
            "and produce a well-structured, professional document. "
            "You may save files using file_ops if instructed. "
            "Always return a JSON object with exactly these keys: "
            "text (str — the full document content), title (str). "
            "Call submit_result when finished."
        ),
        "allowed_tools": ["file_ops"],
        "output_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["text", "title"],
        },
        "max_iterations": 4,
    },
    "notifier": {
        "name": "notifier",
        "model": "groq/llama-3.1-8b-instant",
        "system_prompt": (
            "You are a notification dispatch agent. Send messages to the specified destination "
            "using the available tools. "
            "Always return a JSON object with exactly these keys: "
            "sent (bool), destination (str). "
            "Call submit_result when done."
        ),
        "allowed_tools": ["slack_notify", "http_request"],
        "output_schema": {
            "type": "object",
            "properties": {
                "sent": {"type": "boolean"},
                "destination": {"type": "string"},
            },
            "required": ["sent", "destination"],
        },
        "max_iterations": 3,
    },
    "coder": {
        "name": "coder",
        "model": "groq/llama-3.3-70b-versatile",
        "system_prompt": (
            "You are a code generation and execution agent. Write Python code, execute it, "
            "and analyze the results. You may iterate if execution fails. "
            "Save important outputs to files using file_ops. "
            "Always return a JSON object with exactly these keys: "
            "code (str — the final code), output (str — stdout/result), success (bool). "
            "Call submit_result when finished."
        ),
        "allowed_tools": ["code_exec", "file_ops", "web_search"],
        "output_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "output": {"type": "string"},
                "success": {"type": "boolean"},
            },
            "required": ["code", "output", "success"],
        },
        "max_iterations": 6,
    },
    "integrator": {
        "name": "integrator",
        "model": "groq/llama-3.3-70b-versatile",
        "system_prompt": (
            "You are an integration agent. Interact with external APIs, create GitHub PRs, "
            "or wait for inbound webhooks. "
            "Always return a JSON object with exactly these keys: "
            "action (str — what was done), result (any — the outcome), url (str or null). "
            "Call submit_result when done."
        ),
        "allowed_tools": ["github_pr", "http_request", "wait_webhook"],
        "output_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "result": {},
                "url": {"type": ["string", "null"]},
            },
            "required": ["action", "result"],
        },
        "max_iterations": 5,
    },
}
