import uuid
from datetime import date
from fastapi import APIRouter, Depends, Header, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.session import get_db
from app.db.redis import get_redis
from app.schemas.schemas import BookingCreate, BookingOut, BookingCancel
from app.services.booking import BookingService
from app.api.v1.deps import get_current_user
from app.models.models import User
from app.core.limiter import limiter, get_user_id_from_request

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("", status_code=201)
@limiter.limit("10/hour", key_func=get_user_id_from_request)
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


@router.get("/slots/available")
async def get_available_slots(
    doctor_id: uuid.UUID,
    date: date,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Get available slots for a doctor on a given date. Redis cache-aside, 30s TTL."""
    return await BookingService.get_available_slots(doctor_id, str(date), db, redis)
