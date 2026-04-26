import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification
from app.core.logging import get_logger

log = get_logger(__name__)


class NotificationService:

    @staticmethod
    async def enqueue(
        db: AsyncSession,
        user_id: uuid.UUID,
        channel: str,
        notif_type: str,
        recipient: str,
        body: str,
        subject: str | None = None,
        context: dict | None = None,
        max_attempts: int = 3,
    ) -> Notification:
        notif = Notification(
            user_id=user_id,
            channel=channel,
            type=notif_type,
            subject=subject,
            body=body,
            recipient=recipient,
            status="pending",
            max_attempts=max_attempts,
            next_attempt_at=datetime.now(timezone.utc),
            context=context,
        )
        db.add(notif)
        await db.flush()
        log.info("Notification enqueued", extra={
            "type": notif_type, "channel": channel, "user_id": str(user_id)
        })
        return notif
