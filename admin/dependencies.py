"""Authentication, tenant, and role dependencies for administrative routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from admin.db import get_db
from admin.models.tenant import Tenant
from admin.models.user import User
from admin.services.auth_service import decode_token

try:
    from admin.services.auth_service import (
        AuthenticationConfigurationError as _AuthenticationConfigurationError,
        TokenValidationError as _TokenValidationError,
    )
except ImportError:
    # The A4 auth service uses the underlying exception types directly. These
    # aliases also keep this dependency compatible with the hardened service
    # already present on the integration branch.
    _AuthenticationConfigurationError = RuntimeError
    _TokenValidationError = JWTError


ADMIN_ROLE_NAMES = frozenset({"super_admin", "admin", "agent_manager", "readonly"})
ADMIN_ONLY_ROLE_NAMES = frozenset({"super_admin", "admin"})
PUBLIC_ADMIN_PATHS = frozenset({
    "/api/admin/auth/login",
    "/api/admin/auth/refresh",
})

_bearer_scheme = HTTPBearer(auto_error=False)

DB = Annotated[AsyncSession, Depends(get_db)]


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    bearer: bool = False,
) -> HTTPException:
    """Build the structured error response used by the admin API."""
    headers = {"WWW-Authenticate": "Bearer"} if bearer else None
    return HTTPException(
        status_code=status_code,
        detail={"ok": False, "error": {"code": code, "message": message}},
        headers=headers,
    )


def _tenant_role_names(user: User) -> set[str]:
    """Return recognised roles that belong to the user's current tenant."""
    return {
        role.name
        for role in user.roles
        if role.tenant_id == user.tenant_id and role.name in ADMIN_ROLE_NAMES
    }


def is_admin_role(user: User) -> bool:
    """Return whether a user has the super-admin flag or an admin-level role."""
    return bool(user.is_superadmin) or bool(
        _tenant_role_names(user) & ADMIN_ONLY_ROLE_NAMES
    )


def has_admin_access(user: User) -> bool:
    """Return whether a user has any recognised administrative role."""
    return bool(user.is_superadmin) or bool(_tenant_role_names(user))


async def _load_current_user(user_id: str, db: AsyncSession) -> User:
    """Load live user, tenant, and role state instead of trusting JWT claims."""
    try:
        result = await db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Authentication credentials are invalid.",
                bearer=True,
            )

        # Usernames are currently used as business-agent identifiers. Reject
        # an already-issued token if that identifier has become ambiguous.
        matching_names = (
            await db.execute(
                select(func.count()).select_from(User).where(
                    User.username == user.username
                )
            )
        ).scalar_one()
        if matching_names != 1:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "UNAUTHORIZED",
                "Authentication credentials are invalid.",
                bearer=True,
            )

        tenant = await db.get(Tenant, user.tenant_id)
    except HTTPException:
        raise
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
    return user


async def authenticate_access_token(token: str, db: AsyncSession) -> User:
    """Resolve a live user from an access token for HTTP or WebSocket use."""
    try:
        claims = decode_token(token)
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
            bearer=True,
        ) from exc

    if claims.get("type") != "access":
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Authentication credentials are invalid.",
            bearer=True,
        )
    user_id = claims.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Authentication credentials are invalid.",
            bearer=True,
        )
    return await _load_current_user(user_id, db)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ],
    db: DB,
) -> User:
    """Resolve the request principal from a valid bearer access token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Authentication credentials are required.",
            bearer=True,
        )

    user = await authenticate_access_token(credentials.credentials, db)
    request.state.audit_principal = (user.id, user.tenant_id)
    return user


async def get_optional_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ],
    db: DB,
) -> User | None:
    """Return the current principal when a valid bearer token is present."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        user = await authenticate_access_token(credentials.credentials, db)
    except HTTPException:
        return None
    request.state.audit_principal = (user.id, user.tenant_id)
    return user


async def require_admin_auth(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ],
    db: DB,
) -> User | None:
    """Protect the admin router while leaving login and refresh public."""
    path = request.url.path.rstrip("/")
    if path in PUBLIC_ADMIN_PATHS:
        return None
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Authentication credentials are required.",
            bearer=True,
        )

    user = await authenticate_access_token(credentials.credentials, db)
    if not has_admin_access(user):
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "NO_ADMIN_ACCESS",
            "Administrative access is required.",
        )
    request.state.audit_principal = (user.id, user.tenant_id)
    return user


async def require_superadmin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require the live super-admin user flag."""
    if not current_user.is_superadmin:
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "INSUFFICIENT_ROLE",
            "Super-admin access is required.",
        )
    return current_user


def require_role(*allowed_roles: str) -> Callable[..., User]:
    """Build a dependency that accepts a super-admin or named tenant roles."""
    allowed = frozenset(allowed_roles)

    async def role_dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.is_superadmin or _tenant_role_names(current_user) & allowed:
            return current_user
        raise _error(
            status.HTTP_403_FORBIDDEN,
            "INSUFFICIENT_ROLE",
            "The current account does not have the required role.",
        )

    return role_dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
SuperAdmin = Annotated[User, Depends(require_superadmin)]
RoleAdmin = Annotated[User, Depends(require_role("super_admin", "admin"))]
RoleManager = Annotated[
    User,
    Depends(require_role("super_admin", "admin", "agent_manager")),
]
RoleAny = Annotated[User, Depends(require_role(*ADMIN_ROLE_NAMES))]
