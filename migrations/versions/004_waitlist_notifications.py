"""waitlist entries, notifications outbox, patient preferences

Revision ID: 004_waitlist_notifications
Revises: 003_clinical_scheduling
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB

revision = "004_waitlist_notifications"
down_revision = "003_clinical_scheduling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── patient_preferences ───────────────────────────────────────────────────
    op.create_table(
        "patient_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False, unique=True),
        sa.Column("preferred_channel", sa.String(10), nullable=False, server_default="email"),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("reminder_hours_before", ARRAY(sa.Integer), nullable=False,
                  server_default="{24,2}"),
        sa.Column("email_notifications", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sms_notifications", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("push_notifications", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_patient_preferences_user", "patient_preferences", ["user_id"])

    # ── waitlist_entries ──────────────────────────────────────────────────────
    op.create_table(
        "waitlist_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"),
                  nullable=False),
        sa.Column("appointment_type_id", UUID(as_uuid=True),
                  sa.ForeignKey("appointment_types.id"), nullable=True),
        sa.Column("doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="waiting"),
        # waiting | notified | expired | cancelled
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_waitlist_dept_status_created", "waitlist_entries",
                    ["department_id", "status", "created_at"])
    op.create_index("ix_waitlist_patient", "waitlist_entries", ["patient_id"])

    # ── notifications ─────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),      # email | sms | push
        sa.Column("type", sa.String(50), nullable=False),          # BOOKING_CONFIRMED | etc.
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("recipient", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # pending | sent | failed | skipped
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("context", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_notifications_pending_next", "notifications", ["status", "next_attempt_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_notifications_user", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user", "notifications")
    op.drop_index("ix_notifications_pending_next", "notifications")
    op.drop_table("notifications")
    op.drop_index("ix_waitlist_patient", "waitlist_entries")
    op.drop_index("ix_waitlist_dept_status_created", "waitlist_entries")
    op.drop_table("waitlist_entries")
    op.drop_index("ix_patient_preferences_user", "patient_preferences")
    op.drop_table("patient_preferences")
