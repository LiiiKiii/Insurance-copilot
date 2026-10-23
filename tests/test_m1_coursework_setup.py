"""Isolated setup checks for the explicitly opted-in M1 coursework tenant."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from admin.db import Base
from admin.dependencies import has_admin_access
from admin.models.tenant import Tenant
from admin.models.user import Permission, Role, User, role_permissions, user_roles
from admin.services.auth_service import verify_password
from scripts import setup_m1_coursework_demo as setup


class DemoSetupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.folder.name, 'demo.db').as_posix()}"
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(
                sync, tables=[Tenant.__table__, User.__table__, Role.__table__,
                              Permission.__table__, user_roles, role_permissions],
            ))

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.folder.cleanup()

    async def test_creates_authenticatable_agent_and_repeat_preserves_password(self) -> None:
        async with self.sessions() as session:
            first = await setup.setup_coursework_agent(session, "AGT00690", "demo-test-password-1")
        self.assertEqual(first["scenario_id"], "SCN-AGT00690")
        async with self.sessions() as session:
            repeated = await setup.setup_coursework_agent(session, "AGT00690", None)
        self.assertEqual(first, repeated)
        async with self.sessions() as session:
            self.assertEqual(
                await setup.setup_coursework_agent(session, "AGT00690", "changed-password"),
                first,
            )
        async with self.sessions() as session:
            tenants = (await session.scalars(select(Tenant))).all()
            users = (await session.scalars(select(User).options(selectinload(User.roles)))).all()
            roles = (await session.scalars(select(Role))).all()
        self.assertEqual(len(tenants), 1)
        self.assertEqual((len(users), len(roles)), (1, 1))
        self.assertEqual((tenants[0].slug, tenants[0].enabled), ("coursework-demo", True))
        self.assertEqual(users[0].tenant_id, first["tenant_id"])
        self.assertFalse(users[0].is_superadmin)
        self.assertTrue(has_admin_access(users[0]))
        self.assertTrue(verify_password("demo-test-password-1", users[0].password_hash))
        self.assertFalse(verify_password("changed-password", users[0].password_hash))

    async def test_rejects_other_tenant_without_modifying_it(self) -> None:
        async with self.sessions() as session:
            session.add(Tenant(id="foreign", slug="real-tenant", name="Real Tenant"))
            await session.commit()
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "non-demo tenant"):
                await setup.setup_coursework_agent(session, "AGT00690", "demo-test-password-1")
        async with self.sessions() as session:
            self.assertEqual((await session.scalars(select(Tenant))).one().slug, "real-tenant")
            self.assertEqual((await session.scalars(select(User))).all(), [])

    async def test_rejects_invalid_scenario_and_missing_password(self) -> None:
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "unique M2 v3 scenario"):
                await setup.setup_coursework_agent(session, "not-an-agent", "demo-test-password-1")
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "M1_COURSEWORK_DEMO_PASSWORD"):
                await setup.setup_coursework_agent(session, "AGT00690", None)
        async with self.sessions() as session:
            self.assertEqual((await session.scalars(select(Tenant))).all(), [])

    async def test_disabled_existing_user_is_not_reenabled(self) -> None:
        async with self.sessions() as session:
            session.add(Tenant(id="demo", slug="coursework-demo", name="Demo"))
            session.add(User(id="disabled", tenant_id="demo", username="AGT00690",
                             email="disabled@example.invalid", password_hash="unchanged",
                             is_active=False, is_superadmin=False))
            await session.commit()
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "disabled or privileged"):
                await setup.setup_coursework_agent(session, "AGT00690", "replacement-password")
        async with self.sessions() as session:
            user = (await session.scalars(select(User))).one()
        self.assertEqual(user.password_hash, "unchanged")
        self.assertFalse(user.is_active)

    async def test_existing_privileged_role_is_rejected(self) -> None:
        async with self.sessions() as session:
            session.add(Tenant(id="demo", slug="coursework-demo", name="Demo"))
            session.add(User(id="agent", tenant_id="demo", username="AGT00690",
                             email="agent@example.invalid", password_hash="unchanged"))
            session.add(Role(id="admin-role", tenant_id="demo", name="admin"))
            await session.flush()
            await session.execute(insert(user_roles).values(user_id="agent", role_id="admin-role"))
            await session.commit()
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "privileged or foreign roles"):
                await setup.setup_coursework_agent(session, "AGT00690", None)

    async def test_existing_readonly_role_with_permissions_is_rejected(self) -> None:
        async with self.sessions() as session:
            session.add(Tenant(id="demo", slug="coursework-demo", name="Demo"))
            session.add(Role(id="readonly-role", tenant_id="demo", name="readonly"))
            session.add(Permission(id="permission", resource="knowledge_bases", action="write"))
            await session.flush()
            await session.execute(insert(role_permissions).values(
                role_id="readonly-role", permission_id="permission",
            ))
            await session.commit()
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "resource permissions"):
                await setup.setup_coursework_agent(session, "AGT00690", "demo-test-password-1")
        async with self.sessions() as session:
            self.assertEqual((await session.scalars(select(User))).all(), [])

    async def test_unmigrated_schema_fails_with_migration_instruction(self) -> None:
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "alembic upgrade head"):
                await setup.check_migrated_schema(session)


class DemoDatabaseGuardTests(unittest.TestCase):
    def test_requires_exact_dedicated_sqlite_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            demo_db = Path(folder) / "demo.db"
            demo_db.touch()
            url = f"sqlite+aiosqlite:///{demo_db.as_posix()}"
            with patch.object(setup, "DEMO_DB", demo_db), patch.object(setup, "ROOT", Path(folder)):
                self.assertEqual(setup.validate_demo_database_url(url), demo_db)
                for unsafe in (None, "sqlite+aiosqlite:///shared.db", "postgresql://host/db"):
                    with self.subTest(url=unsafe), self.assertRaises(RuntimeError):
                        setup.validate_demo_database_url(unsafe)


if __name__ == "__main__":
    unittest.main()
