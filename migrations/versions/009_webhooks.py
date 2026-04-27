"""webhooks and webhook_deliveries tables

Revision ID: 009_webhooks
Revises: 008_compliance
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "009_webhooks"
down_revision = "008_compliance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret", sa.Text, nullable=False),
        sa.Column("events", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_webhooks_user", "webhooks", ["user_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("webhook_id", UUID(as_uuid=True), sa.ForeignKey("webhooks.id"), nullable=False),
        sa.Column("event", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_response_status", sa.Integer, nullable=True),
        sa.Column("signature", sa.Text, nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_deliveries_webhook", "webhook_deliveries", ["webhook_id"])
    op.create_index(
        "ix_webhook_deliveries_pending",
        "webhook_deliveries",
        ["status", "next_retry_at"],
        postgresql_where=sa.text("status IN ('pending', 'retrying')"),
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_pending", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_webhook", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhooks_user", table_name="webhooks")
    op.drop_table("webhooks")
