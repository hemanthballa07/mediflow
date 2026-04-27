"""compliance and audit hardening

Revision ID: 008_compliance
Revises: 007_billing_insurance
Create Date: 2026-04-26
"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "008_compliance"
down_revision = "007_billing_insurance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users: add email_hash column, drop unique on email ────────────────────
    op.add_column("users", sa.Column("email_hash", sa.Text, nullable=True))
    op.drop_index("ix_users_email", table_name="users", if_exists=True)
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index("uq_users_email_hash", "users", ["email_hash"],
                    unique=True, postgresql_where=sa.text("email_hash IS NOT NULL"))

    # ── password_history ─────────────────────────────────────────────────────
    op.create_table(
        "password_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_password_history_user_created", "password_history",
                    ["user_id", "created_at"])

    # Backfill current hashed_passwords into password_history
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO password_history (id, user_id, hashed_password, created_at) "
        "SELECT gen_random_uuid(), id, hashed_password, now() FROM users"
    ))

    # ── deletion_requests ────────────────────────────────────────────────────
    op.create_table(
        "deletion_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("reviewed_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_deletion_requests_patient_status", "deletion_requests",
                    ["patient_id", "status"])

    # ── PII migration: encrypt existing email + name, populate email_hash ─────
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if encryption_key and len(encryption_key) >= 32:
        try:
            from cryptography.fernet import Fernet
            import hashlib
            import hmac as hmac_mod

            fernet = Fernet(encryption_key.encode())
            rows = conn.execute(sa.text("SELECT id, email, name FROM users")).fetchall()
            for row in rows:
                uid, email, name = row
                enc_email = fernet.encrypt(email.encode()).decode()
                enc_name = fernet.encrypt(name.encode()).decode()
                ehash = hmac_mod.new(
                    encryption_key.encode(), email.lower().encode(), hashlib.sha256
                ).hexdigest()
                conn.execute(
                    sa.text(
                        "UPDATE users SET email = :enc_email, name = :enc_name, "
                        "email_hash = :ehash WHERE id = :uid"
                    ),
                    {"enc_email": enc_email, "enc_name": enc_name,
                     "ehash": ehash, "uid": uid},
                )
        except Exception:
            pass


def downgrade() -> None:
    op.drop_table("deletion_requests")
    op.drop_table("password_history")
    op.drop_index("uq_users_email_hash", table_name="users")
    op.drop_column("users", "email_hash")
    op.create_unique_constraint("users_email_key", "users", ["email"])
