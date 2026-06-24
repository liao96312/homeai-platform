"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("color", sa.String(20), nullable=False),
        sa.Column("user_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_roles_key", "roles", ["key"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("icon", sa.String(12), nullable=False),
        sa.Column("theme", sa.String(40), nullable=False),
        sa.Column("docs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_rate", sa.String(20), nullable=False, server_default="0%"),
        sa.Column("updated_at_label", sa.String(40), nullable=False, server_default=""),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_knowledge_bases_key", "knowledge_bases", ["key"])

    op.create_table(
        "knowledge_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kb_id", sa.Integer(), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("can_view", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_edit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_manage", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("kb_id", "role_id", name="uq_knowledge_permissions_kb_role"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kb_id", sa.Integer(), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("status", sa.String(40), nullable=False, server_default="indexed"),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploader_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata_json", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_knowledge_documents_kb_id", "knowledge_documents", ["kb_id"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kb_id", sa.Integer(), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(120), nullable=False, server_default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        sa.Column("embedding", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata_json", json_type, nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index("ix_knowledge_chunks_kb_id", "knowledge_chunks", ["kb_id"])
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])

    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("icon", sa.String(12), nullable=False),
        sa.Column("theme", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("calls_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.String(20), nullable=False, server_default="0%"),
        sa.Column("avg_latency", sa.String(20), nullable=False, server_default="0s"),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "dashboard_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("value", sa.String(40), nullable=False),
        sa.Column("trend", sa.String(40), nullable=False),
        sa.Column("icon", sa.String(12), nullable=False),
        sa.Column("theme", sa.String(40), nullable=False),
    )

    op.create_table(
        "operation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("icon", sa.String(12), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("time_label", sa.String(40), nullable=False),
        sa.Column("theme", sa.String(40), nullable=False),
    )

    op.create_table(
        "system_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(240), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_system_configs_key", "system_configs", ["key"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("assistant_name", sa.String(120), nullable=False),
        sa.Column("icon", sa.String(12), nullable=False),
        sa.Column("theme", sa.String(40), nullable=False),
        sa.Column("preview", sa.String(240), nullable=False),
        sa.Column("time_label", sa.String(40), nullable=False),
        sa.Column("unread", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quick_actions", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("messages", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.UniqueConstraint("key"),
    )

    op.create_table(
        "marketing_platforms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("icon", sa.String(12), nullable=False),
        sa.Column("theme", sa.String(40), nullable=False),
    )

    op.create_table(
        "wecom_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(40), nullable=False, server_default="callback"),
        sa.Column("msg_type", sa.String(40), nullable=False, server_default=""),
        sa.Column("from_user", sa.String(120), nullable=False, server_default=""),
        sa.Column("conversation_key", sa.String(40), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(40), nullable=False, server_default="received"),
        sa.Column("raw_payload", json_type, nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_table("wecom_webhook_events")
    op.drop_table("marketing_platforms")
    op.drop_table("conversations")
    op.drop_index("ix_system_configs_key", table_name="system_configs")
    op.drop_table("system_configs")
    op.drop_table("operation_logs")
    op.drop_table("dashboard_metrics")
    op.drop_table("agents")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_kb_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_kb_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_permissions")
    op.drop_index("ix_knowledge_bases_key", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_roles_key", table_name="roles")
    op.drop_table("roles")
