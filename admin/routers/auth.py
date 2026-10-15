"""Administrative authentication endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, status
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
)
from admin.models.tenant import Tenant
from admin.models.user import User
from admin.services.auth_service import (
    AuthenticationConfigurationError,
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)


router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


def _user_payload(user: User) -> dict[str, Any]:
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
        "is_admin": has_admin_access(user),
        "tier": user.tier,
        "roles": roles,
    }


async def _login_user(username: str, db: DB) -> User:
    """Resolve one username without selecting arbitrarily among duplicates."""

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


def _create_tokens(user: User) -> tuple[str, str]:
    try:
        payload = {"sub": user.id}
        return create_access_token(payload), create_refresh_token(payload)
    except AuthenticationConfigurationError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc


async def _commit_login(user: User, db: DB) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        try:
            await db.rollback()
        except Exception:
            # The commit failure remains the client-safe outcome even if the
            # connection is no longer usable enough to roll the session back.
            pass
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc


@router.post("/login")
async def login(body: LoginRequest, db: DB) -> dict[str, Any]:
    user = await _login_user(body.username, db)
    if not await run_in_threadpool(verify_password, body.password, user.password_hash):
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "Invalid username or password.",
        )
    await _validate_login_account(user, db)
    access_token, refresh_token = _create_tokens(user)
    await _commit_login(user, db)
    return {
        "ok": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": _user_payload(user),
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest, db: DB) -> dict[str, Any]:
    try:
        claims = decode_token(body.refresh_token)
    except TokenValidationError as exc:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Authentication credentials are invalid.",
        ) from exc
    except AuthenticationConfigurationError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
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
    try:
        access_token = create_access_token({"sub": user.id})
    except AuthenticationConfigurationError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AUTH_SERVICE_UNAVAILABLE",
            "Authentication service is unavailable.",
        ) from exc
    return {"ok": True, "data": {"access_token": access_token, "token_type": "bearer"}}


@router.post("/logout")
async def logout(_: CurrentUser) -> dict[str, Any]:
    """Acknowledge client logout; stateless JWTs remain valid until expiry."""

    return {"ok": True, "data": {"message": "Logged out"}}


@router.get("/me")
async def me(current_user: CurrentUser) -> dict[str, Any]:
    return {"ok": True, "data": _user_payload(current_user)}
