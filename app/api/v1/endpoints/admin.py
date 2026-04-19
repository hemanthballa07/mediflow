import uuid
import hmac
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.session import get_db
from app.models.models import AuditLog, Slot, Doctor
from app.schemas.schemas import AuditLogOut, SlotCreate, SlotOut
from app.core.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def verify_admin_key(x_admin_api_key: str = Header(..., alias="X-Admin-Api-Key")):
    if not hmac.compare_digest(x_admin_api_key, settings.ADMIN_API_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API key")


@router.get("/audit", response_model=list[AuditLogOut])
async def get_audit_log(
    limit: int = Query(50, ge=1, le=500),
    after_id: int | None = Query(None),
    action: str | None = Query(None),
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Paginated audit log. Pass after_id for forward pagination.
    Filter by action (e.g. BOOKING_CREATED, AUTH_FAILURE, TOKEN_FAMILY_REVOKED).
    """
    q = select(AuditLog)
    if after_id:
        q = q.where(AuditLog.id > after_id)
    if action:
        q = q.where(AuditLog.action == action)
    q = q.order_by(AuditLog.id).limit(limit)
    result = await db.execute(q)
    return [AuditLogOut.model_validate(row) for row in result.scalars().all()]


@router.post("/slots", response_model=SlotOut, status_code=201)
async def create_slot(
    payload: SlotCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Create an appointment slot for a doctor."""
    if payload.end_time <= payload.start_time:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="end_time must be after start_time")
    if payload.date < datetime.now(timezone.utc).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Slot date must not be in the past")
    # Verify doctor exists
    result = await db.execute(select(Doctor).where(Doctor.id == payload.doctor_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Doctor not found")

    slot = Slot(
        doctor_id=payload.doctor_id,
        date=payload.date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status="available",
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return SlotOut.model_validate(slot)


@router.get("/slots", response_model=list[SlotOut])
async def list_slots(
    doctor_id: uuid.UUID | None = Query(None),
    slot_status: str | None = Query(None),
    after_date: date | None = Query(None, description="Keyset cursor: return slots with date > after_date"),
    limit: int = Query(50, ge=1, le=200),
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    q = select(Slot)
    if doctor_id:
        q = q.where(Slot.doctor_id == doctor_id)
    if slot_status:
        q = q.where(Slot.status == slot_status)
    if after_date:
        q = q.where(Slot.date > after_date)
    q = q.order_by(Slot.date, Slot.start_time).limit(limit)
    result = await db.execute(q)
    return [SlotOut.model_validate(s) for s in result.scalars().all()]
