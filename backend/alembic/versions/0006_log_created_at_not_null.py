"""Enforce non-null timestamps on log tables.

Revision ID: 0006_log_created_at_not_null
Revises: 0005_log_created_at
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_log_created_at_not_null"
down_revision = "0005_log_created_at"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def _enforce_created_at(table: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names() or not _has_column(inspector, table, "created_at"):
        return
    op.execute(sa.text(f"UPDATE {table} SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )


def upgrade() -> None:
    _enforce_created_at("rag_query_logs")
    _enforce_created_at("wecom_webhook_events")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("wecom_webhook_events", "rag_query_logs"):
        if table in inspector.get_table_names() and _has_column(inspector, table, "created_at"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(
                    "created_at",
                    existing_type=sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=None,
                )
