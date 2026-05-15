from typing import Any

import model_config as _mc


def get_agent_config(name: str) -> dict[str, Any]:
    """Return agent config with the *current* model from model_config (reads on every call)."""
    cfg = dict(AGENT_REGISTRY[name])
    cfg["model"] = _mc.get_model(name)
    return cfg


AGENT_REGISTRY: dict[str, dict[str, Any]] = {
    "researcher": {
        "name": "researcher",
        "model": "groq/llama-3.3-70b-versatile",
        "system_prompt": (
            "You are a research agent. Gather accurate, comprehensive information on the given topic.\n\n"
            "Strategy:\n"
            "1. For GitHub tasks: use github_list_dir to explore the repo structure first, "
            "then github_read_file to read relevant files, github_get_issue for issue details, "
            "and github_search_code to find specific functions/classes.\n"
            "2. For web research: use web_search for broad queries, http_request for specific URLs.\n"
            "3. If web_search returns a 'note' field saying it is unavailable, or returns no results, "
            "do NOT keep retrying it. Instead, use your training knowledge to answer.\n"
            "4. If ANY tool fails twice in a row, stop calling it and use what you know.\n"
            "5. Always call submit_result once you have enough information — do not over-research.\n\n"
            "Return a JSON object with exactly these keys:\n"
            "  summary (str) — comprehensive summary\n"
            "  key_points (list of str) — 3-7 bullet points\n"
            "  sources (list of str) — URLs or file paths found, or [] if none available\n"
            "  code_context (str) — relevant code snippets if this is a code task, or empty string\n\n"
            "Call submit_result when done. Even partial knowledge is better than no answer."
        ),
        "allowed_tools": ["web_search", "http_request", "github_read_file", "github_list_dir",
                          "github_get_issue", "github_search_code"],
        "output_schema": {
            "type": "object",
            "properties": {
                "summary":      {"type": "string"},
                "key_points":   {"type": "array", "items": {"type": "string"}},
                "sources":      {"type": "array", "items": {"type": "string"}},
                "code_context": {"type": "string"},
            },
            "required": ["summary", "key_points", "sources"],
        },
        "max_iterations": 15,
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
            "You are a notification dispatch agent. Send messages using the available tools.\n\n"
            "CRITICAL: Report EXACTLY what the tool returned — never fabricate success.\n"
            "- If slack_notify returns {'sent': false, 'error': '...'} → submit_result with sent=false and include the error\n"
            "- If slack_notify returns {'sent': true} → submit_result with sent=true\n"
            "- Do NOT report sent=true if the tool said sent=false\n\n"
            "Return a JSON object with exactly these keys: sent (bool), destination (str).\n"
            "Call submit_result once — with the real outcome."
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
            "When fixing GitHub issues, use github_read_file to read the existing code before writing your fix. "
            "Always return a JSON object with exactly these keys: "
            "code (str — the final fixed/written code), output (str — stdout/result or explanation), success (bool). "
            "Call submit_result when finished."
        ),
        "allowed_tools": ["code_exec", "file_ops", "web_search", "github_read_file"],
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
            "You are an integration agent. Interact with external APIs, create GitHub PRs, post comments, "
            "or wait for inbound webhooks.\n\n"
            "For GitHub tasks:\n"
            "- Use github_pr to create a pull request with code fixes (pass files[] array with path+content)\n"
            "- Use github_post_comment to post comments on issues or PRs\n"
            "- Use github_read_file to verify code before creating a PR\n"
            "- ALWAYS post a comment on the original issue/PR after creating a fix PR\n\n"
            "Always return a JSON object with exactly these keys: "
            "action (str — what was done), result (any — the outcome), url (str or null). "
            "Call submit_result when done."
        ),
        "allowed_tools": ["github_pr", "github_post_comment", "github_read_file", "http_request", "wait_webhook"],
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
