"""Create Original-compatible audit tables and indexes.

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from admin.db import Base
import admin.models  # noqa: F401


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TABLES = ("request_logs", "ai_audit_logs", "error_logs", "token_usage_logs", "flow_logs")
_INDEXES = {
    "request_logs": ("user_id",),
    "ai_audit_logs": ("user_id",),
    "token_usage_logs": ("user_id",),
    "flow_logs": ("session_id", "agent_id"),
}
_USER_ID_TABLES = frozenset({"request_logs", "ai_audit_logs", "token_usage_logs"})


def upgrade() -> None:
    bind = op.get_bind()
    for name in _TABLES:
        table = Base.metadata.tables[name]
        if not sa.inspect(bind).has_table(name):
            table.create(bind=bind)
        columns = {column["name"] for column in sa.inspect(bind).get_columns(name)}
        if name in _USER_ID_TABLES and "user_id" not in columns:
            op.add_column(name, sa.Column("user_id", sa.String(length=36), nullable=True))
            columns.add("user_id")
        required = {column.name for column in table.columns}
        if not required <= columns:
            raise RuntimeError(f"Incompatible {name} schema: missing {', '.join(sorted(required - columns))}")
        existing = {index["name"]: index for index in sa.inspect(bind).get_indexes(name)}
        for column in _INDEXES.get(name, ()):
            index_name = f"ix_{name}_{column}"
            if index_name in existing:
                if existing[index_name]["column_names"] != [column] or existing[index_name]["unique"]:
                    raise RuntimeError(f"Incompatible {name} schema: invalid index {index_name}")
            else:
                op.create_index(index_name, name, [column])


def downgrade() -> None:
    raise RuntimeError("Audit log downgrade is blocked to preserve potentially existing records")
