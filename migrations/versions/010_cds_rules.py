"""010 cds rules

Revision ID: 010_cds_rules
Revises: 009_webhooks
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010_cds_rules"
down_revision = "009_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cds_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=True),
        sa.Column("rule_type", sa.String(30), nullable=False),
        sa.Column("rule_key", sa.Text, nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cds_rules_rule_type_key", "cds_rules", ["rule_type", "rule_key"])
    op.create_index("ix_cds_rules_active", "cds_rules", ["active"])

    # Seed common rules
    op.execute(sa.text("""
        INSERT INTO cds_rules (id, facility_id, rule_type, rule_key, severity, message, active, created_at)
        VALUES
        ('a1000000-0000-0000-0000-000000000001', NULL, 'drug_allergy', 'penicillin', 'critical', 'Penicillin allergy documented - prescribing blocked', true, NOW()),
        ('a1000000-0000-0000-0000-000000000002', NULL, 'drug_allergy', 'sulfa', 'warning', 'Sulfonamide allergy documented - verify cross-reactivity', true, NOW()),
        ('a1000000-0000-0000-0000-000000000003', NULL, 'drug_drug', 'aspirin|warfarin', 'warning', 'Aspirin + Warfarin: increased bleeding risk - monitor INR closely', true, NOW()),
        ('a1000000-0000-0000-0000-000000000004', NULL, 'drug_drug', 'metformin|contrast', 'warning', 'Metformin + iodinated contrast: risk of lactic acidosis - hold metformin 48h', true, NOW()),
        ('a1000000-0000-0000-0000-000000000005', NULL, 'sepsis_score', 'qsofa', 'critical', 'qSOFA score >= 2: possible sepsis - consider immediate evaluation', true, NOW()),
        ('a1000000-0000-0000-0000-000000000006', NULL, 'vital_alert', 'RR_HIGH', 'warning', 'Elevated respiratory rate (>=22) - qSOFA component positive', true, NOW())
    """))


def downgrade() -> None:
    op.drop_index("ix_cds_rules_active", "cds_rules")
    op.drop_index("ix_cds_rules_rule_type_key", "cds_rules")
    op.drop_table("cds_rules")
