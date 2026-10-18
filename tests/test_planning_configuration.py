"""A4 M4 tests for action-plan configuration seed data."""

from __future__ import annotations

import json
import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.models.config import SystemConfig
from admin.seeds import ACTION_TEMPLATES_CONFIG_KEY, _seed_planning_configuration


class PlanningConfigurationSeedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(SystemConfig.__table__.create)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_seed_creates_private_english_action_templates(self) -> None:
        async with self.sessions() as session:
            self.assertEqual(await _seed_planning_configuration(session), 1)
            await session.commit()
            row = await session.scalar(
                select(SystemConfig).where(
                    SystemConfig.config_key == ACTION_TEMPLATES_CONFIG_KEY
                )
            )

        self.assertIsNotNone(row)
        self.assertEqual(row.config_type, "json")
        self.assertFalse(row.is_public)
        templates = json.loads(row.config_value)
        self.assertTrue(templates["hkd_actions"])
        self.assertTrue(templates["non_hkd_actions"])
        self.assertTrue(
            all(
                action["template"].isascii()
                for group in templates.values()
                for action in group
            )
        )

    async def test_seed_rerun_preserves_admin_changes(self) -> None:
        customised = json.dumps(
            {
                "hkd_actions": [{"priority": "P0", "template": "Custom action"}],
                "non_hkd_actions": [{"priority": "P1", "template": "Custom case action"}],
            }
        )
        async with self.sessions() as session:
            session.add(
                SystemConfig(
                    config_key=ACTION_TEMPLATES_CONFIG_KEY,
                    config_value=customised,
                    config_type="json",
                )
            )
            await session.commit()
            self.assertEqual(await _seed_planning_configuration(session), 1)
            await session.commit()
            row = await session.scalar(
                select(SystemConfig).where(
                    SystemConfig.config_key == ACTION_TEMPLATES_CONFIG_KEY
                )
            )

        self.assertEqual(row.config_value, customised)


if __name__ == "__main__":
    unittest.main()
