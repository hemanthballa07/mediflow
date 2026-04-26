import uuid
from datetime import datetime, date, time, timezone
from sqlalchemy import (
    String, Text, Boolean, DateTime, Date, Time, Numeric, Integer,
    ForeignKey, UniqueConstraint, Index, event, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────
# Specialties
# ─────────────────────────────────────────
class Specialty(Base):
    __tablename__ = "specialties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)          # "Cardiology"
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # "CARD"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    departments: Mapped[list["Department"]] = relationship("Department", back_populates="specialty")
    doctors: Mapped[list["Doctor"]] = relationship("Doctor", back_populates="specialty_ref")


# ─────────────────────────────────────────
# Facilities
# ─────────────────────────────────────────
class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # "MGH"
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="America/New_York")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    departments: Mapped[list["Department"]] = relationship("Department", back_populates="facility")
    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="facility")
    doctors: Mapped[list["Doctor"]] = relationship("Doctor", back_populates="facility")


# ─────────────────────────────────────────
# Departments
# ─────────────────────────────────────────
class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("facility_id", "code", name="uq_dept_facility_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("specialties.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)    # "CARD", "ER", "RAD"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    facility: Mapped["Facility"] = relationship("Facility", back_populates="departments")
    specialty: Mapped["Specialty | None"] = relationship("Specialty", back_populates="departments")
    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="department")
    doctors: Mapped[list["Doctor"]] = relationship("Doctor", back_populates="department")


# ─────────────────────────────────────────
# Rooms
# ─────────────────────────────────────────
class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)          # "Room 204"
    kind: Mapped[str] = mapped_column(String(20), nullable=False)    # exam | procedure | imaging | ward
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    facility: Mapped["Facility"] = relationship("Facility", back_populates="rooms")
    department: Mapped["Department | None"] = relationship("Department", back_populates="rooms")


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
    home_facility_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="user")
    lab_reports: Mapped[list["LabReport"]] = relationship("LabReport", back_populates="patient")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship("RefreshToken", back_populates="user")
    preferences: Mapped["PatientPreference | None"] = relationship(
        "PatientPreference", back_populates="user", uselist=False
    )
    waitlist_entries: Mapped[list["WaitlistEntry"]] = relationship(
        "WaitlistEntry", back_populates="patient"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user"
    )


# ─────────────────────────────────────────
# Doctors
# ─────────────────────────────────────────
class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    specialty: Mapped[str] = mapped_column(Text, nullable=False)     # free-text kept for backward compat
    facility_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    specialty_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("specialties.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    facility: Mapped["Facility | None"] = relationship("Facility", back_populates="doctors")
    department: Mapped["Department | None"] = relationship("Department", back_populates="doctors")
    specialty_ref: Mapped["Specialty | None"] = relationship("Specialty", back_populates="doctors")
    slots: Mapped[list["Slot"]] = relationship("Slot", back_populates="doctor")
    schedules: Mapped[list["DoctorSchedule"]] = relationship("DoctorSchedule", back_populates="doctor")
    time_off: Mapped[list["DoctorTimeOff"]] = relationship("DoctorTimeOff", back_populates="doctor")


# ─────────────────────────────────────────
# Slots
# ─────────────────────────────────────────
class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        Index("ix_slots_doctor_date", "doctor_id", "date", "start_time"),
        Index("ix_slots_facility_date", "facility_id", "date", "start_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")  # available | booked | cancelled

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="slots")
    booking: Mapped["Booking | None"] = relationship("Booking", back_populates="slot", uselist=False)


# ─────────────────────────────────────────
# Appointment Types
# ─────────────────────────────────────────
class AppointmentType(Base):
    __tablename__ = "appointment_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    department_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)              # "Follow-up", "New Patient", "Procedure"
    duration_min: Mapped[int] = mapped_column(nullable=False, default=30)
    buffer_min: Mapped[int] = mapped_column(nullable=False, default=10)  # buffer after appointment
    requires_referral: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_fasting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # hex color for calendar UI
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    department: Mapped["Department"] = relationship("Department")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="appointment_type")


# ─────────────────────────────────────────
# Doctor Schedules (recurring availability)
# ─────────────────────────────────────────
class DoctorSchedule(Base):
    __tablename__ = "doctor_schedules"
    __table_args__ = (
        Index("ix_doctor_schedules_doctor", "doctor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(nullable=False)             # 0=Mon … 6=Sun
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_duration_min: Mapped[int] = mapped_column(nullable=False, default=30)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # None = indefinite

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="schedules")
    facility: Mapped["Facility"] = relationship("Facility")


# ─────────────────────────────────────────
# Doctor Time Off
# ─────────────────────────────────────────
class DoctorTimeOff(Base):
    __tablename__ = "doctor_time_off"
    __table_args__ = (
        Index("ix_doctor_time_off_doctor", "doctor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    doctor: Mapped["Doctor"] = relationship("Doctor", back_populates="time_off")


# ─────────────────────────────────────────
# Bookings
# ─────────────────────────────────────────
class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("uq_active_booking_per_slot", "slot_id", unique=True,
              postgresql_where=text("status = 'scheduled'")),
        Index("ix_bookings_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    slot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("slots.id"), nullable=False)
    appointment_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("appointment_types.id"), nullable=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    # scheduled | checked_in | in_progress | completed | no_show | cancelled
    reason_for_visit: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="bookings")
    slot: Mapped["Slot"] = relationship("Slot", back_populates="booking")
    appointment_type: Mapped["AppointmentType | None"] = relationship("AppointmentType", back_populates="bookings")
    room: Mapped["Room | None"] = relationship("Room")


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
    facility_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)   # blood | xray | urine | etc.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")  # PENDING | READY | ARCHIVED
    data: Mapped[str | None] = mapped_column(Text, nullable=True)          # report content / reference
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient: Mapped["User"] = relationship("User", back_populates="lab_reports")


# ─────────────────────────────────────────
# Audit Log — append-only
# ─────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


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
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


# ─────────────────────────────────────────
# Patient Preferences
# ─────────────────────────────────────────
class PatientPreference(Base):
    __tablename__ = "patient_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    preferred_channel: Mapped[str] = mapped_column(String(10), nullable=False, default="email")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    reminder_hours_before: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=lambda: [24, 2]
    )
    email_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sms_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    push_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="preferences")


# ─────────────────────────────────────────
# Waitlist Entries
# ─────────────────────────────────────────
class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"
    __table_args__ = (
        Index("ix_waitlist_dept_status_created", "department_id", "status", "created_at"),
        Index("ix_waitlist_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False
    )
    appointment_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_types.id"), nullable=True
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting")
    # waiting | notified | expired | cancelled
    priority: Mapped[int] = mapped_column(nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    patient: Mapped["User"] = relationship("User", back_populates="waitlist_entries")
    department: Mapped["Department"] = relationship("Department")
    appointment_type: Mapped["AppointmentType | None"] = relationship("AppointmentType")
    doctor: Mapped["Doctor | None"] = relationship("Doctor")


# ─────────────────────────────────────────
# Notifications Outbox
# ─────────────────────────────────────────
class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_pending_next", "status", "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_notifications_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(10), nullable=False)   # email | sms | push
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending | sent | failed | skipped
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship("User", back_populates="notifications")
