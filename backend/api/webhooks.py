import logging

from fastapi import APIRouter, HTTPException, Request

import db
import events
from models import WebhookResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/{token}")
async def receive_webhook(token: str, request: Request) -> WebhookResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    task = await db.resume_webhook_task(token, payload)
    if not task:
        raise HTTPException(status_code=404, detail="No task waiting for this webhook token")

    logger.info("Webhook received: token=%s task=%s payload=%s", token[:16], task.id, str(payload)[:120])

    # Emit SSE so the live log updates
    events.emit(task.goal_id, "task_update", {
        "task_id": task.id,
        "status": "READY",
        "event": "webhook_received",
    })

    return WebhookResponse(ok=True, task_id=task.id)
