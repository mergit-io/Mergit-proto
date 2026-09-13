"""
Special tool: suspends the current task, waiting for an inbound webhook.
The agent_runner detects the WAITING_WEBHOOK sentinel in the result and
calls db.set_task_waiting_webhook() instead of settling the task as DONE.
"""
import uuid

WAITING_WEBHOOK_SENTINEL = "__WAITING_WEBHOOK__"


async def wait_webhook(args: dict) -> dict:
    wait_token = str(uuid.uuid4())
    description = args.get("description", "Waiting for inbound webhook")
    timeout_seconds = args.get("timeout_seconds", 3600)
    return {
        WAITING_WEBHOOK_SENTINEL: True,
        "wait_token": wait_token,
        "description": description,
        "timeout_seconds": timeout_seconds,
        "webhook_url": f"/api/webhooks/{wait_token}",
    }


SCHEMA = {
    "description": "Suspend this task and wait for an inbound HTTP webhook to resume it. Returns a webhook URL to share with the caller.",
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "What this task is waiting for"},
        "timeout_seconds": {"type": "integer", "default": 3600, "description": "Max wait time in seconds"},
    },
    "required": [],
}
