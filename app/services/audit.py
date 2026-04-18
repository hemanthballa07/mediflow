import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import AuditLog


class AuditService:
    @staticmethod
    async def log(
        db: AsyncSession,
        action: str,
        user_id: uuid.UUID | None = None,
        target: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLog(
            ts=datetime.now(timezone.utc),
            user_id=user_id,
            action=action,
            target=target,
            details=details,
        )
        db.add(entry)
        # Use flush so the entry is part of the current transaction
        # but we don't commit here — caller controls the transaction boundary.
        await db.flush()
