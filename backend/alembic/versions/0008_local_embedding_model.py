"""Use local fastembed model metadata.

Revision ID: 0008_local_embedding_model
Revises: 0007_agent_runtime_tables
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_local_embedding_model"
down_revision = "0007_agent_runtime_tables"
branch_labels = None
depends_on = None

LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("knowledge_chunks"):
        return
    with op.batch_alter_table("knowledge_chunks") as batch_op:
        batch_op.alter_column(
            "embedding_model",
            existing_type=sa.String(length=80),
            type_=sa.String(length=120),
            existing_nullable=False,
            server_default=LOCAL_MODEL,
        )


def downgrade() -> None:
    if not _has_table("knowledge_chunks"):
        return
    with op.batch_alter_table("knowledge_chunks") as batch_op:
        batch_op.alter_column(
            "embedding_model",
            existing_type=sa.String(length=120),
            type_=sa.String(length=80),
            existing_nullable=False,
            server_default="local-hash-embedding-v1",
        )
