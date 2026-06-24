"""Add real timestamps to event logs.

Revision ID: 0005_log_created_at
Revises: 0004_publish_jobs
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_log_created_at"
down_revision = "0004_publish_jobs"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "rag_query_logs" in tables and not _has_column(inspector, "rag_query_logs", "created_at"):
        op.add_column(
            "rag_query_logs",
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )
        op.execute(sa.text("UPDATE rag_query_logs SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
        op.create_index("ix_rag_query_logs_created_at", "rag_query_logs", ["created_at"])

    if "wecom_webhook_events" in tables and not _has_column(inspector, "wecom_webhook_events", "created_at"):
        op.add_column(
            "wecom_webhook_events",
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )
        op.execute(sa.text("UPDATE wecom_webhook_events SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
        op.create_index("ix_wecom_webhook_events_created_at", "wecom_webhook_events", ["created_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "wecom_webhook_events" in tables and _has_column(inspector, "wecom_webhook_events", "created_at"):
        op.drop_index("ix_wecom_webhook_events_created_at", table_name="wecom_webhook_events")
        op.drop_column("wecom_webhook_events", "created_at")
    if "rag_query_logs" in tables and _has_column(inspector, "rag_query_logs", "created_at"):
        op.drop_index("ix_rag_query_logs_created_at", table_name="rag_query_logs")
        op.drop_column("rag_query_logs", "created_at")
