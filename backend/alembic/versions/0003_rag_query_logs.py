"""Add RAG query logs.

Revision ID: 0003_rag_query_logs
Revises: 0002_business_artifacts
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_rag_query_logs"
down_revision = "0002_business_artifacts"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "rag_query_logs" in inspector.get_table_names():
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("rag_query_logs")}
        if "ix_rag_query_logs_conversation_key" not in existing_indexes:
            op.create_index("ix_rag_query_logs_conversation_key", "rag_query_logs", ["conversation_key"])
        return

    op.create_table(
        "rag_query_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("conversation_key", sa.String(40), nullable=False, server_default=""),
        sa.Column("query", sa.Text(), nullable=False, server_default=""),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("injected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("top_sources", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at_label", sa.String(40), nullable=False, server_default="刚刚"),
    )
    op.create_index("ix_rag_query_logs_conversation_key", "rag_query_logs", ["conversation_key"])


def downgrade() -> None:
    op.drop_index("ix_rag_query_logs_conversation_key", table_name="rag_query_logs")
    op.drop_table("rag_query_logs")
