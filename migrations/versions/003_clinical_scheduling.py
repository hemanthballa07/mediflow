"""clinical scheduling: appointment types, doctor schedules, time off, booking status machine

Revision ID: 003_clinical_scheduling
Revises: 002_multi_tenant
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003_clinical_scheduling"
down_revision = "002_multi_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── appointment_types ─────────────────────────────────────────────────────
    op.create_table(
        "appointment_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("duration_min", sa.Integer, nullable=False, server_default="30"),
        sa.Column("buffer_min", sa.Integer, nullable=False, server_default="10"),
        sa.Column("requires_referral", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("requires_fasting", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_appointment_types_dept", "appointment_types", ["department_id"])

    # ── doctor_schedules ──────────────────────────────────────────────────────
    op.create_table(
        "doctor_schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False),
        sa.Column("start_time", sa.Time, nullable=False),
        sa.Column("end_time", sa.Time, nullable=False),
        sa.Column("slot_duration_min", sa.Integer, nullable=False, server_default="30"),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
    )
    op.create_index("ix_doctor_schedules_doctor", "doctor_schedules", ["doctor_id"])

    # ── doctor_time_off ───────────────────────────────────────────────────────
    op.create_table(
        "doctor_time_off",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
    )
    op.create_index("ix_doctor_time_off_doctor", "doctor_time_off", ["doctor_id"])

    # ── extend bookings ───────────────────────────────────────────────────────
    op.add_column("bookings", sa.Column("appointment_type_id", UUID(as_uuid=True),
                  sa.ForeignKey("appointment_types.id"), nullable=True))
    op.add_column("bookings", sa.Column("room_id", UUID(as_uuid=True),
                  sa.ForeignKey("rooms.id"), nullable=True))
    op.add_column("bookings", sa.Column("reason_for_visit", sa.Text, nullable=True))
    op.add_column("bookings", sa.Column("notes", sa.Text, nullable=True))
    op.add_column("bookings", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    # Migrate existing 'active' → 'scheduled', 'cancelled' stays 'cancelled'
    op.execute("UPDATE bookings SET status = 'scheduled' WHERE status = 'active'")

    # Replace partial unique index: was 'active', now 'scheduled'
    op.drop_index("uq_active_booking_per_slot", "bookings")
    op.create_index(
        "uq_scheduled_booking_per_slot", "bookings", ["slot_id"],
        unique=True, postgresql_where=sa.text("status = 'scheduled'"),
    )


def downgrade() -> None:
    op.drop_index("uq_scheduled_booking_per_slot", "bookings")
    op.create_index(
        "uq_active_booking_per_slot", "bookings", ["slot_id"],
        unique=True, postgresql_where=sa.text("status = 'active'"),
    )
    op.execute("UPDATE bookings SET status = 'active' WHERE status = 'scheduled'")
    op.drop_column("bookings", "completed_at")
    op.drop_column("bookings", "started_at")
    op.drop_column("bookings", "checked_in_at")
    op.drop_column("bookings", "notes")
    op.drop_column("bookings", "reason_for_visit")
    op.drop_column("bookings", "room_id")
    op.drop_column("bookings", "appointment_type_id")
    op.drop_index("ix_doctor_time_off_doctor", "doctor_time_off")
    op.drop_table("doctor_time_off")
    op.drop_index("ix_doctor_schedules_doctor", "doctor_schedules")
    op.drop_table("doctor_schedules")
    op.drop_index("ix_appointment_types_dept", "appointment_types")
    op.drop_table("appointment_types")
