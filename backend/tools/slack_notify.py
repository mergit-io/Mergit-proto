import httpx

from config import settings
from tracing import trace


@trace("slack_notify")
async def slack_notify(args: dict) -> dict:
    webhook_url = settings.slack_webhook_url
    if not webhook_url:
        return {"sent": False, "error": "SLACK_WEBHOOK_URL not configured"}

    message = args["message"]
    channel = args.get("channel")

    payload: dict = {"text": message}
    if channel:
        payload["channel"] = channel

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)

    return {"sent": resp.is_success, "destination": channel or "default", "status_code": resp.status_code}


SCHEMA = {
    "description": "Post a message to Slack via an incoming webhook.",
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "The message text to post"},
        "channel": {"type": "string", "description": "Override the default channel (e.g. #general)"},
    },
    "required": ["message"],
}
