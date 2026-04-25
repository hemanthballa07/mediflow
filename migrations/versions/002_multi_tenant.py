"""multi-tenant: facilities, departments, specialties, rooms

Revision ID: 002_multi_tenant
Revises: 001_initial
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002_multi_tenant"
down_revision = "001_initial"
branch_labels = None
depends_on = None

# Deterministic UUIDs for default backfill rows
DEFAULT_SPECIALTY_ID = "00000000-0000-0000-0000-000000000002"
DEFAULT_FACILITY_ID  = "00000000-0000-0000-0000-000000000001"
DEFAULT_DEPT_ID      = "00000000-0000-0000-0000-000000000003"


def upgrade() -> None:
    # ── specialties ───────────────────────────────────────────────────────────
    op.create_table(
        "specialties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── facilities ────────────────────────────────────────────────────────────
    op.create_table(
        "facilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("code", sa.String(20), unique=True, nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="America/New_York"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ── departments ───────────────────────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("specialty_id", UUID(as_uuid=True), sa.ForeignKey("specialties.id"), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_dept_facility_code", "departments", ["facility_id", "code"])
    op.create_index("ix_departments_facility", "departments", ["facility_id"])

    # ── rooms ─────────────────────────────────────────────────────────────────
    op.create_table(
        "rooms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("department_id", UUID(as_uuid=True), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),  # exam|procedure|imaging|ward
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_rooms_facility", "rooms", ["facility_id"])

    # ── seed default facility + specialty + department (backfill anchor) ──────
    op.execute(f"""
        INSERT INTO specialties (id, name, code)
        VALUES ('{DEFAULT_SPECIALTY_ID}', 'General Practice', 'GP')
    """)
    op.execute(f"""
        INSERT INTO facilities (id, name, code, address, timezone)
        VALUES (
            '{DEFAULT_FACILITY_ID}',
            'MediFlow General Hospital',
            'MGH',
            '1 Hospital Drive, New York, NY 10001',
            'America/New_York'
        )
    """)
    op.execute(f"""
        INSERT INTO departments (id, facility_id, specialty_id, name, code)
        VALUES (
            '{DEFAULT_DEPT_ID}',
            '{DEFAULT_FACILITY_ID}',
            '{DEFAULT_SPECIALTY_ID}',
            'General Medicine',
            'GM'
        )
    """)

    # ── add FK columns to doctors (nullable, then backfill) ───────────────────
    op.add_column("doctors", sa.Column("facility_id", UUID(as_uuid=True),
                  sa.ForeignKey("facilities.id"), nullable=True))
    op.add_column("doctors", sa.Column("department_id", UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True))
    op.add_column("doctors", sa.Column("specialty_id", UUID(as_uuid=True),
                  sa.ForeignKey("specialties.id"), nullable=True))

    op.execute(f"""
        UPDATE doctors
        SET facility_id   = '{DEFAULT_FACILITY_ID}',
            department_id = '{DEFAULT_DEPT_ID}',
            specialty_id  = '{DEFAULT_SPECIALTY_ID}'
    """)

    # ── add FK columns to slots ───────────────────────────────────────────────
    op.add_column("slots", sa.Column("facility_id", UUID(as_uuid=True),
                  sa.ForeignKey("facilities.id"), nullable=True))
    op.add_column("slots", sa.Column("department_id", UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True))
    op.create_index("ix_slots_facility_date", "slots", ["facility_id", "date", "start_time"])

    op.execute(f"""
        UPDATE slots s
        SET facility_id   = d.facility_id,
            department_id = d.department_id
        FROM doctors d
        WHERE s.doctor_id = d.id
    """)

    # ── add FK columns to lab_reports ─────────────────────────────────────────
    op.add_column("lab_reports", sa.Column("facility_id", UUID(as_uuid=True),
                  sa.ForeignKey("facilities.id"), nullable=True))
    op.add_column("lab_reports", sa.Column("department_id", UUID(as_uuid=True),
                  sa.ForeignKey("departments.id"), nullable=True))

    op.execute(f"""
        UPDATE lab_reports
        SET facility_id   = '{DEFAULT_FACILITY_ID}',
            department_id = '{DEFAULT_DEPT_ID}'
    """)

    # ── add home_facility_id to users ─────────────────────────────────────────
    op.add_column("users", sa.Column("home_facility_id", UUID(as_uuid=True),
                  sa.ForeignKey("facilities.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "home_facility_id")
    op.drop_column("lab_reports", "department_id")
    op.drop_column("lab_reports", "facility_id")
    op.drop_index("ix_slots_facility_date", "slots")
    op.drop_column("slots", "department_id")
    op.drop_column("slots", "facility_id")
    op.drop_column("doctors", "specialty_id")
    op.drop_column("doctors", "department_id")
    op.drop_column("doctors", "facility_id")
    op.drop_index("ix_rooms_facility", "rooms")
    op.drop_table("rooms")
    op.drop_index("ix_departments_facility", "departments")
    op.drop_constraint("uq_dept_facility_code", "departments")
    op.drop_table("departments")
    op.drop_table("facilities")
    op.drop_table("specialties")
