import os

import httpx

from tools.credential_request import WAITING_CREDENTIAL_SENTINEL
from tracing import trace


@trace("slack_notify")
async def slack_notify(args: dict) -> dict:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        return {
            WAITING_CREDENTIAL_SENTINEL: True,
            "credential": "SLACK_WEBHOOK_URL",
            "provider": "slack",
            "message": "Slack Webhook URL required to send notifications",
        }

    message = args["message"]
    channel = args.get("channel")

    payload: dict = {"text": message}
    if channel:
        payload["channel"] = channel

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)

    body = resp.text.strip()
    slack_ok = resp.is_success and body == "ok"
    if not slack_ok:
        return {"sent": False, "error": f"Slack rejected the message: {body or resp.status_code}"}
    return {"sent": True, "destination": channel or "default"}


SCHEMA = {
    "description": "Post a message to Slack via an incoming webhook.",
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "The message text to post"},
        "channel": {"type": "string", "description": "Override the default channel (e.g. #general)"},
    },
    "required": ["message"],
}
