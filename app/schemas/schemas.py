import uuid
from datetime import datetime, date, time
from typing import Any
from pydantic import BaseModel, EmailStr, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "patient"

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("patient", "doctor", "admin"):
            raise ValueError("role must be patient, doctor, or admin")
        return v


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


# ── Slots ─────────────────────────────────────────────────────────────────────

class SlotCreate(BaseModel):
    doctor_id: uuid.UUID
    date: date
    start_time: time
    end_time: time


class SlotOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    date: date
    start_time: time
    end_time: time
    status: str

    model_config = {"from_attributes": True}


# ── Bookings ──────────────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    slot_id: uuid.UUID


class BookingOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    slot_id: uuid.UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


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
    next_cursor: uuid.UUID | None   # keyset pagination cursor


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
