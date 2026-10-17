"""Shared safeguards for tenant-scoped business administration routes."""

from __future__ import annotations

from fastapi import status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from admin.dependencies import _error
from admin.models.tenant import Tenant
from admin.models.user import User


def resolve_tenant_id(current_user: User, requested_tenant_id: str | None) -> str:
    """Resolve a writable tenant without allowing cross-tenant access."""

    if not current_user.is_superadmin:
        if requested_tenant_id not in (None, current_user.tenant_id):
            raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")
        return current_user.tenant_id
    return requested_tenant_id or current_user.tenant_id


def ensure_tenant_access(current_user: User, tenant_id: str | None) -> None:
    """Reject records outside the current administrator's tenant."""

    if not current_user.is_superadmin and tenant_id != current_user.tenant_id:
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")


async def ensure_tenant_exists(db: AsyncSession, tenant_id: str) -> None:
    """Validate a tenant identifier before inserting dependent records."""

    if await db.get(Tenant, tenant_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant not found")


async def commit_or_error(
    db: AsyncSession,
    *,
    conflict_message: str,
) -> None:
    """Commit a business-data transaction with stable client-safe errors."""

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "CONFLICT", conflict_message) from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "Database service is unavailable",
        ) from exc
