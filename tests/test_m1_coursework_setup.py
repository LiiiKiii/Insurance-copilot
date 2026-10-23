"""Read-only M1 setup checks against seeded default-tenant identities."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.db import Base
from admin.models.tenant import Tenant
from admin.models.user import Role, User, user_roles
from admin.seeds import DEFAULT_TENANT_ID
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
                sync, tables=[Tenant.__table__, User.__table__, Role.__table__, user_roles],
            ))

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.folder.cleanup()

    async def seed_identity(self, *, tenant_id=DEFAULT_TENANT_ID, slug="default",
                            enabled=True, active=True, superadmin=False,
                            role="agent_manager", agent_id="AGT00690") -> None:
        async with self.sessions() as session:
            session.add(Tenant(id=tenant_id, slug=slug, name="Default", enabled=enabled))
            session.add(User(id="agent", tenant_id=tenant_id, username=agent_id,
                             email="agent@example.test", password_hash="original-hash",
                             is_active=active, is_superadmin=superadmin))
            session.add(Role(id="role", tenant_id=tenant_id, name=role))
            await session.flush()
            await session.execute(insert(user_roles).values(user_id="agent", role_id="role"))
            await session.commit()

    async def test_repeated_validation_does_not_change_password_roles_or_counts(self) -> None:
        await self.seed_identity()
        async with self.sessions() as session:
            first = await setup.setup_coursework_agent(session, "AGT00690")
            second = await setup.setup_coursework_agent(session, "AGT00690")
        self.assertEqual(first, second)
        self.assertEqual(first, {"tenant_id": DEFAULT_TENANT_ID,
                                 "agent_id": "AGT00690", "scenario_id": "SCN-AGT00690"})
        async with self.sessions() as session:
            self.assertEqual((await session.scalars(select(Tenant))).one().slug, "default")
            self.assertEqual((await session.scalars(select(User))).one().password_hash, "original-hash")
            self.assertEqual((await session.scalars(select(Role))).one().name, "agent_manager")
            self.assertEqual(len((await session.execute(select(user_roles))).all()), 1)

    async def test_missing_seed_fails_without_creating_records(self) -> None:
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "run admin.seeds"):
                await setup.setup_coursework_agent(session, "AGT00690")
            self.assertEqual((await session.scalars(select(Tenant))).all(), [])

    async def test_missing_agent_fails(self) -> None:
        await self.seed_identity(agent_id="AGT00770")
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "run admin.seeds"):
                await setup.setup_coursework_agent(session, "AGT00690")

    async def test_invalid_scenario_fails(self) -> None:
        await self.seed_identity()
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "unique M2 v3 scenario"):
                await setup.setup_coursework_agent(session, "not-an-agent")

    async def test_disabled_or_wrong_default_tenant_fails(self) -> None:
        for kwargs in ({"enabled": False}, {"tenant_id": "wrong-id"}, {"slug": "other"}):
            with self.subTest(kwargs=kwargs):
                await self.seed_identity(**kwargs)
                async with self.sessions() as session:
                    with self.assertRaises(RuntimeError):
                        await setup.setup_coursework_agent(session, "AGT00690")
                    for table in (user_roles, User.__table__, Role.__table__, Tenant.__table__):
                        await session.execute(table.delete())
                    await session.commit()

    async def test_disabled_privileged_or_wrong_role_fails_without_escalation(self) -> None:
        for kwargs in ({"active": False}, {"superadmin": True}, {"role": "admin"}):
            with self.subTest(kwargs=kwargs):
                await self.seed_identity(**kwargs)
                async with self.sessions() as session:
                    with self.assertRaises(RuntimeError):
                        await setup.setup_coursework_agent(session, "AGT00690")
                    self.assertEqual((await session.scalars(select(User))).one().password_hash,
                                     "original-hash")
                    for table in (user_roles, User.__table__, Role.__table__, Tenant.__table__):
                        await session.execute(table.delete())
                    await session.commit()

    async def test_cross_tenant_duplicate_login_fails(self) -> None:
        await self.seed_identity()
        async with self.sessions() as session:
            session.add(Tenant(id="other", slug="other", name="Other"))
            session.add(User(id="other-user", tenant_id="other", username="AGT00690",
                             email="other@example.test", password_hash="untouched"))
            await session.commit()
        async with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, "ambiguous"):
                await setup.setup_coursework_agent(session, "AGT00690")

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
