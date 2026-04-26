import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.models import WaitlistEntry, Department, User
from app.schemas.schemas import WaitlistEntryCreate, WaitlistEntryOut, WaitlistPositionOut
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.notification import NotificationService

log = get_logger(__name__)
settings = get_settings()


class WaitlistService:

    @staticmethod
    async def join(
        patient_id: uuid.UUID,
        payload: WaitlistEntryCreate,
        db: AsyncSession,
    ) -> WaitlistEntryOut:
        dept = await db.get(Department, payload.department_id)
        if not dept:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Department not found")

        q = select(WaitlistEntry).where(
            WaitlistEntry.patient_id == patient_id,
            WaitlistEntry.department_id == payload.department_id,
            WaitlistEntry.status == "waiting",
        )
        if payload.appointment_type_id:
            q = q.where(WaitlistEntry.appointment_type_id == payload.appointment_type_id)
        result = await db.execute(q)
        if result.scalar_one_or_none():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Already on waitlist for this department/type",
            )

        entry = WaitlistEntry(
            patient_id=patient_id,
            department_id=payload.department_id,
            appointment_type_id=payload.appointment_type_id,
            doctor_id=payload.doctor_id,
            notes=payload.notes,
            status="waiting",
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)

        log.info("Waitlist join", extra={
            "patient_id": str(patient_id), "dept_id": str(payload.department_id)
        })
        return WaitlistEntryOut.model_validate(entry)

    @staticmethod
    async def leave(
        entry_id: uuid.UUID,
        patient_id: uuid.UUID,
        db: AsyncSession,
    ) -> WaitlistEntryOut:
        result = await db.execute(
            select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Waitlist entry not found")
        if entry.patient_id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your waitlist entry")
        if entry.status not in ("waiting", "notified"):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel from status '{entry.status}'",
            )

        entry.status = "cancelled"
        entry.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return WaitlistEntryOut.model_validate(entry)

    @staticmethod
    async def get_position(
        entry_id: uuid.UUID,
        patient_id: uuid.UUID,
        db: AsyncSession,
    ) -> WaitlistPositionOut:
        result = await db.execute(
            select(WaitlistEntry).where(WaitlistEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Waitlist entry not found")
        if entry.patient_id != patient_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your waitlist entry")

        q = select(WaitlistEntry).where(
            WaitlistEntry.department_id == entry.department_id,
            WaitlistEntry.status == "waiting",
            WaitlistEntry.created_at < entry.created_at,
        )
        if entry.appointment_type_id:
            q = q.where(WaitlistEntry.appointment_type_id == entry.appointment_type_id)

        ahead = await db.execute(q)
        position = len(ahead.scalars().all()) + 1

        return WaitlistPositionOut(
            entry=WaitlistEntryOut.model_validate(entry),
            position=position,
        )

    @staticmethod
    async def list_active(
        patient_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[WaitlistEntryOut]:
        result = await db.execute(
            select(WaitlistEntry).where(
                WaitlistEntry.patient_id == patient_id,
                WaitlistEntry.status.in_(["waiting", "notified"]),
            ).order_by(WaitlistEntry.created_at)
        )
        return [WaitlistEntryOut.model_validate(e) for e in result.scalars().all()]

    @staticmethod
    async def promote_next(
        department_id: uuid.UUID,
        appointment_type_id: uuid.UUID | None,
        db: AsyncSession,
    ) -> None:
        """
        Find the highest-priority waiting patient for this dept/type and
        queue a WAITLIST_SLOT_AVAILABLE notification. Called after cancellation.
        """
        q = (
            select(WaitlistEntry)
            .where(
                WaitlistEntry.department_id == department_id,
                WaitlistEntry.status == "waiting",
            )
            .order_by(WaitlistEntry.priority.desc(), WaitlistEntry.created_at.asc())
        )
        if appointment_type_id:
            q = q.where(WaitlistEntry.appointment_type_id == appointment_type_id)

        result = await db.execute(q)
        entry = result.scalars().first()
        if not entry:
            return

        patient = await db.get(User, entry.patient_id)
        if not patient:
            return

        entry.status = "notified"
        entry.updated_at = datetime.now(timezone.utc)

        await NotificationService.enqueue(
            db=db,
            user_id=entry.patient_id,
            channel="email",
            notif_type="WAITLIST_SLOT_AVAILABLE",
            recipient=patient.email,
            subject="A slot is now available — MediFlow",
            body=(
                f"Dear {patient.name},\n\n"
                "A slot has opened up in your requested department. "
                "Log in to MediFlow and book your appointment before it fills up.\n\n"
                f"This notification is valid for {settings.WAITLIST_NOTIFICATION_EXPIRY_HOURS} hours.\n\n"
                "MediFlow"
            ),
            context={
                "waitlist_entry_id": str(entry.id),
                "department_id": str(department_id),
            },
        )

        log.info("Waitlist promoted", extra={
            "entry_id": str(entry.id), "patient_id": str(entry.patient_id)
        })
