"""A6 M2 end-to-end validation for database initialization and seed data."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ADMIN_PASSWORD = "A6-only-validation-password"


class SeedInitializationTests(unittest.TestCase):
    """Validate the real seed command against a disposable SQLite database."""

    @staticmethod
    def _run_seed(database_path: Path) -> dict[str, int]:
        environment = os.environ.copy()
        environment["ADMIN_DATABASE_URL"] = (
            f"sqlite+aiosqlite:///{database_path.as_posix()}"
        )
        environment["ADMIN_DEFAULT_PASSWORD"] = TEST_ADMIN_PASSWORD

        completed = subprocess.run(
            [sys.executable, "-m", "admin.seeds"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "Seed command failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )
        return json.loads(completed.stdout)

    @staticmethod
    def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
        tables = {
            "tenants": "tenants",
            "knowledge_permissions": "permissions",
            "admin_roles": "roles",
            "admin_users": "users",
            "agent_profiles": "agent_profiles",
            "performance_rows": "agent_performance_metrics",
            "performance_targets": "performance_targets",
            "policies": "agent_policies",
            "attribution_rows": "agent_attribution",
            "competitions": "competitions",
            "competition_entries": "competition_entries",
            "planning_configs": "system_configs",
        }
        return {
            summary_key: connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            for summary_key, table_name in tables.items()
        }

    def test_seed_command_initializes_secure_idempotent_database(self) -> None:
        with tempfile.TemporaryDirectory(prefix="insurance-a6-") as directory:
            database_path = Path(directory) / "admin.db"

            first_summary = self._run_seed(database_path)
            with closing(sqlite3.connect(database_path)) as connection:
                first_counts = self._table_counts(connection)

            second_summary = self._run_seed(database_path)
            with closing(sqlite3.connect(database_path)) as connection:
                second_counts = self._table_counts(connection)
                admin_row = connection.execute(
                    "SELECT id, password_hash, is_superadmin, is_active "
                    "FROM users WHERE username = 'admin'"
                ).fetchone()
                admin_role = connection.execute(
                    "SELECT roles.name FROM roles "
                    "JOIN user_roles ON user_roles.role_id = roles.id "
                    "WHERE user_roles.user_id = ?",
                    (admin_row[0],),
                ).fetchall()
                planning_value = connection.execute(
                    "SELECT config_value FROM system_configs "
                    "WHERE config_key = 'planning.action_templates'"
                ).fetchone()[0]
                fts_table = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'knowledge_fts'"
                ).fetchone()
                foreign_key_violations = connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()

        self.assertEqual(first_summary, first_counts)
        self.assertEqual(second_summary, second_counts)
        self.assertEqual(second_counts, first_counts)
        self.assertTrue(all(count > 0 for count in second_counts.values()))

        self.assertIsNotNone(admin_row)
        self.assertNotEqual(admin_row[1], TEST_ADMIN_PASSWORD)
        self.assertTrue(admin_row[1].startswith("$2"))
        self.assertEqual(admin_row[2:], (1, 1))
        self.assertEqual(admin_role, [("super_admin",)])

        templates = json.loads(planning_value)
        self.assertTrue(templates["hkd_actions"])
        self.assertTrue(templates["non_hkd_actions"])
        self.assertIsNotNone(fts_table)
        self.assertEqual(foreign_key_violations, [])


if __name__ == "__main__":
    unittest.main()
