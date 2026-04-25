import uuid
from datetime import date
from fastapi import APIRouter, Depends, Header, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.session import get_db
from app.db.redis import get_redis
from app.schemas.schemas import BookingCreate, BookingOut, BookingCancel, BookingStatusUpdate
from app.services.booking import BookingService
from app.api.v1.deps import get_current_user
from app.models.models import User
from app.core.limiter import limiter, get_user_id_from_request
from app.core.config import get_settings as _get_settings

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", status_code=201)
@limiter.limit(lambda: _get_settings().BOOKING_RATE_LIMIT, key_func=get_user_id_from_request)
async def create_booking(
    request: Request,
    payload: BookingCreate,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Book a slot. Requires Idempotency-Key header (UUID).
    Returns 201 on first success, 200 on replay.
    Returns 409 if slot is already taken.
    """
    out, http_status = await BookingService.create_booking(
        user_id=current_user.id,
        slot_id=payload.slot_id,
        idempotency_key=idempotency_key,
        db=db,
        redis=redis,
        appointment_type_id=payload.appointment_type_id,
        room_id=payload.room_id,
        reason_for_visit=payload.reason_for_visit,
    )
    response.status_code = http_status
    return out


@router.delete("/{booking_id}", response_model=BookingOut)
async def cancel_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await BookingService.cancel_booking(booking_id, current_user.id, db, redis)


@router.post("/{booking_id}/check-in", response_model=BookingOut)
async def check_in(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BookingService.check_in(booking_id, current_user.id, current_user.role, db)


@router.post("/{booking_id}/start", response_model=BookingOut)
async def start_appointment(
    booking_id: uuid.UUID,
    payload: BookingStatusUpdate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notes = payload.notes if payload else None
    return await BookingService.start_appointment(booking_id, current_user.id, current_user.role, notes, db)


@router.post("/{booking_id}/complete", response_model=BookingOut)
async def complete_appointment(
    booking_id: uuid.UUID,
    payload: BookingStatusUpdate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notes = payload.notes if payload else None
    return await BookingService.complete_appointment(booking_id, current_user.id, current_user.role, notes, db)


@router.post("/{booking_id}/no-show", response_model=BookingOut)
async def mark_no_show(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await BookingService.mark_no_show(booking_id, current_user.id, current_user.role, db)


@router.get("/slots/available")
async def get_available_slots(
    doctor_id: uuid.UUID,
    date: date,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Get available slots for a doctor on a given date. Redis cache-aside, 30s TTL."""
    return await BookingService.get_available_slots(doctor_id, str(date), db, redis)
