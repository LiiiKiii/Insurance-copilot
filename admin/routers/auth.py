"""Administrative authentication endpoints for the A4 admin console."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from jose import JWTError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from admin.dependencies import (
    CurrentUser,
    DB,
    _error,
    _load_current_user,
    has_admin_access,
    is_admin_role,
)
from admin.models.tenant import Tenant
from admin.models.user import User
from admin.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from admin.utils import now_beijing

try:
    from admin.services.auth_service import (
        AuthenticationConfigurationError as _AuthenticationConfigurationError,
        TokenValidationError as _TokenValidationError,
    )
except ImportError:
    # The staged A4 service exposes the underlying exception types. These
    # aliases also support the hardened integration-branch implementation.
    _AuthenticationConfigurationError = RuntimeError
    _TokenValidationError = JWTError


# The parent registry supplies /api/admin/auth. Keeping this router unprefixed
# prevents duplicate paths when it is included by the stage-scoped registry.
router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


def _user_schema(user: User) -> dict[str, Any]:
    """Return the stable user contract consumed by the A4 frontend."""
    roles = sorted(
        {
            role.name
            for role in user.roles
            if role.tenant_id == user.tenant_id
        }
    )
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "tenant_id": user.tenant_id,
        "is_superadmin": bool(user.is_superadmin),
        "is_admin": is_admin_role(user),
        "tier": user.tier or "agent",
        "roles": roles,
    }


async def _login_user(username: str, db: DB) -> User:
    """Resolve exactly one username without selecting among duplicates."""
    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.username == username)
        )
        users = result.scalars().unique().all()
    except SQLAlchemyError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc

    if len(users) != 1:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "Invalid username or password.",
        )
    return users[0]


async def _validate_login_account(user: User, db: DB) -> None:
    """Check live account, tenant, and administrative-access state."""
    try:
        tenant = await db.get(Tenant, user.tenant_id)
    except SQLAlchemyError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc

    if not user.is_active:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "ACCOUNT_DISABLED",
            "Account access is disabled.",
        )
    if tenant is None or not tenant.enabled:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "TENANT_DISABLED",
            "Tenant access is disabled.",
        )
    if not has_admin_access(user):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "NO_ADMIN_ACCESS",
            "Administrative access is required.",
        )


def _create_login_tokens(user: User) -> tuple[str, str]:
    """Create an access/refresh pair without embedding mutable role claims."""
    try:
        payload = {"sub": user.id}
        return create_access_token(payload), create_refresh_token(payload)
    except _AuthenticationConfigurationError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc


def _create_refreshed_access_token(user: User) -> str:
    try:
        return create_access_token({"sub": user.id})
    except _AuthenticationConfigurationError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc


async def _commit_login(user: User, db: DB) -> None:
    user.last_login_at = now_beijing()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        try:
            await db.rollback()
        except Exception:
            # Preserve the client-safe commit error when rollback is impossible.
            pass
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc


@router.post("/login")
async def login(body: LoginRequest, db: DB) -> dict[str, Any]:
    user = await _login_user(body.username, db)
    try:
        password_matches = await run_in_threadpool(
            verify_password,
            body.password,
            user.password_hash,
        )
    except (TypeError, ValueError):
        password_matches = False
    if not password_matches:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "Invalid username or password.",
        )

    await _validate_login_account(user, db)
    access_token, refresh_token = _create_login_tokens(user)
    await _commit_login(user, db)
    return {
        "ok": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": _user_schema(user),
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest, db: DB) -> dict[str, Any]:
    try:
        claims = decode_token(body.refresh_token)
    except _AuthenticationConfigurationError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc
    except (_TokenValidationError, JWTError, ValueError) as exc:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Authentication credentials are invalid.",
        ) from exc

    user_id = claims.get("sub")
    if claims.get("type") != "refresh" or not isinstance(user_id, str) or not user_id:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Authentication credentials are invalid.",
        )

    user = await _load_current_user(user_id, db)
    if not has_admin_access(user):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "NO_ADMIN_ACCESS",
            "Administrative access is required.",
        )

    return {
        "ok": True,
        "data": {
            "access_token": _create_refreshed_access_token(user),
            "token_type": "bearer",
        },
    }


@router.post("/logout")
async def logout(_: CurrentUser) -> dict[str, Any]:
    """Acknowledge logout; stateless tokens remain valid until expiry."""
    return {"ok": True, "data": {"message": "Logged out"}}


@router.get("/me")
async def me(current_user: CurrentUser) -> dict[str, Any]:
    return {"ok": True, "data": _user_schema(current_user)}
