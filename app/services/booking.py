import uuid
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
import redis.asyncio as aioredis

from app.models.models import Slot, Booking, IdempotencyKey, User
from app.schemas.schemas import BookingOut
from app.core.metrics import (
    bookings_created_total, booking_conflicts_total,
    booking_cancelled_total, idempotency_replays_total,
    cache_hits_total, cache_misses_total,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.audit import AuditService

log = get_logger(__name__)
settings = get_settings()


class BookingService:

    # ── Create booking ────────────────────────────────────────────────────────
    @staticmethod
    async def create_booking(
        user_id: uuid.UUID,
        slot_id: uuid.UUID,
        idempotency_key: str,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> tuple[BookingOut, int]:
        """
        Returns (BookingOut, http_status).
        Idempotent: same key returns the cached response.
        Uses SELECT FOR UPDATE SKIP LOCKED to prevent double-booking.
        """

        # ── 1. Idempotency check ──────────────────────────────────────────────
        existing = await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id,
                IdempotencyKey.key == idempotency_key,
            )
        )
        idem: IdempotencyKey | None = existing.scalar_one_or_none()

        if idem:
            if idem.status == "SUCCESS" and idem.response:
                idempotency_replays_total.inc()
                log.info("Idempotency replay", extra={"key": idempotency_key})
                return BookingOut(**idem.response), 200
            if idem.status == "PENDING":
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Request in progress")
            if idem.status == "ERROR":
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Previous attempt failed")

        # ── 2. Insert PENDING idempotency record ──────────────────────────────
        idem_record = IdempotencyKey(
            user_id=user_id,
            key=idempotency_key,
            status="PENDING",
        )
        db.add(idem_record)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Duplicate idempotency key")

        # ── 3. SELECT FOR UPDATE SKIP LOCKED — pessimistic slot lock ─────────
        result = await db.execute(
            text("""
                SELECT id FROM slots
                WHERE id = :slot_id
                  AND status = 'available'
                FOR UPDATE SKIP LOCKED
            """),
            {"slot_id": str(slot_id)},
        )
        locked_slot = result.fetchone()

        if not locked_slot:
            # Either slot doesn't exist, is already booked, or another transaction holds the lock
            booking_conflicts_total.inc()
            idem_record.status = "ERROR"
            idem_record.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await AuditService.log(
                db, action="BOOKING_CONFLICT",
                user_id=user_id,
                target=str(slot_id),
                details={"reason": "slot_unavailable_or_locked"},
            )
            await db.commit()
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Slot is not available")

        # ── 4. Create booking + mark slot booked ─────────────────────────────
        try:
            await db.execute(
                text("UPDATE slots SET status = 'booked' WHERE id = :slot_id"),
                {"slot_id": str(slot_id)},
            )
            booking = Booking(user_id=user_id, slot_id=slot_id, status="active")
            db.add(booking)
            await db.flush()  # triggers unique constraint if somehow a race slipped through

            # ── 5. Update idempotency record to SUCCESS ───────────────────────
            out = BookingOut.model_validate(booking)
            idem_record.status = "SUCCESS"
            idem_record.response = out.model_dump(mode="json")
            idem_record.updated_at = datetime.now(timezone.utc)

            await AuditService.log(
                db, action="BOOKING_CREATED",
                user_id=user_id,
                target=str(booking.id),
                details={"slot_id": str(slot_id)},
            )
            await db.commit()

        except IntegrityError:
            # Unique constraint on bookings(slot_id) fired — ultimate safety net
            await db.rollback()
            booking_conflicts_total.inc()
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Slot already booked (constraint)")

        bookings_created_total.inc()

        # ── 6. Invalidate slot availability cache ─────────────────────────────
        slot_res = await db.execute(select(Slot).where(Slot.id == slot_id))
        slot: Slot | None = slot_res.scalar_one_or_none()
        if slot:
            cache_key = f"slots:{slot.doctor_id}:{slot.date}"
            await redis.delete(cache_key)
            log.info("Cache invalidated", extra={"key": cache_key})

        log.info("Booking created", extra={"booking_id": str(booking.id), "user_id": str(user_id)})
        return out, 201

    # ── Get available slots (cache-aside) ─────────────────────────────────────
    @staticmethod
    async def get_available_slots(
        doctor_id: uuid.UUID,
        date_: str,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> list[dict]:
        cache_key = f"slots:{doctor_id}:{date_}"

        cached = await redis.get(cache_key)
        if cached:
            cache_hits_total.labels(cache_key_prefix="slots").inc()
            return json.loads(cached)

        cache_misses_total.labels(cache_key_prefix="slots").inc()
        result = await db.execute(
            select(Slot).where(
                Slot.doctor_id == doctor_id,
                Slot.date == date_,
                Slot.status == "available",
            ).order_by(Slot.start_time)
        )
        slots = result.scalars().all()
        data = [
            {"id": str(s.id), "start_time": str(s.start_time), "end_time": str(s.end_time)}
            for s in slots
        ]
        await redis.setex(cache_key, settings.SLOT_CACHE_TTL, json.dumps(data))
        return data

    # ── Cancel booking ────────────────────────────────────────────────────────
    @staticmethod
    async def cancel_booking(
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        db: AsyncSession,
        redis: aioredis.Redis,
    ) -> BookingOut:
        result = await db.execute(
            select(Booking).where(Booking.id == booking_id)
        )
        booking: Booking | None = result.scalar_one_or_none()

        if not booking:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Booking not found")
        if booking.user_id != user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your booking")
        if booking.status == "cancelled":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Already cancelled")

        slot_res = await db.execute(select(Slot).where(Slot.id == booking.slot_id))
        slot = slot_res.scalar_one_or_none()
        if slot:
            appointment_dt = datetime.combine(slot.date, slot.start_time, tzinfo=timezone.utc)
            deadline = appointment_dt - timedelta(hours=settings.CANCELLATION_WINDOW_HOURS)
            if datetime.now(timezone.utc) >= deadline:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=f"Cannot cancel within {settings.CANCELLATION_WINDOW_HOURS}h of appointment",
                )

        booking.status = "cancelled"

        # Free the slot back up
        await db.execute(
            text("UPDATE slots SET status = 'available' WHERE id = :slot_id"),
            {"slot_id": str(booking.slot_id)},
        )

        await AuditService.log(
            db, action="BOOKING_CANCELLED",
            user_id=user_id,
            target=str(booking_id),
        )
        await db.commit()
        booking_cancelled_total.inc()

        if slot:
            await redis.delete(f"slots:{slot.doctor_id}:{slot.date}")

        return BookingOut.model_validate(booking)
