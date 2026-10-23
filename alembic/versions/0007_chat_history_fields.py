"""Add chat history ordering and count fields.

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _chat_session_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("chat_sessions"):
        return set()
    return {column["name"] for column in inspector.get_columns("chat_sessions")}


def upgrade() -> None:
    columns = _chat_session_columns()
    if not columns:
        return

    with op.batch_alter_table("chat_sessions") as batch:
        if "last_message_at" not in columns:
            batch.add_column(sa.Column("last_message_at", sa.DateTime(), nullable=True))
        if "message_count" not in columns:
            batch.add_column(
                sa.Column(
                    "message_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )

    if "last_message_at" not in columns:
        op.execute(
            "UPDATE chat_sessions "
            "SET last_message_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        with op.batch_alter_table("chat_sessions") as batch:
            batch.alter_column("last_message_at", nullable=False)
            batch.create_index(
                "ix_chat_sessions_last_message_at",
                ["last_message_at"],
                unique=False,
            )


def downgrade() -> None:
    columns = _chat_session_columns()
    with op.batch_alter_table("chat_sessions") as batch:
        if "last_message_at" in columns:
            batch.drop_index("ix_chat_sessions_last_message_at")
            batch.drop_column("last_message_at")
        if "message_count" in columns:
            batch.drop_column("message_count")
