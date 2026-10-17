"""Tenant-aware user and role administration endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from admin.dependencies import DB, RoleAdmin, RoleAny, SuperAdmin, _error, is_admin_role
from admin.models.user import Role, User
from admin.routers._business import (
    commit_or_error,
    ensure_tenant_access,
    ensure_tenant_exists,
    resolve_tenant_id,
)
from admin.services.auth_service import hash_password

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
AgentTier = Literal["director", "team_lead", "senior_agent", "agent"]


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=1024)
    display_name: str = Field(default="", max_length=200)
    tenant_id: str | None = Field(default=None, max_length=36)
    is_superadmin: bool = False
    role_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    tier: AgentTier = "agent"
    supervisor_id: str | None = Field(default=None, max_length=36)
    daily_call_limit: int = Field(default=50, ge=0)


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, min_length=3, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=1024)
    is_active: bool | None = None
    role_ids: list[str] | None = None
    roles: list[str] | None = None
    tier: AgentTier | None = None
    supervisor_id: str | None = Field(default=None, max_length=36)
    daily_call_limit: int | None = Field(default=None, ge=0)


class CreateRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


def _role_payload(role: Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "tenant_id": role.tenant_id,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
    }


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "tenant_id": user.tenant_id,
        "is_active": user.is_active,
        "is_superadmin": user.is_superadmin,
        "is_admin": is_admin_role(user),
        "tier": user.tier or "agent",
        "supervisor_id": user.supervisor_id,
        "daily_call_limit": user.daily_call_limit,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "roles": [
            _role_payload(role)
            for role in sorted(user.roles, key=lambda item: item.name)
        ],
    }


async def _roles_for_request(
    db: DB,
    tenant_id: str,
    role_ids: list[str] | None,
    role_names: list[str] | None,
) -> list[Role]:
    requested_ids = set(role_ids or [])
    requested_names = set(role_names or [])
    if not requested_ids and not requested_names:
        return []

    filters = []
    if requested_ids:
        filters.append(Role.id.in_(requested_ids))
    if requested_names:
        filters.append(Role.name.in_(requested_names))
    statement = select(Role).where(Role.tenant_id == tenant_id, or_(*filters))
    rows = (await db.execute(statement)).scalars().all()
    found_ids = {role.id for role in rows}
    found_names = {role.name for role in rows}
    if requested_ids - found_ids or requested_names - found_names:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "ROLE_NOT_FOUND",
            "One or more roles were not found",
        )
    return list({role.id: role for role in rows}.values())


async def _load_user(user_id: str, db: DB) -> User:
    statement = select(User).options(selectinload(User.roles)).where(User.id == user_id)
    user = (await db.execute(statement)).scalar_one_or_none()
    if user is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "User not found")
    return user


async def _validate_supervisor(
    db: DB,
    *,
    tenant_id: str,
    supervisor_id: str | None,
    user_id: str | None = None,
) -> None:
    if not supervisor_id:
        return
    if supervisor_id == user_id:
        raise _error(
            status.HTTP_409_CONFLICT,
            "INVALID_SUPERVISOR",
            "A user cannot supervise itself",
        )
    supervisor = await db.get(User, supervisor_id)
    if supervisor is None or supervisor.tenant_id != tenant_id:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "SUPERVISOR_NOT_FOUND",
            "Supervisor was not found in this tenant",
        )


@router.get("/")
async def list_users(
    current_user: RoleAny,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (
        None,
        current_user.tenant_id,
    ):
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")

    statement = select(User).options(selectinload(User.roles))
    if tenant_id is not None:
        statement = statement.where(User.tenant_id == tenant_id)
    elif not current_user.is_superadmin:
        statement = statement.where(User.tenant_id == current_user.tenant_id)
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(User.username.ilike(term), User.email.ilike(term))
        )

    count_statement = select(func.count()).select_from(
        statement.order_by(None).subquery()
    )
    total = int((await db.execute(count_statement)).scalar_one())
    result = await db.execute(
        statement.order_by(User.username.asc(), User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = result.scalars().unique().all()
    return {
        "ok": True,
        "data": [_user_payload(user) for user in users],
        "meta": {"page": page, "page_size": page_size, "total": total},
    }


@router.post("/")
async def create_user(
    body: CreateUserRequest,
    current_user: SuperAdmin,
    db: DB,
) -> dict[str, Any]:
    tenant_id = resolve_tenant_id(current_user, body.tenant_id)
    await ensure_tenant_exists(db, tenant_id)
    duplicate = await db.execute(
        select(User.id).where(
            or_(User.username == body.username, User.email == body.email)
        )
    )
    if duplicate.first() is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "USER_EXISTS",
            "Username or email is already registered",
        )

    roles = await _roles_for_request(db, tenant_id, body.role_ids, body.roles)
    await _validate_supervisor(
        db,
        tenant_id=tenant_id,
        supervisor_id=body.supervisor_id,
    )
    password_hash = await run_in_threadpool(hash_password, body.password)
    user = User(
        tenant_id=tenant_id,
        username=body.username,
        email=body.email,
        password_hash=password_hash,
        display_name=body.display_name,
        is_superadmin=body.is_superadmin,
        tier=body.tier,
        supervisor_id=body.supervisor_id,
        daily_call_limit=body.daily_call_limit,
        roles=roles,
    )
    db.add(user)
    await commit_or_error(db, conflict_message="User conflicts with existing data")
    return {"ok": True, "data": _user_payload(user)}


@router.get("/roles/list")
async def list_roles(
    current_user: RoleAny,
    db: DB,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (
        None,
        current_user.tenant_id,
    ):
        raise _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")
    statement = select(Role)
    if tenant_id is not None:
        statement = statement.where(Role.tenant_id == tenant_id)
    elif not current_user.is_superadmin:
        statement = statement.where(Role.tenant_id == current_user.tenant_id)
    roles = (
        (await db.execute(statement.order_by(Role.name.asc(), Role.id.asc())))
        .scalars()
        .all()
    )
    return {"ok": True, "data": [_role_payload(role) for role in roles]}


@router.post("/roles")
async def create_role(
    body: CreateRoleRequest,
    current_user: SuperAdmin,
    db: DB,
) -> dict[str, Any]:
    tenant_id = resolve_tenant_id(current_user, body.tenant_id)
    await ensure_tenant_exists(db, tenant_id)
    duplicate = await db.execute(
        select(Role.id).where(Role.tenant_id == tenant_id, Role.name == body.name)
    )
    if duplicate.first() is not None:
        raise _error(
            status.HTTP_409_CONFLICT,
            "ROLE_EXISTS",
            "Role already exists in this tenant",
        )
    role = Role(tenant_id=tenant_id, name=body.name, description=body.description)
    db.add(role)
    await commit_or_error(db, conflict_message="Role conflicts with existing data")
    return {"ok": True, "data": _role_payload(role)}


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, _: SuperAdmin, db: DB) -> dict[str, Any]:
    role = await db.get(Role, role_id)
    if role is None:
        raise _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Role not found")
    if role.is_system:
        raise _error(
            status.HTTP_409_CONFLICT, "SYSTEM_ROLE", "System roles cannot be deleted"
        )
    await db.delete(role)
    await commit_or_error(db, conflict_message="Role is still in use")
    return {"ok": True, "data": {"message": "Role deleted"}}


@router.get("/{user_id}")
async def get_user(user_id: str, current_user: RoleAny, db: DB) -> dict[str, Any]:
    user = await _load_user(user_id, db)
    ensure_tenant_access(current_user, user.tenant_id)
    return {"ok": True, "data": _user_payload(user)}


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    current_user: RoleAdmin,
    db: DB,
) -> dict[str, Any]:
    user = await _load_user(user_id, db)
    ensure_tenant_access(current_user, user.tenant_id)

    if body.email is not None and body.email != user.email:
        duplicate = await db.execute(select(User.id).where(User.email == body.email))
        if duplicate.first() is not None:
            raise _error(
                status.HTTP_409_CONFLICT, "EMAIL_TAKEN", "Email is already registered"
            )
        user.email = body.email
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.password is not None:
        user.password_hash = await run_in_threadpool(hash_password, body.password)
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.tier is not None:
        user.tier = body.tier
    if body.supervisor_id is not None:
        await _validate_supervisor(
            db,
            tenant_id=user.tenant_id,
            supervisor_id=body.supervisor_id,
            user_id=user.id,
        )
        user.supervisor_id = body.supervisor_id or None
    if body.daily_call_limit is not None:
        user.daily_call_limit = body.daily_call_limit
    if body.role_ids is not None or body.roles is not None:
        user.roles = await _roles_for_request(
            db,
            user.tenant_id,
            body.role_ids,
            body.roles,
        )

    await commit_or_error(db, conflict_message="User conflicts with existing data")
    return {"ok": True, "data": _user_payload(user)}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: SuperAdmin,
    db: DB,
) -> dict[str, Any]:
    user = await _load_user(user_id, db)
    if user.id == current_user.id:
        raise _error(
            status.HTTP_409_CONFLICT,
            "SELF_DELETE",
            "The active account cannot delete itself",
        )
    await db.delete(user)
    await commit_or_error(
        db, conflict_message="User is still referenced by other records"
    )
    return {"ok": True, "data": {"message": "User deleted"}}
