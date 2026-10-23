"""Repair chat_sessions missing tenant_id column.

Why this migration exists
------------------------
Migration 0005 creates ``chat_sessions`` only when the table does not exist
(``if not inspector.has_table("chat_sessions")``). Databases whose
``chat_sessions`` table was created earlier (e.g. by ``Base.metadata.create_all``
from a pre-multi-tenancy model) therefore never received the ``tenant_id``
column, while the ORM model maps it as NOT NULL with a foreign key to
``tenants.id``. As a result every ORM read/write on ``ChatSession`` fails with::

    column chat_sessions.tenant_id does not exist

``Base.metadata.create_all`` only creates missing tables; it never adds columns
to existing ones, so the drift was silent until runtime.

This migration adds the column when missing, backfills it from the owning
user's tenant, drops orphan sessions that cannot be attributed to any tenant,
then applies the NOT NULL constraint, the foreign key and the indexes required
by the model.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    columns = _column_names("chat_sessions")
    if "tenant_id" in columns:
        return  # nothing to repair

    op.add_column(
        "chat_sessions",
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
    )

    # Backfill from the owning user. Sessions whose user no longer exists
    # cannot be attributed to any tenant and are unusable anyway, so they are
    # removed before the NOT NULL constraint is applied.
    op.execute(
        "UPDATE chat_sessions "
        "SET tenant_id = (SELECT users.tenant_id FROM users "
        "WHERE users.id = chat_sessions.user_id)"
    )
    op.execute("DELETE FROM chat_sessions WHERE tenant_id IS NULL")

    with op.batch_alter_table("chat_sessions") as batch:
        batch.alter_column("tenant_id", nullable=False)
        batch.create_foreign_key(
            "fk_chat_sessions_tenant_id",
            "tenants",
            ["tenant_id"],
            ["id"],
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_sessions_tenant_id "
        "ON chat_sessions (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_session_owner_updated "
        "ON chat_sessions (tenant_id, user_id, updated_at)"
    )


def downgrade() -> None:
    columns = _column_names("chat_sessions")
    if "tenant_id" not in columns:
        return
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_constraint("fk_chat_sessions_tenant_id", type_="foreignkey")
        batch.drop_column("tenant_id")
