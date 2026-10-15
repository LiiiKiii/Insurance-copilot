"""Secure persisted runtime configuration resolution.

``SystemConfig`` stores only non-secret runtime metadata.  The Fernet token
for an applied runtime remains in the existing ``ModelConfig`` encrypted
credential column, referenced by that metadata.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from admin.config_bridge import DefaultModelConfigurationError, get_default_model_config
from admin.db import get_sync_db
from admin.models.config import SystemConfig
from admin.models.model_config import ModelConfig
from admin.services.crypto_service import (
    CredentialDecryptionError,
    EncryptionConfigurationError,
    decrypt_if_not_empty,
    encrypt_if_not_empty,
)
from nanobot.config.loader import load_config
from nanobot.config.schema import Config


RUNTIME_CONFIG_KEY = "runtime.api_config"
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_PERSISTED_RUNTIME_DISPLAY_NAME = "Persisted Runtime Configuration"


class RuntimeConfigurationError(RuntimeError):
    """Raised when selected persisted runtime configuration is unusable."""


@dataclass(frozen=True)
class RuntimePersistenceSnapshot:
    metadata: dict[str, Any] | None
    model: dict[str, Any] | None
    created_model_id: str | None


def _normalized_base_url(value: object) -> str:
    base_url = value.strip() if isinstance(value, str) else ""
    return (base_url or _OPENROUTER_BASE_URL).rstrip("/")


def _apply_openrouter(config: Config, *, model: object, api_key: object, base_url: object) -> Config:
    if not isinstance(model, str) or not model.strip():
        raise RuntimeConfigurationError("Stored runtime model is invalid.")
    if not isinstance(api_key, str) or not api_key:
        raise RuntimeConfigurationError("Stored runtime credential is unavailable.")
    if _normalized_base_url(base_url) != _OPENROUTER_BASE_URL:
        raise RuntimeConfigurationError("Stored runtime endpoint is not permitted.")
    resolved = config.model_copy(deep=True)
    resolved.agents.defaults.provider = "openrouter"
    resolved.agents.defaults.model = model.strip()
    resolved.providers.openrouter.api_key = api_key
    resolved.providers.openrouter.api_base = _OPENROUTER_BASE_URL
    return resolved


def _environment_config(config: Config) -> Config:
    """Retain existing config loading and recognize the established key name."""

    resolved = config.model_copy(deep=True)
    if not resolved.providers.openrouter.api_key:
        resolved.providers.openrouter.api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not resolved.providers.openrouter.api_base:
        resolved.providers.openrouter.api_base = _OPENROUTER_BASE_URL
    return resolved


def _default_runtime_config(config: Config) -> Config | None:
    try:
        default = get_default_model_config()
    except DefaultModelConfigurationError as exc:
        raise RuntimeConfigurationError("Default model credential cannot be decrypted.") from exc
    if default is None:
        return None
    if str(default.get("provider", "")).casefold() != "openrouter":
        return None
    api_key = default.get("api_key")
    if not isinstance(api_key, str) or not api_key:
        return None
    try:
        return _apply_openrouter(
            config,
            model=default.get("model_id"),
            api_key=api_key,
            base_url=default.get("base_url"),
        )
    except RuntimeConfigurationError:
        # An administrator record outside the supported OpenRouter contract is
        # not a usable runtime default; allow the persisted fallback instead.
        return None


def _persisted_runtime_config(config: Config) -> Config | None:
    try:
        with get_sync_db() as db:
            metadata = (
                db.query(SystemConfig)
                .filter(
                    SystemConfig.tenant_id.is_(None),
                    SystemConfig.config_key == RUNTIME_CONFIG_KEY,
                )
                .one_or_none()
            )
            if metadata is None:
                return None
            try:
                value = json.loads(metadata.config_value)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeConfigurationError("Persisted runtime configuration is invalid.") from exc
            if (
                metadata.config_type != "json"
                or not isinstance(value, dict)
                or value.get("provider") != "openrouter"
            ):
                raise RuntimeConfigurationError("Persisted runtime configuration is invalid.")
            model_id = value.get("model_config_id")
            if not isinstance(model_id, str) or not model_id:
                raise RuntimeConfigurationError("Persisted runtime configuration is invalid.")
            model = db.get(ModelConfig, model_id)
            if (
                model is None
                or model.tenant_id is not None
                or not model.enabled
                or model.provider.casefold() != "openrouter"
                or not model.api_key_encrypted
                or model.model_id != value.get("model")
            ):
                raise RuntimeConfigurationError("Persisted runtime credential is unavailable.")
            try:
                api_key = decrypt_if_not_empty(model.api_key_encrypted)
            except (CredentialDecryptionError, EncryptionConfigurationError) as exc:
                raise RuntimeConfigurationError("Persisted runtime credential cannot be decrypted.") from exc
    except SQLAlchemyError:
        # Database unavailability is equivalent to there being no usable
        # persisted fallback; retain the established environment fallback.
        return None

    return _apply_openrouter(
        config,
        model=value.get("model"),
        api_key=api_key,
        base_url=value.get("baseUrl"),
    )


def resolve_startup_runtime_config() -> Config:
    """Apply default-model, persisted-runtime, then environment precedence."""

    base = load_config()
    default = _default_runtime_config(base)
    if default is not None:
        return default
    persisted = _persisted_runtime_config(base)
    if persisted is not None:
        return persisted
    return _environment_config(base)


def _snapshot_model(row: ModelConfig | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "provider": row.provider,
        "model_id": row.model_id,
        "display_name": row.display_name,
        "model_type": row.model_type,
        "category": row.category,
        "api_key_encrypted": row.api_key_encrypted,
        "base_url": row.base_url,
        "max_tokens": row.max_tokens,
        "temperature": row.temperature,
        "price_per_1k_input": row.price_per_1k_input,
        "price_per_1k_output": row.price_per_1k_output,
        "enabled": row.enabled,
        "is_default": row.is_default,
    }


def _snapshot_metadata(row: SystemConfig | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "config_key": row.config_key,
        "config_value": row.config_value,
        "config_type": row.config_type,
        "description": row.description,
        "is_public": row.is_public,
    }


async def persist_runtime_config(
    db: AsyncSession,
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    enable_thinking: bool,
) -> RuntimePersistenceSnapshot:
    """Commit a safe runtime record before publishing its candidate runtime."""

    if provider.casefold() != "openrouter" or _normalized_base_url(base_url) != _OPENROUTER_BASE_URL:
        raise RuntimeConfigurationError("The requested runtime configuration is not permitted.")
    try:
        encrypted_key = encrypt_if_not_empty(api_key)
    except EncryptionConfigurationError as exc:
        raise RuntimeConfigurationError("Credential encryption is unavailable.") from exc
    if not encrypted_key:
        raise RuntimeConfigurationError("Runtime credentials are required.")

    metadata = (
        await db.execute(
            select(SystemConfig).where(
                SystemConfig.tenant_id.is_(None), SystemConfig.config_key == RUNTIME_CONFIG_KEY
            )
        )
    ).scalar_one_or_none()
    pointed_model: ModelConfig | None = None
    if metadata is not None:
        try:
            prior = json.loads(metadata.config_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            prior = None
        if isinstance(prior, dict) and isinstance(prior.get("model_config_id"), str):
            pointed_model = await db.get(ModelConfig, prior["model_config_id"])

    snapshot = RuntimePersistenceSnapshot(
        metadata=_snapshot_metadata(metadata),
        model=_snapshot_model(pointed_model),
        created_model_id=None,
    )
    if pointed_model is None:
        pointed_model = ModelConfig(
            id=str(uuid.uuid4()),
            tenant_id=None,
            provider="openrouter",
            model_id=model,
            display_name=_PERSISTED_RUNTIME_DISPLAY_NAME,
            model_type="llm",
            category="chat",
            enabled=True,
            is_default=False,
        )
        db.add(pointed_model)
        snapshot = RuntimePersistenceSnapshot(
            metadata=snapshot.metadata,
            model=None,
            created_model_id=pointed_model.id,
        )
    elif (
        pointed_model.tenant_id is not None
        or pointed_model.is_default
        or pointed_model.display_name != _PERSISTED_RUNTIME_DISPLAY_NAME
    ):
        # Metadata must not be able to redirect Apply into an unrelated
        # administrator-managed record.
        pointed_model = ModelConfig(
            id=str(uuid.uuid4()),
            tenant_id=None,
            provider="openrouter",
            model_id=model,
            display_name=_PERSISTED_RUNTIME_DISPLAY_NAME,
            model_type="llm",
            category="chat",
            enabled=True,
            is_default=False,
        )
        db.add(pointed_model)
        snapshot = RuntimePersistenceSnapshot(
            metadata=snapshot.metadata,
            model=None,
            created_model_id=pointed_model.id,
        )

    pointed_model.tenant_id = None
    pointed_model.provider = "openrouter"
    pointed_model.model_id = model
    pointed_model.model_type = "llm"
    pointed_model.category = "chat"
    pointed_model.base_url = _OPENROUTER_BASE_URL
    pointed_model.api_key_encrypted = encrypted_key
    pointed_model.enabled = True
    pointed_model.is_default = False
    await db.flush()

    metadata_value = json.dumps(
        {
            "provider": "openrouter",
            "model": model,
            "baseUrl": _OPENROUTER_BASE_URL,
            "model_config_id": pointed_model.id,
            "enableThinking": bool(enable_thinking),
        },
        sort_keys=True,
    )
    if metadata is None:
        metadata = SystemConfig(
            config_key=RUNTIME_CONFIG_KEY,
            config_value=metadata_value,
            config_type="json",
            description="Persisted runtime configuration metadata",
            is_public=False,
        )
        db.add(metadata)
    else:
        metadata.config_value = metadata_value
        metadata.config_type = "json"
        metadata.is_public = False
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise RuntimeConfigurationError("Runtime configuration could not be persisted.") from exc
    return snapshot


async def restore_runtime_config(db: AsyncSession, snapshot: RuntimePersistenceSnapshot) -> None:
    """Restore persistent state after a replacement fails before publication."""

    if snapshot.created_model_id is not None:
        created = await db.get(ModelConfig, snapshot.created_model_id)
        if created is not None:
            await db.delete(created)
    elif snapshot.model is not None:
        row = await db.get(ModelConfig, snapshot.model["id"])
        if row is not None:
            for field, value in snapshot.model.items():
                setattr(row, field, value)

    metadata = (
        await db.execute(
            select(SystemConfig).where(
                SystemConfig.tenant_id.is_(None), SystemConfig.config_key == RUNTIME_CONFIG_KEY
            )
        )
    ).scalar_one_or_none()
    if snapshot.metadata is None:
        if metadata is not None:
            await db.delete(metadata)
    elif metadata is not None:
        for field, value in snapshot.metadata.items():
            setattr(metadata, field, value)
    else:
        db.add(SystemConfig(**snapshot.metadata))
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise RuntimeConfigurationError("Runtime configuration rollback failed.") from exc
