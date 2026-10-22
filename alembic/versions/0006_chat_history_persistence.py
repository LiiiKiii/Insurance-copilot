"""Add user-owned chat sessions and persisted messages.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("chat_sessions"):
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("agent_id", sa.String(length=100), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(), nullable=False),
            sa.Column("message_count", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_chat_sessions_user_id", "chat_sessions", ["user_id"], unique=False
        )
        op.create_index(
            "ix_chat_sessions_agent_id", "chat_sessions", ["agent_id"], unique=False
        )
        op.create_index(
            "ix_chat_sessions_updated_at",
            "chat_sessions",
            ["updated_at"],
            unique=False,
        )
        op.create_index(
            "ix_chat_sessions_last_message_at",
            "chat_sessions",
            ["last_message_at"],
            unique=False,
        )

    if not _has_table("chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("role", sa.String(length=20), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_chat_messages_session_id",
            "chat_messages",
            ["session_id"],
            unique=False,
        )
        op.create_index(
            "ix_chat_messages_created_at",
            "chat_messages",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("chat_messages"):
        op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
        op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
        op.drop_table("chat_messages")
    if _has_table("chat_sessions"):
        op.drop_index("ix_chat_sessions_last_message_at", table_name="chat_sessions")
        op.drop_index("ix_chat_sessions_updated_at", table_name="chat_sessions")
        op.drop_index("ix_chat_sessions_agent_id", table_name="chat_sessions")
        op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
        op.drop_table("chat_sessions")
