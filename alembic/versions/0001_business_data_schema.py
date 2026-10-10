"""Create the staged business-data schema.

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from admin.db import Base
import admin.models  # noqa: F401


revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create every model available through the A3 milestone."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
            "doc_id, title, content, tokenize='unicode61'"
            ")"
        )


def downgrade() -> None:
    """Drop the A3 schema."""
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TABLE IF EXISTS knowledge_fts")
    Base.metadata.drop_all(bind=bind)
