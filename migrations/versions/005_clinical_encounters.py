"""encounters, vitals, diagnoses, prescriptions, allergies, problem_list

Revision ID: 005_clinical_encounters
Revises: 004_waitlist_notifications
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "005_clinical_encounters"
down_revision = "004_waitlist_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── encounters ────────────────────────────────────────────────────────────
    op.create_table(
        "encounters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("booking_id", UUID(as_uuid=True), sa.ForeignKey("bookings.id"),
                  nullable=True),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("doctor_id", UUID(as_uuid=True), sa.ForeignKey("doctors.id"),
                  nullable=False),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"),
                  nullable=True),
        sa.Column("encounter_type", sa.String(30), nullable=False,
                  server_default="office_visit"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("chief_complaint", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("encounter_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_encounters_patient_date", "encounters",
                    ["patient_id", "encounter_date"])
    op.create_index("ix_encounters_doctor", "encounters", ["doctor_id"])

    # ── vitals ────────────────────────────────────────────────────────────────
    op.create_table(
        "vitals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("encounter_id", UUID(as_uuid=True), sa.ForeignKey("encounters.id"),
                  nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("bp_systolic", sa.Integer, nullable=True),
        sa.Column("bp_diastolic", sa.Integer, nullable=True),
        sa.Column("heart_rate", sa.Integer, nullable=True),
        sa.Column("temperature_f", sa.Numeric(5, 2), nullable=True),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=True),
        sa.Column("height_cm", sa.Numeric(5, 1), nullable=True),
        sa.Column("spo2", sa.Numeric(5, 2), nullable=True),
        sa.Column("respiratory_rate", sa.Integer, nullable=True),
        sa.Column("recorded_by", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_vitals_encounter", "vitals", ["encounter_id"])
    op.create_index("ix_vitals_patient", "vitals", ["patient_id"])

    # ── diagnoses ─────────────────────────────────────────────────────────────
    op.create_table(
        "diagnoses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("encounter_id", UUID(as_uuid=True), sa.ForeignKey("encounters.id"),
                  nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("icd10_code", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("diagnosis_type", sa.String(20), nullable=False,
                  server_default="primary"),
        sa.Column("onset_date", sa.Date, nullable=True),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_diagnoses_encounter", "diagnoses", ["encounter_id"])
    op.create_index("ix_diagnoses_patient", "diagnoses", ["patient_id"])

    # ── prescriptions ─────────────────────────────────────────────────────────
    op.create_table(
        "prescriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("encounter_id", UUID(as_uuid=True), sa.ForeignKey("encounters.id"),
                  nullable=False),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("drug_name", sa.Text, nullable=False),
        sa.Column("dose", sa.String(50), nullable=False),
        sa.Column("frequency", sa.String(50), nullable=False),
        sa.Column("route", sa.String(20), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("refills", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("prescriber_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_prescriptions_encounter", "prescriptions", ["encounter_id"])
    op.create_index("ix_prescriptions_patient", "prescriptions", ["patient_id"])

    # ── allergies ─────────────────────────────────────────────────────────────
    op.create_table(
        "allergies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("allergen", sa.Text, nullable=False),
        sa.Column("reaction", sa.Text, nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("onset_date", sa.Date, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("recorded_by", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_allergies_patient", "allergies", ["patient_id"])

    # ── problem_list ──────────────────────────────────────────────────────────
    op.create_table(
        "problem_list",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("icd10_code", sa.String(20), nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("onset_date", sa.Date, nullable=True),
        sa.Column("resolved_date", sa.Date, nullable=True),
        sa.Column("noted_by", UUID(as_uuid=True), sa.ForeignKey("users.id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_problem_list_patient", "problem_list", ["patient_id"])


def downgrade() -> None:
    op.drop_table("problem_list")
    op.drop_table("allergies")
    op.drop_table("prescriptions")
    op.drop_table("diagnoses")
    op.drop_table("vitals")
    op.drop_table("encounters")
