"""Add indexes for user filtered operational tables.

Revision ID: 0010_add_user_filter_indexes
Revises: 0009_promo_templates_schedule
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_add_user_filter_indexes"
down_revision = "0009_promo_templates_schedule"
branch_labels = None
depends_on = None


INDEXES = (
    ("business_artifacts", "ix_business_artifacts_owner_id", ["owner_id"]),
    ("publish_jobs", "ix_publish_jobs_user_id", ["user_id"]),
    ("rag_query_logs", "ix_rag_query_logs_user_id", ["user_id"]),
    ("promo_templates", "ix_promo_templates_owner_id", ["owner_id"]),
)


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_index(table: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return False
    return any(index["name"] == index_name for index in inspector.get_indexes(table))


def upgrade() -> None:
    for table, index_name, columns in INDEXES:
        if _has_table(table) and not _has_index(table, index_name):
            op.create_index(index_name, table, columns)


def downgrade() -> None:
    for table, index_name, _columns in reversed(INDEXES):
        if _has_table(table) and _has_index(table, index_name):
            op.drop_index(index_name, table_name=table)
