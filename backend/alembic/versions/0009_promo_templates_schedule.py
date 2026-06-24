"""Add promo templates and publish scheduling.

Revision ID: 0009_promo_templates_schedule
Revises: 0008_local_embedding_model
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_promo_templates_schedule"
down_revision = "0008_local_embedding_model"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_table("promo_templates"):
        op.create_table(
            "promo_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("platform", sa.String(length=40), nullable=False, server_default="小红书"),
            sa.Column("scene", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
            sa.Column("default_audience", sa.String(length=160), nullable=False, server_default="准备装修的家庭客户"),
            sa.Column("default_tone", sa.String(length=160), nullable=False, server_default="专业、真实、有转化力"),
            sa.Column("default_selling_points", _json_type(), nullable=False, server_default="[]"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_promo_templates_platform", "promo_templates", ["platform"])
        op.create_index("ix_promo_templates_is_active", "promo_templates", ["is_active"])
        op.create_index("ix_promo_templates_created_at", "promo_templates", ["created_at"])

    if _has_table("publish_jobs") and not _has_column("publish_jobs", "scheduled_at"):
        op.add_column("publish_jobs", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_publish_jobs_scheduled_at", "publish_jobs", ["scheduled_at"])


def downgrade() -> None:
    if _has_table("publish_jobs") and _has_column("publish_jobs", "scheduled_at"):
        op.drop_index("ix_publish_jobs_scheduled_at", table_name="publish_jobs")
        op.drop_column("publish_jobs", "scheduled_at")
    if _has_table("promo_templates"):
        op.drop_table("promo_templates")
