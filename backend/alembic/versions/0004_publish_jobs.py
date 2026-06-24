"""Add publish jobs.

Revision ID: 0004_publish_jobs
Revises: 0003_rag_query_logs
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_publish_jobs"
down_revision = "0003_rag_query_logs"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "publish_jobs" in inspector.get_table_names():
        return

    op.create_table(
        "publish_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_id", sa.Integer(), sa.ForeignKey("business_artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False, server_default="multipost"),
        sa.Column("platform_label", sa.String(80), nullable=False, server_default=""),
        sa.Column("platform_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("external_task_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("title", sa.String(160), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("response_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at_label", sa.String(40), nullable=False, server_default="刚刚"),
        sa.Column("updated_at_label", sa.String(40), nullable=False, server_default="刚刚"),
    )
    op.create_index("ix_publish_jobs_artifact_id", "publish_jobs", ["artifact_id"])
    op.create_index("ix_publish_jobs_status", "publish_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_publish_jobs_status", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_artifact_id", table_name="publish_jobs")
    op.drop_table("publish_jobs")
