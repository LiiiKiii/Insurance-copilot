"""Add user-owned chat sessions and messages.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-21
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("chat_sessions"):
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.String(length=100), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("agent_id", sa.String(length=100), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_chat_sessions_tenant_id", "chat_sessions", ["tenant_id"])
        op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
        op.create_index("ix_chat_sessions_agent_id", "chat_sessions", ["agent_id"])
        op.create_index("ix_chat_sessions_updated_at", "chat_sessions", ["updated_at"])
        op.create_index(
            "idx_chat_session_owner_updated",
            "chat_sessions",
            ["tenant_id", "user_id", "updated_at"],
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("session_id", sa.String(length=100), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
        op.create_index(
            "idx_chat_message_session_created",
            "chat_messages",
            ["session_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
