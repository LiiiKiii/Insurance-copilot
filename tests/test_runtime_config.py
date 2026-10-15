"""Disposable-database tests for secure runtime configuration precedence."""
from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

import admin.db
from admin.db import Base
from admin.models.config import SystemConfig
from admin.models.model_config import ModelConfig
from admin.services.crypto_service import decrypt_if_not_empty, encrypt
from api.runtime_config import (
    RUNTIME_CONFIG_KEY,
    RuntimeConfigurationError,
    persist_runtime_config,
    resolve_startup_runtime_config,
)
from nanobot.config.schema import Config


class RuntimeConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        path = Path(self.temp_dir.name) / "runtime-config.db"
        self.sync_engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self.sync_engine)
        self.sessions = sessionmaker(self.sync_engine, expire_on_commit=False)
        self.async_engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        self.async_sessions = async_sessionmaker(self.async_engine, expire_on_commit=False)
        self.session_patch = patch.object(admin.db, "SyncSessionFactory", self.sessions)
        self.session_patch.start()
        self.environment = patch.dict(os.environ, {"ADMIN_ENCRYPTION_KEY": Fernet.generate_key().decode(), "OPENROUTER_API_KEY": ""}, clear=False)
        self.environment.start()
        self.loader_patch = patch("api.runtime_config.load_config", return_value=Config())
        self.loader_patch.start()

    async def asyncTearDown(self) -> None:
        self.loader_patch.stop()
        self.environment.stop()
        self.session_patch.stop()
        await self.async_engine.dispose()
        self.sync_engine.dispose()
        self.temp_dir.cleanup()

    def _add_default(self, *, api_key_encrypted: str | None, model_id: str = "default-model") -> None:
        with self.sessions.begin() as session:
            session.add(ModelConfig(
                id="default", tenant_id=None, provider="openrouter", model_id=model_id,
                display_name="Default", model_type="llm", category="chat", enabled=True,
                is_default=True, api_key_encrypted=api_key_encrypted,
                base_url="https://openrouter.ai/api/v1",
            ))

    async def _persist(self, *, model: str = "persisted-model", key: str = "persisted-key") -> None:
        async with self.async_sessions() as db:
            await persist_runtime_config(
                db, provider="openrouter", model=model, api_key=key,
                base_url="https://openrouter.ai/api/v1", enable_thinking=False,
            )

    async def test_default_model_precedes_persisted_runtime(self) -> None:
        self._add_default(api_key_encrypted=encrypt("default-key"))
        await self._persist()
        resolved = resolve_startup_runtime_config()
        self.assertEqual(resolved.agents.defaults.model, "default-model")
        self.assertEqual(resolved.providers.openrouter.api_key, "default-key")

    async def test_persisted_runtime_is_restored_when_no_valid_default_exists(self) -> None:
        await self._persist(model="restart-model", key="restart-key")
        resolved = resolve_startup_runtime_config()
        self.assertEqual(resolved.agents.defaults.model, "restart-model")
        self.assertEqual(resolved.providers.openrouter.api_key, "restart-key")
        self.assertEqual(resolved.providers.openrouter.api_base, "https://openrouter.ai/api/v1")

    async def test_unsupported_default_endpoint_does_not_block_persisted_fallback(self) -> None:
        self._add_default(api_key_encrypted=encrypt("default-key"))
        with self.sessions.begin() as session:
            session.get(ModelConfig, "default").base_url = "https://unapproved.example/v1"
        await self._persist(model="restart-model", key="restart-key")
        resolved = resolve_startup_runtime_config()
        self.assertEqual(resolved.agents.defaults.model, "restart-model")
        self.assertEqual(resolved.providers.openrouter.api_key, "restart-key")

    async def test_environment_is_final_fallback(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "environment-key"}, clear=False):
            resolved = resolve_startup_runtime_config()
        self.assertEqual(resolved.providers.openrouter.api_key, "environment-key")

    async def test_corrupt_persisted_ciphertext_does_not_fall_back_to_environment(self) -> None:
        await self._persist()
        with self.sessions.begin() as session:
            metadata = session.query(SystemConfig).filter_by(config_key=RUNTIME_CONFIG_KEY).one()
            model_id = json.loads(metadata.config_value)["model_config_id"]
            session.get(ModelConfig, model_id).api_key_encrypted = "not-a-fernet-token"
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "must-not-be-used"}, clear=False):
            with self.assertRaisesRegex(RuntimeConfigurationError, "cannot be decrypted"):
                resolve_startup_runtime_config()

    async def test_persistence_keeps_plaintext_out_of_system_config(self) -> None:
        await self._persist(key="super-secret")
        with self.sessions() as session:
            metadata = session.query(SystemConfig).filter_by(config_key=RUNTIME_CONFIG_KEY).one()
            self.assertEqual(metadata.config_type, "json")
            self.assertNotIn("super-secret", metadata.config_value)
            model_id = json.loads(metadata.config_value)["model_config_id"]
            model = session.get(ModelConfig, model_id)
            self.assertNotEqual(model.api_key_encrypted, "super-secret")
            self.assertEqual(decrypt_if_not_empty(model.api_key_encrypted), "super-secret")

    async def test_reapply_reuses_only_its_managed_credential_and_rotates_key(self) -> None:
        await self._persist(model="first-model", key="first-key")
        with self.sessions() as session:
            metadata = session.query(SystemConfig).filter_by(config_key=RUNTIME_CONFIG_KEY).one()
            first_id = json.loads(metadata.config_value)["model_config_id"]

        await self._persist(model="second-model", key="second-key")
        with self.sessions() as session:
            metadata = session.query(SystemConfig).filter_by(config_key=RUNTIME_CONFIG_KEY).one()
            second_id = json.loads(metadata.config_value)["model_config_id"]
            model = session.get(ModelConfig, second_id)
            self.assertEqual(first_id, second_id)
            self.assertEqual((model.model_id, decrypt_if_not_empty(model.api_key_encrypted)), ("second-model", "second-key"))
            self.assertEqual(session.query(ModelConfig).count(), 1)

    async def test_tenant_scoped_metadata_pointer_is_not_modified(self) -> None:
        tenant_ciphertext = encrypt("tenant-key")
        with self.sessions.begin() as session:
            session.add(ModelConfig(
                id="tenant-model", tenant_id="tenant-a", provider="openrouter", model_id="tenant-model",
                display_name="Persisted Runtime Configuration", model_type="llm", category="chat",
                enabled=True, is_default=False, api_key_encrypted=tenant_ciphertext,
            ))
            session.add(SystemConfig(
                config_key=RUNTIME_CONFIG_KEY, config_type="json", is_public=False,
                config_value=json.dumps({
                    "provider": "openrouter", "model": "tenant-model",
                    "baseUrl": "https://openrouter.ai/api/v1", "model_config_id": "tenant-model",
                }),
            ))
        await self._persist(model="global-model", key="global-key")
        with self.sessions() as session:
            tenant = session.get(ModelConfig, "tenant-model")
            metadata = session.query(SystemConfig).filter_by(config_key=RUNTIME_CONFIG_KEY).one()
            replacement_id = json.loads(metadata.config_value)["model_config_id"]
            replacement = session.get(ModelConfig, replacement_id)
            self.assertEqual((tenant.tenant_id, decrypt_if_not_empty(tenant.api_key_encrypted)), ("tenant-a", "tenant-key"))
            self.assertNotEqual(replacement_id, "tenant-model")
            self.assertEqual((replacement.tenant_id, decrypt_if_not_empty(replacement.api_key_encrypted)), (None, "global-key"))

    async def test_missing_referenced_model_fails_closed(self) -> None:
        with self.sessions.begin() as session:
            session.add(SystemConfig(
                config_key=RUNTIME_CONFIG_KEY, config_type="json", is_public=False,
                config_value=json.dumps({
                    "provider": "openrouter", "model": "missing-model",
                    "baseUrl": "https://openrouter.ai/api/v1", "model_config_id": "missing",
                }),
            ))
        with self.assertRaisesRegex(RuntimeConfigurationError, "credential is unavailable"):
            resolve_startup_runtime_config()

    async def test_missing_persisted_credential_fails_closed(self) -> None:
        await self._persist()
        with self.sessions.begin() as session:
            metadata = session.query(SystemConfig).filter_by(config_key=RUNTIME_CONFIG_KEY).one()
            model_id = json.loads(metadata.config_value)["model_config_id"]
            session.get(ModelConfig, model_id).api_key_encrypted = None
        with self.assertRaisesRegex(RuntimeConfigurationError, "credential is unavailable"):
            resolve_startup_runtime_config()

    async def test_failed_persistence_rolls_back_without_storing_plaintext(self) -> None:
        async with self.async_sessions() as db:
            with patch.object(db, "commit", new=AsyncMock(side_effect=SQLAlchemyError("commit failed"))):
                with self.assertRaisesRegex(RuntimeConfigurationError, "could not be persisted"):
                    await persist_runtime_config(
                        db, provider="openrouter", model="failed-model", api_key="failed-secret",
                        base_url="https://openrouter.ai/api/v1", enable_thinking=False,
                    )
        with self.sessions() as session:
            self.assertIsNone(session.query(SystemConfig).filter_by(config_key=RUNTIME_CONFIG_KEY).one_or_none())
            self.assertEqual(session.query(ModelConfig).count(), 0)


if __name__ == "__main__":
    unittest.main()
