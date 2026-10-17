"""Offline security and contract tests for the default model bridge."""

from __future__ import annotations

import asyncio
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin.config_bridge import (
    DefaultModelConfigurationAmbiguityError,
    DefaultModelConfigurationError,
    get_default_model_config,
)
from admin.models.model_config import ModelConfig
from admin.models.tenant import Tenant  # noqa: F401 -- resolves model foreign keys.
from admin.db import Base
from admin.services.crypto_service import encrypt


class ConfigBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        for name in (
            "ADMIN_ENCRYPTION_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
        ):
            os.environ.pop(name, None)

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self.bridge_db = patch("admin.db.get_sync_db", self._get_sync_db)
        self.bridge_db.start()

    def tearDown(self) -> None:
        self.bridge_db.stop()
        self.engine.dispose()
        self.environment.stop()

    @contextmanager
    def _get_sync_db(self):
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def _add_model(self, **overrides: object) -> ModelConfig:
        values: dict[str, object] = {
            "id": "global-default",
            "tenant_id": None,
            "provider": "openrouter",
            "model_id": "test-model",
            "display_name": "Test Model",
            "model_type": "llm",
            "api_key_encrypted": None,
            "base_url": "https://provider.invalid/v1",
            "max_tokens": 2048,
            "temperature": 0.25,
            "enabled": True,
            "is_default": True,
        }
        values.update(overrides)
        row = ModelConfig(**values)
        with self.session_factory.begin() as session:
            session.add(row)
        return row

    def _configure_encryption(self) -> str:
        key = Fernet.generate_key().decode("ascii")
        os.environ["ADMIN_ENCRYPTION_KEY"] = key
        return key

    def test_valid_global_encrypted_configuration_preserves_contract(self) -> None:
        self._configure_encryption()
        self._add_model(api_key_encrypted=encrypt("stored-key"))

        result = get_default_model_config()

        self.assertEqual(
            result,
            {
                "id": "global-default",
                "provider": "openrouter",
                "model_id": "test-model",
                "display_name": "Test Model",
                "api_key": "stored-key",
                "base_url": "https://provider.invalid/v1",
                "max_tokens": 2048,
                "temperature": 0.25,
            },
        )

    def test_none_ciphertext_uses_existing_environment_fallback(self) -> None:
        self._add_model(api_key_encrypted=None)
        os.environ["OPENROUTER_API_KEY"] = "environment-key"
        os.environ["ANTHROPIC_API_KEY"] = "lower-priority-key"

        result = get_default_model_config()

        self.assertEqual(result["api_key"], "environment-key")

    def test_empty_ciphertext_uses_existing_environment_fallback(self) -> None:
        self._add_model(api_key_encrypted="")
        os.environ["OPENROUTER_API_KEY"] = "environment-key"

        result = get_default_model_config()

        self.assertEqual(result["api_key"], "environment-key")

    def test_no_eligible_global_default_returns_none(self) -> None:
        self._add_model(id="disabled", enabled=False)
        self._add_model(id="embedding", model_type="embedding", is_default=True)
        self._add_model(id="tenant-only", tenant_id="tenant-a")

        self.assertIsNone(get_default_model_config())

    def test_invalid_ciphertext_fails_closed_without_environment_fallback(self) -> None:
        ciphertext = "not-a-valid-fernet-token"
        self._add_model(api_key_encrypted=ciphertext)
        os.environ["OPENROUTER_API_KEY"] = "must-not-be-used"

        with self.assertRaises(DefaultModelConfigurationError) as error:
            get_default_model_config()

        self.assertNotIn(ciphertext, str(error.exception))
        self.assertNotIn("must-not-be-used", str(error.exception))

    def test_wrong_or_missing_encryption_key_fails_closed(self) -> None:
        original_key = self._configure_encryption()
        ciphertext = encrypt("stored-key")
        self._add_model(api_key_encrypted=ciphertext)

        os.environ["ADMIN_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        with self.assertRaises(DefaultModelConfigurationError) as wrong_key:
            get_default_model_config()
        self.assertNotIn(ciphertext, str(wrong_key.exception))
        self.assertNotIn(original_key, str(wrong_key.exception))

        os.environ.pop("ADMIN_ENCRYPTION_KEY")
        with self.assertRaises(DefaultModelConfigurationError):
            get_default_model_config()

    def test_duplicate_global_defaults_are_rejected(self) -> None:
        self._add_model(id="global-a")
        self._add_model(id="global-b")

        with self.assertRaises(DefaultModelConfigurationAmbiguityError):
            get_default_model_config()

    def test_tenant_default_never_leaks_to_global_caller(self) -> None:
        self._add_model(id="tenant-default", tenant_id="tenant-a")
        os.environ["OPENROUTER_API_KEY"] = "environment-key"

        self.assertIsNone(get_default_model_config())

    def test_database_failure_preserves_existing_none_fallback(self) -> None:
        self.bridge_db.stop()
        with patch("admin.db.get_sync_db", side_effect=OperationalError("select", {}, None)):
            self.assertIsNone(get_default_model_config())

    def test_briefing_generator_retains_none_configuration_contract(self) -> None:
        from api.briefing.llm_generator import generate_briefing

        with patch("admin.config_bridge.get_default_model_config", return_value=None):
            result = asyncio.run(generate_briefing([]))

        self.assertEqual(result["model_id"], None)
        self.assertEqual(result["model_display_name"], "fallback-rule-based")
        self.assertIn("summary_markdown", result)


if __name__ == "__main__":
    unittest.main()
