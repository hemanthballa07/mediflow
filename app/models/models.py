import uuid
from datetime import datetime, date, time
from sqlalchemy import (
    String, Text, Boolean, DateTime, Date, Time, Numeric,
    ForeignKey, UniqueConstraint, Index, event
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────
# Users
# ─────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="patient")  # patient | doctor | admin
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="user")
    lab_reports: Mapped[list["LabReport"]] = relationship("LabReport", back_populates="patient")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="user")


# ─────────────────────────────────────────
# Doctors
# ─────────────────────────────────────────
class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    specialty: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    slots: Mapped[list["Slot"]] = relationship("Slot", back_populates="doctor")


# ─────────────────────────────────────────
# Slots
# ─────────────────────────────────────────
class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        Index("ix_slots_doctor_date", "doctor_id", "date", "start_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")  # available | booked | cancelled

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="slots")
    booking: Mapped["Booking | None"] = relationship("Booking", back_populates="slot", uselist=False)


# ─────────────────────────────────────────
# Bookings
# ─────────────────────────────────────────
class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("slot_id", name="uq_bookings_slot_id"),  # DB-level safety net
        Index("ix_bookings_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    slot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slots.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active | cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="bookings")
    slot: Mapped["Slot"] = relationship("Slot", back_populates="booking")


# ─────────────────────────────────────────
# Lab Reports
# ─────────────────────────────────────────
class LabReport(Base):
    __tablename__ = "lab_reports"
    __table_args__ = (
        Index("ix_lab_reports_patient_status_created", "patient_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)   # blood | xray | urine | etc.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")  # PENDING | READY | ARCHIVED
    data: Mapped[str | None] = mapped_column(Text, nullable=True)          # report content / reference
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    patient: Mapped["User"] = relationship("User", back_populates="lab_reports")


# ─────────────────────────────────────────
# Audit Log — append-only
# ─────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)   # BOOKING_CREATED | REPORT_ACCESSED | AUTH_FAILURE | etc.
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ─────────────────────────────────────────
# Idempotency Keys
# ─────────────────────────────────────────
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")  # PENDING | SUCCESS | ERROR
    response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# ─────────────────────────────────────────
# Refresh Tokens
# ─────────────────────────────────────────
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_family", "user_id", "family_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=_uuid)
    token_jti: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
