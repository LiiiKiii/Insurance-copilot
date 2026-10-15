"""Secure administrative endpoints for non-secret system configuration."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from admin.config_bridge import invalidate
from admin.dependencies import DB, RoleAdmin, SuperAdmin, _error
from admin.models.config import SystemConfig, is_secret_config_key
from admin.models.user import User


router = APIRouter(prefix="/api/admin/configs", tags=["admin-system-configs"])
_CONFIG_TYPES = frozenset({"string", "int", "float", "json", "bool"})


class ConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_key: str = Field(min_length=1, max_length=200)
    config_value: str
    config_type: str = "string"
    description: str = Field(default="", max_length=500)
    is_public: bool = False
    tenant_id: str | None = Field(default=None, max_length=36)


class UpdateConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_value: str | None = None
    config_type: str | None = None
    description: str | None = Field(default=None, max_length=500)
    is_public: bool | None = None


def _payload(row: SystemConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "config_key": row.config_key,
        "config_value": row.config_value,
        "config_type": row.config_type,
        "description": row.description,
        "is_public": row.is_public,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _not_found() -> Exception:
    return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "System config not found")


def _forbidden() -> Exception:
    return _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")


def _validate_config(key: str, config_type: str) -> str:
    normalized = key.strip()
    if not normalized or is_secret_config_key(normalized):
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "INVALID_CONFIG_KEY", "Configuration key is not allowed")
    if config_type not in _CONFIG_TYPES:
        raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "INVALID_CONFIG_TYPE", "Configuration type is not supported")
    return normalized


async def _commit(db: DB) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "CONFLICT", "Configuration key already exists") from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database service is unavailable") from exc


async def _get_config(config_id: str, db: DB) -> SystemConfig:
    row = await db.get(SystemConfig, config_id)
    if row is None:
        raise _not_found()
    return row


def _public_value(row: SystemConfig) -> Any:
    try:
        if row.config_type == "int":
            return int(row.config_value)
        if row.config_type == "float":
            return float(row.config_value)
        if row.config_type == "bool":
            value = row.config_value.strip().casefold()
            if value in {"true", "1", "yes"}:
                return True
            if value in {"false", "0", "no"}:
                return False
            return None
        if row.config_type == "json":
            return json.loads(row.config_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return row.config_value


@router.get("/")
async def list_configs(
    current_user: RoleAdmin, db: DB, tenant_id: str | None = None
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (None, current_user.tenant_id):
        raise _forbidden()
    statement = select(SystemConfig).order_by(SystemConfig.config_key.asc(), SystemConfig.id.asc())
    if tenant_id is not None:
        statement = statement.where(SystemConfig.tenant_id == tenant_id)
    elif not current_user.is_superadmin:
        statement = statement.where(
            (SystemConfig.tenant_id == current_user.tenant_id) | SystemConfig.tenant_id.is_(None)
        )
    rows = (await db.execute(statement)).scalars().all()
    return {"ok": True, "data": [_payload(row) for row in rows]}


@router.get("/public")
async def public_configs(_: RoleAdmin, db: DB) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(SystemConfig)
            .where(SystemConfig.tenant_id.is_(None), SystemConfig.is_public.is_(True))
            .order_by(SystemConfig.config_key.asc())
        )
    ).scalars().all()
    return {"ok": True, "data": {row.config_key: _public_value(row) for row in rows}}


@router.get("/{config_key}")
async def get_config(
    config_key: str, current_user: RoleAdmin, db: DB, tenant_id: str | None = None
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (None, current_user.tenant_id):
        raise _forbidden()
    if tenant_id is not None:
        row = (
            await db.execute(
                select(SystemConfig).where(
                    SystemConfig.config_key == config_key, SystemConfig.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
    elif current_user.is_superadmin:
        row = (
            await db.execute(
                select(SystemConfig).where(
                    SystemConfig.config_key == config_key, SystemConfig.tenant_id.is_(None)
                )
            )
        ).scalar_one_or_none()
    else:
        row = (
            await db.execute(
                select(SystemConfig).where(
                    SystemConfig.config_key == config_key,
                    SystemConfig.tenant_id == current_user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = (
                await db.execute(
                    select(SystemConfig).where(
                        SystemConfig.config_key == config_key, SystemConfig.tenant_id.is_(None)
                    )
                )
            ).scalar_one_or_none()
    if row is None:
        raise _not_found()
    return {"ok": True, "data": _payload(row)}


@router.post("/")
async def create_config(body: ConfigRequest, _: SuperAdmin, db: DB) -> dict[str, Any]:
    key = _validate_config(body.config_key, body.config_type)
    statement = select(SystemConfig.id).where(SystemConfig.config_key == key)
    statement = statement.where(
        SystemConfig.tenant_id.is_(None)
        if body.tenant_id is None
        else SystemConfig.tenant_id == body.tenant_id
    )
    if (await db.execute(statement)).scalar_one_or_none() is not None:
        raise _error(status.HTTP_409_CONFLICT, "CONFLICT", "Configuration key already exists")
    values = body.model_dump()
    values["config_key"] = key
    row = SystemConfig(**values)
    db.add(row)
    await _commit(db)
    if row.tenant_id is None:
        invalidate(row.config_key)
    return {"ok": True, "data": _payload(row)}


@router.put("/{config_id}")
async def update_config(config_id: str, body: UpdateConfigRequest, _: SuperAdmin, db: DB) -> dict[str, Any]:
    row = await _get_config(config_id, db)
    changes = body.model_dump(exclude_unset=True)
    config_type = changes.get("config_type", row.config_type)
    _validate_config(row.config_key, config_type)
    for field, value in changes.items():
        setattr(row, field, value)
    await _commit(db)
    if row.tenant_id is None:
        invalidate(row.config_key)
    return {"ok": True, "data": _payload(row)}


@router.delete("/{config_id}")
async def delete_config(config_id: str, _: SuperAdmin, db: DB) -> dict[str, Any]:
    row = await _get_config(config_id, db)
    key, global_scope = row.config_key, row.tenant_id is None
    await db.delete(row)
    await _commit(db)
    if global_scope:
        invalidate(key)
    return {"ok": True, "data": {"message": "System config deleted"}}
