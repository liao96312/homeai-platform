"""Add agent runtime tables.

Revision ID: 0007_agent_runtime_tables
Revises: 0006_log_created_at_not_null
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_agent_runtime_tables"
down_revision = "0006_log_created_at_not_null"
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("agent_runs"):
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_key", sa.String(length=64), nullable=False),
            sa.Column("channel", sa.String(length=40), nullable=False, server_default="web"),
            sa.Column("conversation_id", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("sender_id", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="running"),
            sa.Column("intent", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("route", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("tool_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("input_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("output_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("state_json", _json_type(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_agent_runs_run_key", "agent_runs", ["run_key"], unique=True)
        op.create_index("ix_agent_runs_channel", "agent_runs", ["channel"])
        op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])
        op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
        op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
        op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])
        op.create_index("ix_agent_runs_updated_at", "agent_runs", ["updated_at"])

    if not _has_table("agent_steps"):
        op.create_table(
            "agent_steps",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="completed"),
            sa.Column("detail_json", _json_type(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])
        op.create_index("ix_agent_steps_created_at", "agent_steps", ["created_at"])

    if not _has_table("agent_tool_calls"):
        op.create_table(
            "agent_tool_calls",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="completed"),
            sa.Column("input_json", _json_type(), nullable=False, server_default="{}"),
            sa.Column("output_json", _json_type(), nullable=False, server_default="{}"),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_agent_tool_calls_run_id", "agent_tool_calls", ["run_id"])
        op.create_index("ix_agent_tool_calls_tool_name", "agent_tool_calls", ["tool_name"])
        op.create_index("ix_agent_tool_calls_status", "agent_tool_calls", ["status"])
        op.create_index("ix_agent_tool_calls_created_at", "agent_tool_calls", ["created_at"])

    if not _has_table("agent_handoffs"):
        op.create_table(
            "agent_handoffs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("decision_json", _json_type(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_agent_handoffs_run_id", "agent_handoffs", ["run_id"])
        op.create_index("ix_agent_handoffs_status", "agent_handoffs", ["status"])
        op.create_index("ix_agent_handoffs_created_at", "agent_handoffs", ["created_at"])
        op.create_index("ix_agent_handoffs_updated_at", "agent_handoffs", ["updated_at"])


def downgrade() -> None:
    for table in ("agent_handoffs", "agent_tool_calls", "agent_steps", "agent_runs"):
        if _has_table(table):
            op.drop_table(table)
