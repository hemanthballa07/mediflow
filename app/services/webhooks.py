import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.models import Webhook, WebhookDelivery


def _sign(secret: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return f"sha256={sig}"


class WebhookService:

    @staticmethod
    async def register(
        user_id: uuid.UUID,
        url: str,
        events: list[str],
        description: str | None,
        db: AsyncSession,
    ) -> tuple["Webhook", str]:
        plaintext_secret = secrets.token_urlsafe(32)
        wh = Webhook(
            id=uuid.uuid4(),
            user_id=user_id,
            url=url,
            secret=plaintext_secret,
            events=events,
            description=description,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(wh)
        await db.flush()
        await db.refresh(wh)
        return wh, plaintext_secret

    @staticmethod
    async def list_all(db: AsyncSession) -> list["Webhook"]:
        result = await db.execute(select(Webhook).where(Webhook.active == True).order_by(Webhook.created_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def get(webhook_id: uuid.UUID, db: AsyncSession) -> "Webhook | None":
        result = await db.execute(select(Webhook).where(Webhook.id == webhook_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def deactivate(webhook_id: uuid.UUID, db: AsyncSession) -> bool:
        wh = await WebhookService.get(webhook_id, db)
        if wh is None:
            return False
        wh.active = False
        await db.flush()
        return True

    @staticmethod
    async def list_deliveries(
        webhook_id: uuid.UUID,
        limit: int,
        after_id: uuid.UUID | None,
        db: AsyncSession,
    ) -> list["WebhookDelivery"]:
        q = (
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.created_at.desc())
        )
        if after_id is not None:
            q = q.where(WebhookDelivery.id != after_id)
        q = q.limit(limit)
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def enqueue(event: str, payload: dict, db: AsyncSession) -> None:
        try:
            async with AsyncSessionLocal() as lookup_db:
                result = await lookup_db.execute(
                    select(Webhook).where(
                        Webhook.active == True,
                        Webhook.events.contains([event]),
                    )
                )
                webhooks = result.scalars().all()
        except Exception:
            return
        now = datetime.now(timezone.utc)
        for wh in webhooks:
            sig = _sign(wh.secret, payload)
            delivery = WebhookDelivery(
                id=uuid.uuid4(),
                webhook_id=wh.id,
                event=event,
                payload=payload,
                status="pending",
                attempts=0,
                next_retry_at=now,
                signature=sig,
                created_at=now,
            )
            db.add(delivery)
