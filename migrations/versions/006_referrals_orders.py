"""referrals, orders, lab_reports.order_id

Revision ID: 006_referrals_orders
Revises: 005_clinical_encounters
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "006_referrals_orders"
down_revision = "005_clinical_encounters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── referrals ─────────────────────────────────────────────────────────────
    op.create_table(
        "referrals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("referring_doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id"),
                  nullable=False),
        sa.Column("receiving_department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"),
                  nullable=False),
        sa.Column("encounter_id", UUID(as_uuid=True), sa.ForeignKey("encounters.id"),
                  nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("urgency", sa.String(10), nullable=False, server_default="routine"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("referred_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_referrals_patient", "referrals", ["patient_id"])
    op.create_index("ix_referrals_referring_doctor", "referrals", ["referring_doctor_id"])
    op.create_index("ix_referrals_receiving_dept_status", "referrals",
                    ["receiving_department_id", "status"])

    # ── orders ────────────────────────────────────────────────────────────────
    op.create_table(
        "orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("encounter_id", UUID(as_uuid=True), sa.ForeignKey("encounters.id"),
                  nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("ordering_doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id"),
                  nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("cpt_code", sa.String(10), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="routine"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("resulted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_orders_encounter", "orders", ["encounter_id"])
    op.create_index("ix_orders_patient", "orders", ["patient_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # ── link lab_reports → orders ─────────────────────────────────────────────
    op.add_column(
        "lab_reports",
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True),
    )
    op.create_index("ix_lab_reports_order", "lab_reports", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_lab_reports_order", table_name="lab_reports")
    op.drop_column("lab_reports", "order_id")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_patient", table_name="orders")
    op.drop_index("ix_orders_encounter", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_referrals_receiving_dept_status", table_name="referrals")
    op.drop_index("ix_referrals_referring_doctor", table_name="referrals")
    op.drop_index("ix_referrals_patient", table_name="referrals")
    op.drop_table("referrals")
