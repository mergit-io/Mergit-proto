from fastapi import APIRouter, HTTPException, Request

import db
from models import WebhookResponse

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

    return WebhookResponse(ok=True, task_id=task.id)
