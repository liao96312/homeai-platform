"""Add agent status check constraint.

Revision ID: 0012_agent_status_check
Revises: 0011_conversation_messages
Create Date: 2026-06-18 00:00:00.000000
"""

from alembic import op


revision = "0012_agent_status_check"
down_revision = "0011_conversation_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.create_check_constraint(
        "ck_agents_status",
        "agents",
        "status IN ('online', 'paused', 'maintenance')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.drop_constraint("ck_agents_status", "agents", type_="check")
