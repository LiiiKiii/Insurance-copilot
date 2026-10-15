"""Offline behavior tests for the global generic configuration bridge."""
from __future__ import annotations

from contextlib import contextmanager
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin.config_bridge import (
    GenericConfigurationAmbiguityError,
    SecretConfigurationKeyError,
    get,
    get_bool,
    get_disclaimer,
    get_float,
    get_forbidden_keywords,
    get_int,
    get_json,
    get_model_for_category,
    get_str,
    invalidate,
)
from admin.db import Base
from admin.models.config import SystemConfig
from admin.models.model_config import ModelConfig


class GenericConfigBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        invalidate()
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
        invalidate()
        self.bridge_db.stop()
        self.engine.dispose()

    @contextmanager
    def _get_sync_db(self):
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _add(
        self,
        key: str,
        value: str,
        config_type: str = "string",
        tenant_id: str | None = None,
    ) -> None:
        with self.session_factory.begin() as session:
            session.add(
                SystemConfig(
                    tenant_id=tenant_id,
                    config_key=key,
                    config_value=value,
                    config_type=config_type,
                )
            )

    def test_global_lookup_ignores_tenant_value_and_missing_uses_caller_default(self) -> None:
        self._add("ui.title", "Global")
        self._add("ui.title", "Tenant A", tenant_id="tenant-a")

        self.assertEqual(get("ui.title", "fallback"), "Global")
        self.assertEqual(get("missing.key", "first"), "first")
        self.assertEqual(get("missing.key", "second"), "second")

    def test_type_conversions_and_malformed_values_return_defaults(self) -> None:
        self._add("limit", "12", "int")
        self._add("ratio", "1.25", "float")
        self._add("enabled", "YeS", "bool")
        self._add("payload", '{"ready": true}', "json")
        self._add("bad.int", "twelve", "int")
        self._add("bad.bool", "sometimes", "bool")
        self._add("bad.json", "{", "json")

        self.assertEqual(get("limit", 0), 12)
        self.assertEqual(get("ratio", 0.0), 1.25)
        self.assertTrue(get("enabled", False))
        self.assertEqual(get("payload", None), {"ready": True})
        self.assertEqual(get("bad.int", 7), 7)
        self.assertTrue(get("bad.bool", True))
        self.assertEqual(get("bad.json", {"safe": True}), {"safe": True})
        self.assertEqual(get_int("limit"), 12)
        self.assertEqual(get_float("ratio"), 1.25)
        self.assertTrue(get_bool("enabled"))
        self.assertEqual(get_json("payload"), {"ready": True})
        self.assertEqual(get_str("limit"), "12")

    def test_cache_invalidation_and_ttl_expiry(self) -> None:
        self._add("cached", "one")
        calls = 0

        @contextmanager
        def counted_db():
            nonlocal calls
            calls += 1
            with self._get_sync_db() as session:
                yield session

        with patch("admin.db.get_sync_db", counted_db), patch(
            "admin.config_bridge.time.monotonic", side_effect=[100.0, 101.0, 131.0]
        ):
            self.assertEqual(get("cached", ttl=30), "one")
            self.assertEqual(get("cached", ttl=30), "one")
            self.assertEqual(get("cached", ttl=30), "one")
        self.assertEqual(calls, 2)

        invalidate("cached")
        self.assertEqual(get("cached"), "one")
        with self.session_factory.begin() as session:
            row = session.query(SystemConfig).filter_by(config_key="cached").one()
            row.config_value = "two"
        self.assertEqual(get("cached"), "one")
        invalidate("cached")
        self.assertEqual(get("cached"), "two")
        invalidate()
        self.assertEqual(get("cached"), "two")

    def test_database_failures_return_defaults_and_are_not_cached(self) -> None:
        invalidate()
        with patch(
            "admin.db.get_sync_db", side_effect=OperationalError("select", {}, None)
        ) as unavailable:
            self.assertEqual(get("missing.db", "first"), "first")
            self.assertEqual(get("missing.db", "second"), "second")
        self.assertEqual(unavailable.call_count, 2)

    def test_duplicate_global_rows_are_rejected_defensively(self) -> None:
        fake_session = MagicMock()
        fake_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            SimpleNamespace(config_value="one", config_type="string"),
            SimpleNamespace(config_value="two", config_type="string"),
        ]

        @contextmanager
        def duplicate_db():
            yield fake_session

        with patch("admin.db.get_sync_db", duplicate_db):
            with self.assertRaises(GenericConfigurationAmbiguityError):
                get("legacy.duplicate", ttl=0)

    def test_secret_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "encrypted credential"):
            SystemConfig(config_key="provider.api_key", config_value="plaintext")
        with self.assertRaises(SecretConfigurationKeyError):
            get("provider.api_key")

    def test_compliance_helpers_have_conservative_defaults_and_validate_values(self) -> None:
        self.assertEqual(get_forbidden_keywords(), ["guarantee", "guaranteed", "must pay"])
        self.assertIn("internal reference", get_disclaimer())

        self._add(
            "compliance.forbidden_keywords",
            '["Guarantee", "zero risk", "ZERO RISK"]',
            "json",
        )
        self._add("compliance.disclaimer", "Review with a licensed adviser.")
        invalidate("compliance.forbidden_keywords")
        invalidate("compliance.disclaimer")
        self.assertEqual(get_forbidden_keywords(), ["Guarantee", "zero risk"])
        self.assertEqual(get_disclaimer(), "Review with a licensed adviser.")

    def test_model_category_lookup_is_global_only(self) -> None:
        with self.session_factory.begin() as session:
            session.add_all(
                [
                    ModelConfig(
                        id="global-embedding",
                        tenant_id=None,
                        provider="openai",
                        model_id="embedding-global",
                        display_name="Global embedding",
                        model_type="embedding",
                        category="embedding",
                        enabled=True,
                        is_default=True,
                    ),
                    ModelConfig(
                        id="tenant-embedding",
                        tenant_id="tenant-a",
                        provider="openai",
                        model_id="embedding-tenant",
                        display_name="Tenant embedding",
                        model_type="embedding",
                        category="embedding",
                        enabled=True,
                        is_default=True,
                    ),
                ]
            )

        with patch.dict(os.environ, {}, clear=False):
            result = get_model_for_category("embedding")
        self.assertEqual(result["id"], "global-embedding")
        self.assertEqual(result["model_id"], "embedding-global")


if __name__ == "__main__":
    unittest.main()
