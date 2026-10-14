"""Secure administrative model-configuration endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from admin.dependencies import DB, RoleAdmin, SuperAdmin, _error
from admin.models.model_config import ModelConfig
from admin.models.user import User
from admin.services.crypto_service import EncryptionConfigurationError, encrypt_if_not_empty


router = APIRouter(prefix="/api/admin/model-configs", tags=["admin-model-configs"])


class ModelConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=50)
    model_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    model_type: str = Field(default="llm", min_length=1, max_length=20)
    category: str = Field(default="chat", min_length=1, max_length=20)
    api_key: str | None = Field(default=None, max_length=10_000)
    base_url: str | None = Field(default=None, max_length=500)
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.7, ge=0)
    price_per_1k_input: float = Field(default=0.0, ge=0)
    price_per_1k_output: float = Field(default=0.0, ge=0)
    enabled: bool = True
    is_default: bool = False
    tenant_id: str | None = Field(default=None, max_length=36)


class ModelConfigUpdateRequest(BaseModel):
    """Mutable model fields; tenant ownership and identifiers are never mutable."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(default=None, min_length=1, max_length=50)
    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    model_type: str | None = Field(default=None, min_length=1, max_length=20)
    category: str | None = Field(default=None, min_length=1, max_length=20)
    api_key: str | None = Field(default=None, max_length=10_000)
    base_url: str | None = Field(default=None, max_length=500)
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)
    price_per_1k_input: float | None = Field(default=None, ge=0)
    price_per_1k_output: float | None = Field(default=None, ge=0)
    enabled: bool | None = None
    is_default: bool | None = None


def _payload(row: ModelConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "provider": row.provider,
        "model_id": row.model_id,
        "display_name": row.display_name,
        "model_type": row.model_type,
        "category": row.category,
        "base_url": row.base_url,
        "max_tokens": row.max_tokens,
        "temperature": row.temperature,
        "price_per_1k_input": row.price_per_1k_input,
        "price_per_1k_output": row.price_per_1k_output,
        "enabled": row.enabled,
        "is_default": row.is_default,
        "has_api_key": bool(row.api_key_encrypted),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _not_found() -> Exception:
    return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Model config not found")


def _forbidden() -> Exception:
    return _error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Access denied")


def _visible_to(user: User, row: ModelConfig) -> bool:
    return user.is_superadmin or row.tenant_id is None or row.tenant_id == user.tenant_id


def _modifiable_by(user: User, row: ModelConfig) -> bool:
    """Tenant admins may alter only records owned by their own tenant."""

    return user.is_superadmin or row.tenant_id == user.tenant_id


async def _get_visible(model_id: str, current_user: User, db: DB) -> ModelConfig:
    row = await db.get(ModelConfig, model_id)
    if row is None:
        raise _not_found()
    if not _visible_to(current_user, row):
        raise _forbidden()
    return row


async def _commit(db: DB) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "CONFLICT", "Model configuration conflicts with existing data") from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE", "Database service is unavailable") from exc


async def _clear_conflicting_defaults(row: ModelConfig, db: DB) -> None:
    """Clear only defaults in the row's deterministic selection scope.

    The legacy global bridge selects a global LLM default by model type alone,
    so every enabled global LLM default shares one scope regardless of category.
    Other defaults remain scoped by tenant, type, and category.
    """

    # Materialize a newly-added row before binding its id into the exclusion.
    # Without this, ``id != None`` becomes ``id IS NOT NULL`` and can unset the
    # new default along with the conflicting records.
    await db.flush()
    statement = select(ModelConfig).where(
        ModelConfig.id != row.id,
        ModelConfig.is_default.is_(True),
        ModelConfig.enabled.is_(True),
    )
    if row.tenant_id is None and row.model_type == "llm":
        statement = statement.where(
            ModelConfig.tenant_id.is_(None), ModelConfig.model_type == "llm"
        )
    else:
        tenant_clause = (
            ModelConfig.tenant_id.is_(None)
            if row.tenant_id is None
            else ModelConfig.tenant_id == row.tenant_id
        )
        statement = statement.where(
            tenant_clause,
            ModelConfig.model_type == row.model_type,
            ModelConfig.category == row.category,
        )
    for other in (await db.execute(statement)).scalars():
        other.is_default = False


async def _apply_default_invariant(row: ModelConfig, db: DB) -> None:
    if not row.enabled:
        row.is_default = False
    elif row.is_default:
        await _clear_conflicting_defaults(row, db)


def _encrypted_key(api_key: str | None) -> str | None:
    try:
        return encrypt_if_not_empty(api_key)
    except EncryptionConfigurationError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ENCRYPTION_UNAVAILABLE",
            "Credential encryption is unavailable.",
        ) from exc


@router.get("/")
async def list_model_configs(
    current_user: RoleAdmin,
    db: DB,
    tenant_id: str | None = None,
    model_type: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    if not current_user.is_superadmin and tenant_id not in (None, current_user.tenant_id):
        raise _forbidden()
    statement = select(ModelConfig).order_by(ModelConfig.created_at.asc(), ModelConfig.id.asc())
    if tenant_id is not None:
        statement = statement.where(ModelConfig.tenant_id == tenant_id)
    elif not current_user.is_superadmin:
        statement = statement.where(
            (ModelConfig.tenant_id == current_user.tenant_id) | ModelConfig.tenant_id.is_(None)
        )
    if model_type is not None:
        statement = statement.where(ModelConfig.model_type == model_type)
    if category is not None:
        statement = statement.where(ModelConfig.category == category)
    rows = (await db.execute(statement)).scalars().all()
    return {"ok": True, "data": [_payload(row) for row in rows]}


@router.post("/")
async def create_model_config(body: ModelConfigRequest, _: SuperAdmin, db: DB) -> dict[str, Any]:
    encrypted_key = _encrypted_key(body.api_key)
    row = ModelConfig(
        **body.model_dump(exclude={"api_key"}), api_key_encrypted=encrypted_key
    )
    db.add(row)
    await _apply_default_invariant(row, db)
    await _commit(db)
    return {"ok": True, "data": _payload(row)}


@router.get("/defaults")
async def list_default_models(
    current_user: RoleAdmin, db: DB, model_type: str | None = None
) -> dict[str, Any]:
    statement = select(ModelConfig).where(ModelConfig.enabled.is_(True), ModelConfig.is_default.is_(True))
    if not current_user.is_superadmin:
        statement = statement.where(
            (ModelConfig.tenant_id == current_user.tenant_id) | ModelConfig.tenant_id.is_(None)
        )
    if model_type is not None:
        statement = statement.where(ModelConfig.model_type == model_type)
    rows = (await db.execute(statement.order_by(ModelConfig.id.asc()))).scalars().all()
    return {"ok": True, "data": [_payload(row) for row in rows]}


@router.get("/{model_id}")
async def get_model_config(model_id: str, current_user: RoleAdmin, db: DB) -> dict[str, Any]:
    return {"ok": True, "data": _payload(await _get_visible(model_id, current_user, db))}


@router.put("/{model_id}")
async def update_model_config(
    model_id: str, body: ModelConfigUpdateRequest, current_user: RoleAdmin, db: DB
) -> dict[str, Any]:
    row = await _get_visible(model_id, current_user, db)
    if not _modifiable_by(current_user, row):
        raise _forbidden()
    changes = body.model_dump(exclude_unset=True, exclude={"api_key"})
    encrypted_key = _encrypted_key(body.api_key) if body.api_key not in (None, "") else None
    for field, value in changes.items():
        setattr(row, field, value)
    if encrypted_key is not None:
        row.api_key_encrypted = encrypted_key
    await _apply_default_invariant(row, db)
    await _commit(db)
    return {"ok": True, "data": _payload(row)}


@router.delete("/{model_id}")
async def delete_model_config(model_id: str, _: SuperAdmin, db: DB) -> dict[str, Any]:
    row = await db.get(ModelConfig, model_id)
    if row is None:
        raise _not_found()
    await db.delete(row)
    await _commit(db)
    return {"ok": True, "data": {"message": "Model config deleted"}}


@router.post("/{model_id}/set-default")
@router.put("/{model_id}/set-default")
async def set_default_model(model_id: str, current_user: RoleAdmin, db: DB) -> dict[str, Any]:
    row = await _get_visible(model_id, current_user, db)
    if not _modifiable_by(current_user, row):
        raise _forbidden()
    if not row.enabled:
        raise _error(status.HTTP_409_CONFLICT, "CONFLICT", "Disabled models cannot be defaults")
    row.is_default = True
    await _clear_conflicting_defaults(row, db)
    await _commit(db)
    return {"ok": True, "data": _payload(row)}


@router.post("/{model_id}/toggle-active")
async def toggle_model_active(model_id: str, current_user: RoleAdmin, db: DB) -> dict[str, Any]:
    row = await _get_visible(model_id, current_user, db)
    if not _modifiable_by(current_user, row):
        raise _forbidden()
    row.enabled = not row.enabled
    if not row.enabled:
        row.is_default = False
    await _commit(db)
    return {"ok": True, "data": _payload(row)}
