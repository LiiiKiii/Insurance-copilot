"""Create the generic non-secret system configuration table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_NAME = "system_configs"
_GLOBAL_INDEX_NAME = "uq_system_configs_global_key"
_TENANT_UNIQUE_COLUMNS = ("tenant_id", "config_key")
_REQUIRED_COLUMNS = {
    "id": (sa.String, 36, False),
    "tenant_id": (sa.String, 36, True),
    "config_key": (sa.String, 200, False),
    "config_value": (sa.Text, None, False),
    "config_type": (sa.String, 20, False),
    "description": (sa.String, 500, False),
    "is_public": (sa.Boolean, None, False),
    "created_at": (sa.DateTime, None, False),
    "updated_at": (sa.DateTime, None, False),
}


def _create_system_configs_table() -> None:
    """Create the table for historical databases that predate this model."""

    op.create_table(
        _TABLE_NAME,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("config_key", sa.String(length=200), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=False),
        sa.Column("config_type", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(*_TENANT_UNIQUE_COLUMNS, name="uq_system_configs_tenant_key"),
    )


def _type_matches(actual: sa.types.TypeEngine, expected: type[sa.types.TypeEngine]) -> bool:
    if expected is sa.Text:
        return isinstance(actual, sa.Text)
    return isinstance(actual, expected) and not isinstance(actual, sa.Text)


def _normalized_expression(expression: object) -> str:
    normalized = " ".join(str(expression).casefold().replace('"', "").split())
    while normalized.startswith("(") and normalized.endswith(")"):
        depth = 0
        for position, character in enumerate(normalized):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            if depth == 0:
                break
        if depth != 0 or position != len(normalized) - 1:
            break
        normalized = normalized[1:-1].strip()
    return normalized


def _is_global_index(index: dict) -> bool:
    if not index.get("unique") or index.get("column_names") != ["config_key"]:
        return False
    dialect_options = index.get("dialect_options") or {}
    predicate = dialect_options.get("sqlite_where")
    if predicate is None:
        predicate = dialect_options.get("postgresql_where")
    return _normalized_expression(predicate) == "tenant_id is null"


def _has_tenant_uniqueness(inspector: sa.Inspector) -> bool:
    for constraint in inspector.get_unique_constraints(_TABLE_NAME):
        if tuple(constraint.get("column_names") or ()) == _TENANT_UNIQUE_COLUMNS:
            return True
    for index in inspector.get_indexes(_TABLE_NAME):
        if (
            index.get("unique")
            and tuple(index.get("column_names") or ()) == _TENANT_UNIQUE_COLUMNS
            and not (index.get("dialect_options") or {})
        ):
            return True
    return False


def _validate_existing_table(bind: sa.Connection) -> None:
    """Reject incompatible pre-existing tables without mutating their data."""

    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns(_TABLE_NAME)}
    problems: list[str] = []

    for name, (expected_type, expected_length, nullable) in _REQUIRED_COLUMNS.items():
        column = columns.get(name)
        if column is None:
            problems.append(f"missing column {name}")
            continue
        if not _type_matches(column["type"], expected_type):
            problems.append(f"column {name} has an incompatible type")
        elif expected_length is not None and getattr(column["type"], "length", None) != expected_length:
            problems.append(f"column {name} has an incompatible length")
        if column.get("nullable") is not nullable:
            problems.append(f"column {name} has incompatible nullability")

    primary_key = tuple(inspector.get_pk_constraint(_TABLE_NAME).get("constrained_columns") or ())
    if primary_key != ("id",):
        problems.append("primary key must be id")
    if not _has_tenant_uniqueness(inspector):
        problems.append("tenant-scoped uniqueness is missing")

    if problems:
        raise RuntimeError("Incompatible system_configs schema: " + "; ".join(problems))


def _ensure_global_index(bind: sa.Connection) -> None:
    """Create or validate the global partial unique index without table replacement."""

    inspector = sa.inspect(bind)
    matching = [
        index
        for index in inspector.get_indexes(_TABLE_NAME)
        if index.get("name") == _GLOBAL_INDEX_NAME
    ]
    if matching:
        if not _is_global_index(matching[0]):
            raise RuntimeError(
                "Incompatible system_configs schema: global uniqueness index is invalid."
            )
        return

    global_scope = sa.text("tenant_id IS NULL")
    op.create_index(
        _GLOBAL_INDEX_NAME,
        _TABLE_NAME,
        ["config_key"],
        unique=True,
        sqlite_where=global_scope,
        postgresql_where=global_scope,
    )


def upgrade() -> None:
    """Create tenant and global configuration uniqueness guarantees.

    Both SQLite and PostgreSQL support the partial unique index used for global
    rows.  The composite constraint covers tenant rows; SQL uniqueness alone
    cannot make two NULL tenant IDs conflict.
    """

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE_NAME):
        _create_system_configs_table()
    else:
        _validate_existing_table(bind)
    _ensure_global_index(bind)


def downgrade() -> None:
    """Refuse destructive downgrade when table provenance cannot be known safely.

    Revision 0001 dynamically creates all currently registered ORM metadata.
    A ``system_configs`` table observed during downgrade could therefore be
    historical, pre-created, dynamically created by 0001, or created by 0002.
    Alembic records only revision state, not per-table provenance.  Preserving
    the table is safer than silently deleting potentially pre-existing data.
    """

    raise RuntimeError(
        "Downgrade of 0002 is blocked: system_configs provenance is ambiguous; "
        "no table or data was removed."
    )
