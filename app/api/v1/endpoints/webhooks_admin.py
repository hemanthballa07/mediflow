import uuid
import hmac
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.config import get_settings
from app.services.webhooks import WebhookService
from app.api.v1.deps import get_current_user
from app.models.models import User

router = APIRouter(prefix="/admin/webhooks", tags=["admin-webhooks"])
settings = get_settings()


def verify_admin_key(x_admin_api_key: str = Header(..., alias="X-Admin-Api-Key")):
    if not hmac.compare_digest(x_admin_api_key, settings.ADMIN_API_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API key")


@router.post("", status_code=201)
async def create_webhook(
    payload: dict,
    _: None = Depends(verify_admin_key),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    url = payload.get("url")
    events = payload.get("events", [])
    description = payload.get("description")
    if not url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url required")
    if not events:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="events required")
    wh, secret = await WebhookService.register(current_user.id, url, events, description, db)
    await db.commit()
    return {
        "id": str(wh.id),
        "url": wh.url,
        "events": wh.events,
        "description": wh.description,
        "active": wh.active,
        "created_at": wh.created_at.isoformat(),
        "secret": secret,
    }


@router.get("")
async def list_webhooks(
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    webhooks = await WebhookService.list_all(db)
    return [
        {
            "id": str(wh.id),
            "url": wh.url,
            "events": wh.events,
            "description": wh.description,
            "active": wh.active,
            "created_at": wh.created_at.isoformat(),
        }
        for wh in webhooks
    ]


@router.get("/{webhook_id}")
async def get_webhook(
    webhook_id: uuid.UUID,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    wh = await WebhookService.get(webhook_id, db)
    if wh is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return {
        "id": str(wh.id),
        "url": wh.url,
        "events": wh.events,
        "description": wh.description,
        "active": wh.active,
        "created_at": wh.created_at.isoformat(),
    }


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: uuid.UUID,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    ok = await WebhookService.deactivate(webhook_id, db)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    await db.commit()


@router.get("/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    after_id: uuid.UUID | None = Query(None),
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    wh = await WebhookService.get(webhook_id, db)
    if wh is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    deliveries = await WebhookService.list_deliveries(webhook_id, limit, after_id, db)
    return [
        {
            "id": str(d.id),
            "event": d.event,
            "status": d.status,
            "attempts": d.attempts,
            "last_error": d.last_error,
            "last_response_status": d.last_response_status,
            "created_at": d.created_at.isoformat(),
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        }
        for d in deliveries
    ]
