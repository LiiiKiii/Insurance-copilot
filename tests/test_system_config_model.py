"""Offline schema tests for the plaintext generic configuration model."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from admin.db import Base
from admin.models.config import SystemConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"

try:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
except ModuleNotFoundError:
    MigrationContext = None
    Operations = None


class SystemConfigModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_model_is_registered_and_defaults_follow_contract(self) -> None:
        self.assertIn("system_configs", Base.metadata.tables)
        with self.session_factory.begin() as session:
            row = SystemConfig(config_key="ui.banner", config_value="Welcome")
            session.add(row)

        with self.session_factory() as session:
            row = session.query(SystemConfig).one()
            self.assertEqual(len(row.id), 36)
            self.assertIsNone(row.tenant_id)
            self.assertEqual(row.config_type, "string")
            self.assertEqual(row.description, "")
            self.assertFalse(row.is_public)
            self.assertIsNotNone(row.created_at)
            self.assertIsNotNone(row.updated_at)

    def test_global_and_tenant_uniqueness_are_enforced(self) -> None:
        with self.session_factory.begin() as session:
            session.add(SystemConfig(config_key="shared.key", config_value="global"))
            session.add(
                SystemConfig(
                    tenant_id="tenant-a",
                    config_key="shared.key",
                    config_value="tenant-a",
                )
            )

        with self.assertRaises(IntegrityError):
            with self.session_factory.begin() as session:
                session.add(SystemConfig(config_key="shared.key", config_value="duplicate-global"))

        with self.assertRaises(IntegrityError):
            with self.session_factory.begin() as session:
                session.add(
                    SystemConfig(
                        tenant_id="tenant-a",
                        config_key="shared.key",
                        config_value="duplicate-tenant",
                    )
                )

    def test_secret_like_keys_and_unknown_types_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "encrypted credential"):
            SystemConfig(config_key="integration.api_key", config_value="not-allowed")
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            SystemConfig(config_key="ui.banner", config_value="Welcome", config_type="xml")

    @unittest.skipUnless(
        MigrationContext is not None and Operations is not None,
        "Alembic is unavailable in the active virtual environment.",
    )
    def test_migration_creates_sqlite_partial_global_index(self) -> None:
        engine = create_engine("sqlite://")
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "alembic"
            / "versions"
            / "0002_system_configs.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0002", migration_path)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    migration.upgrade()

                tables = inspect(connection).get_table_names()
                self.assertIn("system_configs", tables)
                indexes = inspect(connection).get_indexes("system_configs")
                self.assertIn("uq_system_configs_global_key", {index["name"] for index in indexes})
                connection.execute(
                    text(
                        "INSERT INTO system_configs "
                        "(id, config_key, config_value, config_type, description, is_public, "
                        "created_at, updated_at) VALUES "
                        "('one', 'global.key', 'one', 'string', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        text(
                            "INSERT INTO system_configs "
                            "(id, config_key, config_value, config_type, description, is_public, "
                            "created_at, updated_at) VALUES "
                            "('two', 'global.key', 'two', 'string', '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        )
                    )
        finally:
            engine.dispose()


@unittest.skipUnless(
    MigrationContext is not None and Operations is not None,
    "Alembic is unavailable in the active virtual environment.",
)
class SystemConfigPartialIndexValidationTests(unittest.TestCase):
    """Validate inspector representations without requiring PostgreSQL."""

    @classmethod
    def setUpClass(cls) -> None:
        migration_path = PROJECT_ROOT / "alembic" / "versions" / "0002_system_configs.py"
        spec = importlib.util.spec_from_file_location("migration_0002_predicates", migration_path)
        assert spec is not None and spec.loader is not None
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    @staticmethod
    def _index(predicate: str, *, unique: bool = True) -> dict:
        return {
            "name": "uq_system_configs_global_key",
            "unique": unique,
            "column_names": ["config_key"],
            "dialect_options": {"postgresql_where": text(predicate)},
        }

    def test_unparenthesized_postgresql_predicate_is_valid(self) -> None:
        self.assertTrue(self.migration._is_global_index(self._index("tenant_id IS NULL")))

    def test_parenthesized_postgresql_predicate_is_valid(self) -> None:
        self.assertTrue(self.migration._is_global_index(self._index("(tenant_id IS NULL)")))

    def test_nested_parentheses_in_postgresql_predicate_are_valid(self) -> None:
        self.assertTrue(self.migration._is_global_index(self._index("(((tenant_id IS NULL)))")))

    def test_whitespace_and_quoted_identifier_predicate_is_valid(self) -> None:
        self.assertTrue(
            self.migration._is_global_index(self._index(' ( ( "tenant_id"  IS\t NULL ) ) '))
        )

    def test_incorrect_predicates_are_rejected(self) -> None:
        for predicate in ("tenant_id IS NOT NULL", "tenant_id IS NULL OR is_public"):
            with self.subTest(predicate=predicate):
                self.assertFalse(self.migration._is_global_index(self._index(predicate)))

    def test_non_unique_index_with_correct_predicate_is_rejected(self) -> None:
        self.assertFalse(self.migration._is_global_index(self._index("tenant_id IS NULL", unique=False)))


@unittest.skipUnless(
    MigrationContext is not None and Operations is not None,
    "Alembic is unavailable in the active virtual environment.",
)
class SystemConfigMigrationChainTests(unittest.TestCase):
    """Exercise the real CLI chain with an explicitly disposable SQLite URL."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "migration.db"

    def tearDown(self) -> None:
        self.directory.cleanup()

    @property
    def database_url(self) -> str:
        return "sqlite+aiosqlite:///" + self.database_path.as_posix()

    @property
    def sync_database_url(self) -> str:
        return "sqlite:///" + self.database_path.as_posix()

    def _run_alembic(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["ADMIN_DATABASE_URL"] = self.database_url
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *arguments],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def _engine(self):
        return create_engine(self.sync_database_url)

    def _upgrade(self, revision: str) -> None:
        result = self._run_alembic("upgrade", revision)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _assert_global_index(self) -> None:
        engine = self._engine()
        try:
            with engine.connect() as connection:
                indexes = inspect(connection).get_indexes("system_configs")
                matching = [
                    index for index in indexes if index["name"] == "uq_system_configs_global_key"
                ]
                self.assertEqual(len(matching), 1)
                self.assertTrue(matching[0]["unique"])
                sql = connection.execute(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type = 'index' AND name = 'uq_system_configs_global_key'"
                    )
                ).scalar_one()
                self.assertIn("WHERE tenant_id IS NULL", sql)
        finally:
            engine.dispose()

    def _insert(self, identifier: str, key: str, tenant_id: str | None = None) -> None:
        engine = self._engine()
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO system_configs "
                        "(id, tenant_id, config_key, config_value, config_type, description, "
                        "is_public, created_at, updated_at) VALUES "
                        "(:id, :tenant_id, :config_key, 'value', 'string', '', 0, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {"id": identifier, "tenant_id": tenant_id, "config_key": key},
                )
        finally:
            engine.dispose()

    def test_fresh_chain_succeeds_and_enforces_uniqueness(self) -> None:
        self._upgrade("0001")
        self._upgrade("0002")
        self._assert_global_index()

        self._insert("global-one", "global.one")
        self._insert("global-two", "global.two")
        self._insert("tenant-a", "shared.key", "tenant-a")
        self._insert("tenant-b", "shared.key", "tenant-b")

        with self.assertRaises(IntegrityError):
            self._insert("duplicate-global", "global.one")
        with self.assertRaises(IntegrityError):
            self._insert("duplicate-tenant", "shared.key", "tenant-a")

        engine = self._engine()
        try:
            tables = inspect(engine).get_table_names()
            self.assertIn("tenants", tables)
            self.assertIn("model_configs", tables)
            self.assertIn("system_configs", tables)
        finally:
            engine.dispose()

    def test_historical_0001_without_table_is_upgraded(self) -> None:
        self._upgrade("0001")
        engine = self._engine()
        try:
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE system_configs"))
        finally:
            engine.dispose()

        self._upgrade("0002")
        self._assert_global_index()
        self._insert("created-by-0002", "historical.key")

    def test_precreated_compatible_table_keeps_data_and_adds_missing_index(self) -> None:
        self._upgrade("0001")
        self._insert("retained", "retained.key")
        engine = self._engine()
        try:
            with engine.begin() as connection:
                connection.execute(text("DROP INDEX uq_system_configs_global_key"))
        finally:
            engine.dispose()

        self._upgrade("0002")
        self._assert_global_index()
        engine = self._engine()
        try:
            with engine.connect() as connection:
                retained = connection.execute(
                    text("SELECT config_value FROM system_configs WHERE id = 'retained'")
                ).scalar_one()
                self.assertEqual(retained, "value")
        finally:
            engine.dispose()

    def test_incompatible_preexisting_table_is_rejected_without_data_loss(self) -> None:
        engine = self._engine()
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("CREATE TABLE system_configs (id VARCHAR(36) PRIMARY KEY, retained TEXT NOT NULL)")
                )
                connection.execute(text("INSERT INTO system_configs (id, retained) VALUES ('keep', 'yes')"))
        finally:
            engine.dispose()

        self._upgrade("0001")
        result = self._run_alembic("upgrade", "0002")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Incompatible system_configs schema", result.stdout + result.stderr)

        engine = self._engine()
        try:
            with engine.connect() as connection:
                self.assertEqual(
                    connection.execute(text("SELECT retained FROM system_configs WHERE id = 'keep'")).scalar_one(),
                    "yes",
                )
        finally:
            engine.dispose()

    def test_downgrade_is_safely_blocked_without_removing_tables(self) -> None:
        self._upgrade("0001")
        self._upgrade("0002")
        result = self._run_alembic("downgrade", "0001")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("system_configs provenance is ambiguous", result.stdout + result.stderr)

        engine = self._engine()
        try:
            tables = inspect(engine).get_table_names()
            self.assertIn("system_configs", tables)
            self.assertIn("tenants", tables)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
