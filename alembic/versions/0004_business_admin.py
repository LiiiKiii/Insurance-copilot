"""Add the A4 agent assessment schema.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from __future__ import annotations

import sqlalchemy as sa

import admin.models  # noqa: F401
from admin.db import Base
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TABLE_NAME = "agent_assessments"
_REQUIRED_COLUMNS = {
    "id",
    "tenant_id",
    "agent_id",
    "subject",
    "target_value",
    "current_value",
    "status",
    "remark",
    "created_at",
    "updated_at",
}
_UNIQUE_COLUMNS = ("tenant_id", "agent_id", "subject")


def _has_assessment_uniqueness(inspector: sa.Inspector) -> bool:
    for constraint in inspector.get_unique_constraints(_TABLE_NAME):
        if tuple(constraint.get("column_names") or ()) == _UNIQUE_COLUMNS:
            return True
    for index in inspector.get_indexes(_TABLE_NAME):
        if (
            index.get("unique")
            and tuple(index.get("column_names") or ()) == _UNIQUE_COLUMNS
        ):
            return True
    return False


def upgrade() -> None:
    """Create or validate the assessment table without replacing existing data."""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table = Base.metadata.tables[_TABLE_NAME]
    if not inspector.has_table(_TABLE_NAME):
        table.create(bind=bind)
        return

    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(_TABLE_NAME)}
    missing = sorted(_REQUIRED_COLUMNS - columns)
    if missing:
        raise RuntimeError(
            f"Incompatible {_TABLE_NAME} schema: missing {', '.join(missing)}"
        )
    if not _has_assessment_uniqueness(inspector):
        raise RuntimeError(
            f"Incompatible {_TABLE_NAME} schema: assessment uniqueness is missing"
        )


def downgrade() -> None:
    """Preserve assessment data when table provenance cannot be determined."""

    raise RuntimeError(
        "Downgrade of 0004 is blocked to preserve existing assessment records"
    )
