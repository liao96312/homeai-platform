"""Add business artifacts.

Revision ID: 0002_business_artifacts
Revises: 0001_initial
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_business_artifacts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "business_artifacts" in inspector.get_table_names():
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("business_artifacts")}
        if "ix_business_artifacts_artifact_type" not in existing_indexes:
            op.create_index("ix_business_artifacts_artifact_type", "business_artifacts", ["artifact_type"])
        return

    op.create_table(
        "business_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("artifact_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("result_json", json_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at_label", sa.String(40), nullable=False, server_default="刚刚"),
    )
    op.create_index("ix_business_artifacts_artifact_type", "business_artifacts", ["artifact_type"])


def downgrade() -> None:
    op.drop_index("ix_business_artifacts_artifact_type", table_name="business_artifacts")
    op.drop_table("business_artifacts")
