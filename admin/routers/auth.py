"""Authentication routes for the staged administration console."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.db import get_db
from admin.dependencies import CurrentUser, is_admin_role, has_admin_access
from admin.models.user import User, Role
from admin.services.auth_service import (
    verify_password, create_access_token, create_refresh_token, decode_token,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


def _user_payload(user: User, roles: list[str]) -> dict:
    return {
        "sub": user.id,
        "tenant_id": user.tenant_id,
        "roles": roles,
        "is_superadmin": user.is_superadmin,
    }


def _user_schema(user: User, roles: list[str]) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "tenant_id": user.tenant_id,
        "is_superadmin": user.is_superadmin,
        "is_admin": is_admin_role(user),
        "tier": getattr(user, "tier", "agent") or "agent",
        "roles": roles,
    }


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"}},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"ok": False, "error": {"code": "ACCOUNT_DISABLED", "message": "Account is disabled"}},
        )

    # Load roles before constructing the signed identity payload.
    await db.refresh(user, ["roles"])
    role_names = [r.name for r in user.roles]

    # Only users with an admin-panel role can log in
    if not has_admin_access(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"ok": False, "error": {"code": "NO_ADMIN_ACCESS", "message": "This account cannot access the admin console"}},
        )

    payload = _user_payload(user, role_names)

    # Record the successful login in the same transaction.
    from admin.utils import now_beijing
    user.last_login_at = now_beijing()
    await db.commit()

    return {
        "ok": True,
        "data": {
            "access_token": create_access_token(payload),
            "refresh_token": create_refresh_token(payload),
            "token_type": "bearer",
            "user": _user_schema(user, role_names),
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    from jose import JWTError
    try:
        payload = decode_token(body.refresh_token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "INVALID_TOKEN", "message": str(e)}},
        )
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "INVALID_TOKEN", "message": "Refresh token required"}},
        )
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail={"ok": False, "error": {"code": "USER_NOT_FOUND", "message": "User not found"}})

    await db.refresh(user, ["roles"])
    role_names = [r.name for r in user.roles]

    # Validate user still has admin-panel access (role may have been revoked)
    if not has_admin_access(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"ok": False, "error": {"code": "NO_ADMIN_ACCESS", "message": "Admin access has been revoked for this account"}},
        )

    new_payload = _user_payload(user, role_names)
    return {
        "ok": True,
        "data": {"access_token": create_access_token(new_payload), "token_type": "bearer"},
    }


@router.post("/logout")
async def logout(user: CurrentUser):
    # JWTs are stateless; logout instructs the client to discard them.
    return {"ok": True, "data": {"message": "Logged out"}}


@router.get("/me")
async def me(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await db.refresh(user, ["roles"])
    role_names = [r.name for r in user.roles]
    return {"ok": True, "data": _user_schema(user, role_names)}
