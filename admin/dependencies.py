"""FastAPI dependency factories for auth and tenant injection."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from admin.db import get_db
from admin.models.user import User
from admin.services.auth_service import decode_token


# Roles that are permitted to enter the A4 administration surface.
ADMIN_ROLES = frozenset({"super_admin", "admin", "agent_manager", "readonly"})


def _user_role_names(user: User) -> set[str]:
    """Extract role name set from a user, handling unloaded relationships."""
    if user.is_superadmin:
        return {"super_admin"}
    return {r.name for r in user.roles} if hasattr(user, "roles") else set()


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "UNAUTHORIZED", "message": "Bearer token required"}},
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "INVALID_TOKEN", "message": str(e)}},
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "INVALID_TOKEN", "message": "Access token required"}},
        )
    user_id = payload.get("sub")
    result = await db.execute(select(User).options(selectinload(User.roles)).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"ok": False, "error": {"code": "USER_NOT_FOUND", "message": "User not found or inactive"}},
        )
    return user


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Same as get_current_user but returns None instead of raising."""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return None


async def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"ok": False, "error": {"code": "FORBIDDEN", "message": "Superadmin required"}},
        )
    return user


def require_role(*allowed: str):
    """Return a FastAPI dependency that checks user has at least one of *allowed* roles.

    Usage::

        @router.post("/")
        async def create_kb(user: RoleAdmin, ...):
            ...

    ``is_superadmin`` always passes (implicit ``super_admin`` role).
    """
    allowed_set = frozenset(allowed)

    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.is_superadmin:
            return user
        user_roles = _user_role_names(user)
        if not user_roles & allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "ok": False,
                    "error": {
                        "code": "INSUFFICIENT_ROLE",
                        "message": f"One of these roles is required: {', '.join(sorted(allowed_set))}",
                    },
                },
            )
        return user

    return Depends(_check)


def is_admin_role(user: User) -> bool:
    """Return whether a user has tenant-administrator privileges."""
    if user.is_superadmin:
        return True
    role_names = _user_role_names(user)
    return bool(role_names & {"super_admin", "admin"})


def has_admin_access(user: User) -> bool:
    """Check if user has any admin-panel role (used to gate admin login)."""
    if user.is_superadmin:
        return True
    role_names = _user_role_names(user)
    return bool(role_names & ADMIN_ROLES)


# Public endpoints use exact path matching to avoid prefix-based bypasses.
_PUBLIC_AUTH_PATHS = frozenset({
    "/api/admin/auth/login",
    "/api/admin/auth/refresh",
    "/api/admin/agent/status",
})


async def require_admin_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Global auth guard for all /api/admin/* routes.

    Skips authentication for public endpoints (login, refresh, status).
    """
    path = request.url.path.rstrip("/")
    if path in _PUBLIC_AUTH_PATHS:
        return
    await get_current_user(authorization=authorization, db=db)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
SuperAdmin = Annotated[User, Depends(require_superadmin)]
DB = Annotated[AsyncSession, Depends(get_db)]

# ── Role-based type aliases for route signatures ─────────────────────────────
# super_admin + admin
RoleAdmin = Annotated[User, require_role("super_admin", "admin")]
# super_admin + admin + agent_manager
RoleManager = Annotated[User, require_role("super_admin", "admin", "agent_manager")]
# any admin-panel role (including readonly)
RoleAny = Annotated[User, require_role("super_admin", "admin", "agent_manager", "readonly")]
