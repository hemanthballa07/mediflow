import uuid
import hmac
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db.session import get_db
from app.models.models import AuditLog, Slot, Doctor
from app.schemas.schemas import (
    AuditLogOut, SlotCreate, SlotOut,
    FacilityCreate, FacilityOut,
    DepartmentCreate, DepartmentOut,
    SpecialtyCreate, SpecialtyOut,
    RoomCreate, RoomOut,
    AppointmentTypeCreate, AppointmentTypeOut,
    DoctorScheduleCreate, DoctorScheduleOut,
    DoctorTimeOffCreate, DoctorTimeOffOut,
    SlotGenerateRequest,
)
from app.services.catalog_service import CatalogService
from app.services.schedule_service import ScheduleService
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


@router.post("/appointment-types", response_model=AppointmentTypeOut, status_code=201)
async def create_appointment_type(
    payload: AppointmentTypeCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    from app.models.models import AppointmentType
    apt = AppointmentType(
        department_id=payload.department_id,
        name=payload.name,
        duration_min=payload.duration_min,
        buffer_min=payload.buffer_min,
        requires_referral=payload.requires_referral,
        requires_fasting=payload.requires_fasting,
        color=payload.color,
    )
    db.add(apt)
    await db.commit()
    await db.refresh(apt)
    return AppointmentTypeOut.model_validate(apt)


@router.get("/appointment-types", response_model=list[AppointmentTypeOut])
async def list_appointment_types(
    department_id: uuid.UUID | None = Query(None),
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    from app.models.models import AppointmentType
    q = select(AppointmentType).where(AppointmentType.active == True)
    if department_id:
        q = q.where(AppointmentType.department_id == department_id)
    result = await db.execute(q.order_by(AppointmentType.name))
    return [AppointmentTypeOut.model_validate(a) for a in result.scalars().all()]


@router.post("/doctors/{doctor_id}/schedule", response_model=DoctorScheduleOut, status_code=201)
async def create_doctor_schedule(
    doctor_id: uuid.UUID,
    payload: DoctorScheduleCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return DoctorScheduleOut.model_validate(
        await ScheduleService.create_schedule(
            doctor_id=doctor_id,
            facility_id=payload.facility_id,
            day_of_week=payload.day_of_week,
            start_time=payload.start_time,
            end_time=payload.end_time,
            slot_duration_min=payload.slot_duration_min,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            db=db,
        )
    )


@router.get("/doctors/{doctor_id}/schedule", response_model=list[DoctorScheduleOut])
async def list_doctor_schedule(
    doctor_id: uuid.UUID,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return [DoctorScheduleOut.model_validate(s)
            for s in await ScheduleService.list_schedules(doctor_id, db)]


@router.post("/doctors/{doctor_id}/time-off", response_model=DoctorTimeOffOut, status_code=201)
async def create_time_off(
    doctor_id: uuid.UUID,
    payload: DoctorTimeOffCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return DoctorTimeOffOut.model_validate(
        await ScheduleService.create_time_off(
            doctor_id=doctor_id,
            start_ts=payload.start_ts,
            end_ts=payload.end_ts,
            reason=payload.reason,
            db=db,
        )
    )


@router.get("/doctors/{doctor_id}/time-off", response_model=list[DoctorTimeOffOut])
async def list_time_off(
    doctor_id: uuid.UUID,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return [DoctorTimeOffOut.model_validate(t)
            for t in await ScheduleService.list_time_off(doctor_id, db)]


@router.post("/slots/generate", status_code=200)
async def generate_slots(
    payload: SlotGenerateRequest,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Generate slots from doctor schedule records for a date range. Idempotent."""
    created = await ScheduleService.generate_slots(
        payload.doctor_id, payload.from_date, payload.to_date, db
    )
    return {"slots_created": created}


@router.post("/slots", response_model=SlotOut, status_code=201)
async def create_slot(
    payload: SlotCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Create an appointment slot for a doctor."""
    if payload.end_time <= payload.start_time:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="end_time must be after start_time")
    if payload.date < datetime.now(timezone.utc).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Slot date must not be in the past")
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


@router.post("/specialties", response_model=SpecialtyOut, status_code=201)
async def create_specialty(
    payload: SpecialtyCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.create_specialty(payload.name, payload.code, db)


@router.post("/facilities", response_model=FacilityOut, status_code=201)
async def create_facility(
    payload: FacilityCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.create_facility(
        payload.name, payload.code, payload.address, payload.timezone, db
    )


@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.create_department(
        payload.facility_id, payload.specialty_id, payload.name, payload.code, db
    )


@router.post("/rooms", response_model=RoomOut, status_code=201)
async def create_room(
    payload: RoomCreate,
    _: None = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    return await CatalogService.create_room(
        payload.facility_id, payload.department_id, payload.name, payload.kind, db
    )


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
