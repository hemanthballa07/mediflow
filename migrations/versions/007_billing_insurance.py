"""billing and insurance tables

Revision ID: 007_billing_insurance
Revises: 006_referrals_orders
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision = "007_billing_insurance"
down_revision = "006_referrals_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── insurance_plans ───────────────────────────────────────────────────────
    op.create_table(
        "insurance_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("payer_id", sa.String(50), nullable=False),
        sa.Column("plan_type", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ── patient_insurance ─────────────────────────────────────────────────────
    op.create_table(
        "patient_insurance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("insurance_plan_id", UUID(as_uuid=True),
                  sa.ForeignKey("insurance_plans.id"), nullable=False),
        sa.Column("member_id", sa.String(100), nullable=False),
        sa.Column("group_number", sa.String(50), nullable=True),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("termination_date", sa.Date, nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_patient_insurance_patient", "patient_insurance", ["patient_id"])
    op.create_index(
        "uq_patient_primary_insurance",
        "patient_insurance",
        ["patient_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )

    # ── charge_masters ────────────────────────────────────────────────────────
    op.create_table(
        "charge_masters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("cpt_code", sa.String(10), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("base_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("department_id", UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_charge_masters_cpt", "charge_masters", ["cpt_code"])

    # ── claims ────────────────────────────────────────────────────────────────
    op.create_table(
        "claims",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("encounter_id", UUID(as_uuid=True),
                  sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_insurance_id", UUID(as_uuid=True),
                  sa.ForeignKey("patient_insurance.id"), nullable=False),
        sa.Column("ordering_doctor_id", UUID(as_uuid=True),
                  sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'draft'")),
        sa.Column("total_charged", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_paid", sa.Numeric(10, 2), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("adjudicated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_claims_patient_status", "claims", ["patient_id", "status"])
    op.create_index("ix_claims_encounter", "claims", ["encounter_id"])

    # ── claim_line_items ──────────────────────────────────────────────────────
    op.create_table(
        "claim_line_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("claim_id", UUID(as_uuid=True),
                  sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True),
                  sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("cpt_code", sa.String(10), nullable=False),
        sa.Column("icd10_codes", ARRAY(sa.String), nullable=False,
                  server_default=sa.text("'{}'")),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("units", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_claim_line_items_claim", "claim_line_items", ["claim_id"])

    # ── payments ──────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("claim_id", UUID(as_uuid=True),
                  sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("payer", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("payment_method", sa.String(10), nullable=False),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_payments_claim", "payments", ["claim_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_index("ix_claim_line_items_claim", table_name="claim_line_items")
    op.drop_table("claim_line_items")
    op.drop_index("ix_claims_encounter", table_name="claims")
    op.drop_index("ix_claims_patient_status", table_name="claims")
    op.drop_table("claims")
    op.drop_index("ix_charge_masters_cpt", table_name="charge_masters")
    op.drop_table("charge_masters")
    op.drop_index("uq_patient_primary_insurance", table_name="patient_insurance")
    op.drop_index("ix_patient_insurance_patient", table_name="patient_insurance")
    op.drop_table("patient_insurance")
    op.drop_table("insurance_plans")
