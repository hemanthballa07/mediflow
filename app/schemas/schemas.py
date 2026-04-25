import uuid
from datetime import datetime, date, time
from typing import Any
from typing import Literal
from pydantic import BaseModel, EmailStr


# ── Catalog ───────────────────────────────────────────────────────────────────

class SpecialtyOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str

    model_config = {"from_attributes": True}


class SpecialtyCreate(BaseModel):
    name: str
    code: str


class FacilityOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    address: str | None
    timezone: str
    active: bool

    model_config = {"from_attributes": True}


class FacilityCreate(BaseModel):
    name: str
    code: str
    address: str | None = None
    timezone: str = "America/New_York"


class DepartmentOut(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    specialty_id: uuid.UUID | None
    name: str
    code: str

    model_config = {"from_attributes": True}


class DepartmentCreate(BaseModel):
    facility_id: uuid.UUID
    specialty_id: uuid.UUID | None = None
    name: str
    code: str


class RoomOut(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    department_id: uuid.UUID | None
    name: str
    kind: str
    active: bool

    model_config = {"from_attributes": True}


class RoomCreate(BaseModel):
    facility_id: uuid.UUID
    department_id: uuid.UUID | None = None
    name: str
    kind: str  # exam | procedure | imaging | ward


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    service: str
    db: Literal["ok", "error"]
    redis: Literal["ok", "error"]


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Literal["patient", "doctor"] = "patient"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Appointment Types ─────────────────────────────────────────────────────────

class AppointmentTypeCreate(BaseModel):
    department_id: uuid.UUID
    name: str
    duration_min: int = 30
    buffer_min: int = 10
    requires_referral: bool = False
    requires_fasting: bool = False
    color: str | None = None


class AppointmentTypeOut(BaseModel):
    id: uuid.UUID
    department_id: uuid.UUID
    name: str
    duration_min: int
    buffer_min: int
    requires_referral: bool
    requires_fasting: bool
    color: str | None
    active: bool

    model_config = {"from_attributes": True}


# ── Doctor Schedules ──────────────────────────────────────────────────────────

class DoctorScheduleCreate(BaseModel):
    doctor_id: uuid.UUID
    facility_id: uuid.UUID
    day_of_week: int              # 0=Mon … 6=Sun
    start_time: time
    end_time: time
    slot_duration_min: int = 30
    effective_from: date
    effective_to: date | None = None


class DoctorScheduleOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    facility_id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time
    slot_duration_min: int
    effective_from: date
    effective_to: date | None

    model_config = {"from_attributes": True}


class SlotGenerateRequest(BaseModel):
    doctor_id: uuid.UUID
    from_date: date
    to_date: date


class DoctorTimeOffCreate(BaseModel):
    doctor_id: uuid.UUID
    start_ts: datetime
    end_ts: datetime
    reason: str | None = None


class DoctorTimeOffOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    start_ts: datetime
    end_ts: datetime
    reason: str | None

    model_config = {"from_attributes": True}


# ── Slots ─────────────────────────────────────────────────────────────────────

class SlotCreate(BaseModel):
    doctor_id: uuid.UUID
    date: date
    start_time: time
    end_time: time


class DoctorOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    specialty: str
    facility_id: uuid.UUID | None
    department_id: uuid.UUID | None
    specialty_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class SlotOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    facility_id: uuid.UUID | None
    department_id: uuid.UUID | None
    date: date
    start_time: time
    end_time: time
    status: str

    model_config = {"from_attributes": True}


# ── Bookings ──────────────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    slot_id: uuid.UUID
    appointment_type_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    reason_for_visit: str | None = None


class BookingOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    slot_id: uuid.UUID
    appointment_type_id: uuid.UUID | None
    room_id: uuid.UUID | None
    status: str
    reason_for_visit: str | None
    notes: str | None
    checked_in_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingStatusUpdate(BaseModel):
    notes: str | None = None


class BookingCancel(BaseModel):
    reason: str | None = None


# ── Lab Reports ───────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    patient_id: uuid.UUID
    report_type: str
    data: str | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    report_type: str
    status: str
    data: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportPage(BaseModel):
    items: list[ReportOut]
    next_cursor: uuid.UUID | None = None


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditLogOut(BaseModel):
    id: int
    ts: datetime
    user_id: uuid.UUID | None
    action: str
    target: str | None
    details: dict[str, Any] | None

    model_config = {"from_attributes": True}


# ── Generic ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
