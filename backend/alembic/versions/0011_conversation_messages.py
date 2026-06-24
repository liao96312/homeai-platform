"""Add normalized conversation messages.

Revision ID: 0011_conversation_messages
Revises: 0010_add_user_filter_indexes
Create Date: 2026-06-17
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0011_conversation_messages"
down_revision = "0010_add_user_filter_indexes"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector, "conversation_messages"):
        op.create_table(
            "conversation_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sender", sa.String(length=20), nullable=False, server_default="ai"),
            sa.Column("message_type", sa.String(length=20), nullable=False, server_default="text"),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("extra_json", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_conversation_messages_conversation_id", "conversation_messages", ["conversation_id"])
        op.create_index("ix_conversation_messages_sender", "conversation_messages", ["sender"])
        op.create_index("ix_conversation_messages_created_at", "conversation_messages", ["created_at"])

    conversations = sa.table(
        "conversations",
        sa.column("id", sa.Integer()),
        sa.column("messages", sa.JSON()),
    )
    conversation_messages = sa.table(
        "conversation_messages",
        sa.column("conversation_id", sa.Integer()),
        sa.column("sender", sa.String()),
        sa.column("message_type", sa.String()),
        sa.column("content", sa.Text()),
        sa.column("extra_json", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    existing_count = bind.execute(sa.text("select count(*) from conversation_messages")).scalar() or 0
    if existing_count:
        return

    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    for conversation_id, messages in bind.execute(sa.select(conversations.c.id, conversations.c.messages)):
        if isinstance(messages, str):
            try:
                messages = json.loads(messages)
            except json.JSONDecodeError:
                messages = []
        if not isinstance(messages, list):
            continue
        for item in messages:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "conversation_id": conversation_id,
                    "sender": str(item.get("sender") or "ai")[:20],
                    "message_type": str(item.get("type") or item.get("message_type") or "text")[:20],
                    "content": str(item.get("content") or ""),
                    "extra_json": {k: v for k, v in item.items() if k not in {"sender", "type", "message_type", "content"}},
                    "created_at": now,
                }
            )
    if rows:
        bind.execute(sa.insert(conversation_messages), rows)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "conversation_messages"):
        op.drop_index("ix_conversation_messages_created_at", table_name="conversation_messages")
        op.drop_index("ix_conversation_messages_sender", table_name="conversation_messages")
        op.drop_index("ix_conversation_messages_conversation_id", table_name="conversation_messages")
        op.drop_table("conversation_messages")
