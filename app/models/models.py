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
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_hash: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
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
    password_history: Mapped[list["PasswordHistory"]] = relationship(
        "PasswordHistory", back_populates="user", order_by="PasswordHistory.created_at.desc()"
    )
    deletion_requests: Mapped[list["DeletionRequest"]] = relationship(
        "DeletionRequest", back_populates="patient", foreign_keys="DeletionRequest.patient_id"
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
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)   # blood | xray | urine | etc.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")  # PENDING | READY | ARCHIVED
    data: Mapped[str | None] = mapped_column(Text, nullable=True)          # report content / reference
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient: Mapped["User"] = relationship("User", back_populates="lab_reports")
    order: Mapped["Order | None"] = relationship("Order", back_populates="lab_reports")


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


# ─────────────────────────────────────────
# Encounters
# ─────────────────────────────────────────
class Encounter(Base):
    __tablename__ = "encounters"
    __table_args__ = (
        Index("ix_encounters_patient_date", "patient_id", "encounter_date"),
        Index("ix_encounters_doctor", "doctor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    encounter_type: Mapped[str] = mapped_column(String(30), nullable=False, default="office_visit")
    # office_visit | telehealth | emergency | procedure | walk_in
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    # open | completed | cancelled
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    encounter_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    booking: Mapped["Booking | None"] = relationship("Booking")
    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    doctor: Mapped["Doctor"] = relationship("Doctor")
    facility: Mapped["Facility | None"] = relationship("Facility")
    vitals: Mapped[list["Vital"]] = relationship("Vital", back_populates="encounter", cascade="all, delete-orphan")
    diagnoses: Mapped[list["Diagnosis"]] = relationship("Diagnosis", back_populates="encounter", cascade="all, delete-orphan")
    prescriptions: Mapped[list["Prescription"]] = relationship("Prescription", back_populates="encounter", cascade="all, delete-orphan")


# ─────────────────────────────────────────
# Vitals
# ─────────────────────────────────────────
class Vital(Base):
    __tablename__ = "vitals"
    __table_args__ = (
        Index("ix_vitals_encounter", "encounter_id"),
        Index("ix_vitals_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    bp_systolic: Mapped[int | None] = mapped_column(Integer, nullable=True)     # mmHg
    bp_diastolic: Mapped[int | None] = mapped_column(Integer, nullable=True)    # mmHg
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)      # bpm
    temperature_f: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # °F
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    spo2: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)    # %
    respiratory_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)  # breaths/min
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="vitals")
    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    recorder: Mapped["User"] = relationship("User", foreign_keys=[recorded_by])


# ─────────────────────────────────────────
# Diagnoses
# ─────────────────────────────────────────
class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        Index("ix_diagnoses_encounter", "encounter_id"),
        Index("ix_diagnoses_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    icd10_code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis_type: Mapped[str] = mapped_column(String(20), nullable=False, default="primary")
    # primary | secondary | differential
    onset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="diagnoses")
    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])


# ─────────────────────────────────────────
# Prescriptions
# ─────────────────────────────────────────
class Prescription(Base):
    __tablename__ = "prescriptions"
    __table_args__ = (
        Index("ix_prescriptions_encounter", "encounter_id"),
        Index("ix_prescriptions_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    drug_name: Mapped[str] = mapped_column(Text, nullable=False)
    dose: Mapped[str] = mapped_column(String(50), nullable=False)
    frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    route: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # oral | IV | IM | topical | inhaled | sublingual | other
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    refills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    prescriber_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # active | completed | cancelled | on_hold
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="prescriptions")
    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    prescriber: Mapped["User"] = relationship("User", foreign_keys=[prescriber_id])


# ─────────────────────────────────────────
# Allergies  (patient-scoped, not per encounter)
# ─────────────────────────────────────────
class Allergy(Base):
    __tablename__ = "allergies"
    __table_args__ = (
        Index("ix_allergies_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    allergen: Mapped[str] = mapped_column(Text, nullable=False)
    reaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    # mild | moderate | severe | life_threatening | unknown
    onset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # active | inactive
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    recorder: Mapped["User"] = relationship("User", foreign_keys=[recorded_by])


# ─────────────────────────────────────────
# Problem List  (chronic conditions, patient-scoped)
# ─────────────────────────────────────────
class ProblemList(Base):
    __tablename__ = "problem_list"
    __table_args__ = (
        Index("ix_problem_list_patient", "patient_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    icd10_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # active | inactive | resolved
    onset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    resolved_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    noted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    noter: Mapped["User"] = relationship("User", foreign_keys=[noted_by])


# ─────────────────────────────────────────
# Orders
# ─────────────────────────────────────────
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_encounter", "encounter_id"),
        Index("ix_orders_patient", "patient_id"),
        Index("ix_orders_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ordering_doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    cpt_code: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="routine")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    resulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    encounter: Mapped["Encounter"] = relationship("Encounter")
    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    ordering_doctor: Mapped["Doctor"] = relationship("Doctor")
    lab_reports: Mapped[list["LabReport"]] = relationship("LabReport", back_populates="order")


# ─────────────────────────────────────────
# Referrals
# ─────────────────────────────────────────
class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        Index("ix_referrals_patient", "patient_id"),
        Index("ix_referrals_referring_doctor", "referring_doctor_id"),
        Index("ix_referrals_receiving_dept_status", "receiving_department_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    referring_doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    receiving_department_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[str] = mapped_column(String(10), nullable=False, default="routine")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    referred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    referring_doctor: Mapped["Doctor"] = relationship("Doctor", foreign_keys=[referring_doctor_id])
    receiving_department: Mapped["Department"] = relationship("Department")
    encounter: Mapped["Encounter | None"] = relationship("Encounter")


# ─────────────────────────────────────────
# Insurance Plans
# ─────────────────────────────────────────
class InsurancePlan(Base):
    __tablename__ = "insurance_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    payer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # HMO | PPO | EPO | POS | HDHP
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient_policies: Mapped[list["PatientInsurance"]] = relationship("PatientInsurance", back_populates="insurance_plan")


# ─────────────────────────────────────────
# Patient Insurance
# ─────────────────────────────────────────
class PatientInsurance(Base):
    __tablename__ = "patient_insurance"
    __table_args__ = (
        Index("ix_patient_insurance_patient", "patient_id"),
        Index(
            "uq_patient_primary_insurance", "patient_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    insurance_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("insurance_plans.id"), nullable=False)
    member_id: Mapped[str] = mapped_column(String(100), nullable=False)
    group_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    insurance_plan: Mapped["InsurancePlan"] = relationship("InsurancePlan", back_populates="patient_policies")
    claims: Mapped[list["Claim"]] = relationship("Claim", back_populates="patient_insurance")


# ─────────────────────────────────────────
# Charge Masters (CPT pricing)
# ─────────────────────────────────────────
class ChargeMaster(Base):
    __tablename__ = "charge_masters"
    __table_args__ = (
        Index("ix_charge_masters_cpt", "cpt_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    cpt_code: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    department: Mapped["Department | None"] = relationship("Department")


# ─────────────────────────────────────────
# Claims
# ─────────────────────────────────────────
class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_patient_status", "patient_id", "status"),
        Index("ix_claims_encounter", "encounter_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    patient_insurance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patient_insurance.id"), nullable=False)
    ordering_doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | submitted | accepted | rejected | paid
    total_charged: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_paid: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    encounter: Mapped["Encounter"] = relationship("Encounter")
    patient_insurance: Mapped["PatientInsurance"] = relationship("PatientInsurance", back_populates="claims")
    ordering_doctor: Mapped["Doctor"] = relationship("Doctor")
    line_items: Mapped[list["ClaimLineItem"]] = relationship("ClaimLineItem", back_populates="claim", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="claim")


# ─────────────────────────────────────────
# Claim Line Items
# ─────────────────────────────────────────
class ClaimLineItem(Base):
    __tablename__ = "claim_line_items"
    __table_args__ = (
        Index("ix_claim_line_items_claim", "claim_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    cpt_code: Mapped[str] = mapped_column(String(10), nullable=False)
    icd10_codes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    claim: Mapped["Claim"] = relationship("Claim", back_populates="line_items")
    order: Mapped["Order | None"] = relationship("Order")


# ─────────────────────────────────────────
# Payments
# ─────────────────────────────────────────
class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_claim", "claim_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False)
    payer: Mapped[str] = mapped_column(String(20), nullable=False)
    # patient | insurance
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(10), nullable=False)
    # check | eft | card | cash
    reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    claim: Mapped["Claim"] = relationship("Claim", back_populates="payments")


# ─────────────────────────────────────────
# Password History
# ─────────────────────────────────────────
class PasswordHistory(Base):
    __tablename__ = "password_history"
    __table_args__ = (
        Index("ix_password_history_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="password_history")


# ─────────────────────────────────────────
# Deletion Requests (GDPR)
# ─────────────────────────────────────────
class DeletionRequest(Base):
    __tablename__ = "deletion_requests"
    __table_args__ = (
        Index("ix_deletion_requests_patient_status", "patient_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending | approved | rejected | completed
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient: Mapped["User"] = relationship("User", back_populates="deletion_requests", foreign_keys=[patient_id])
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by])
