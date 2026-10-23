"""Validate one seeded default-tenant agent in the dedicated local demo DB."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / "data/demo/m1_coursework.db"
DATASET = ROOT / "data/evaluation/m2_candidate_scenarios.json"
ROSTER = ROOT / "data/mock/agents.json"


def validate_demo_database_url(value: str | None) -> Path:
    """Refuse default, shared, remote, and redirected database targets."""
    if not value:
        raise RuntimeError("Set ADMIN_DATABASE_URL to the dedicated data/demo/m1_coursework.db")
    try:
        url = make_url(value)
        database = Path(url.database or "")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Invalid ADMIN_DATABASE_URL for coursework setup") from exc
    if (url.drivername != "sqlite+aiosqlite" or url.query
            or DEMO_DB.is_symlink() or DEMO_DB.parent.is_symlink()
            or DEMO_DB.parent.parent.is_symlink()
            or not DEMO_DB.resolve().is_relative_to(ROOT.resolve())
            or database.resolve() != DEMO_DB.resolve()):
        raise RuntimeError("Coursework setup only accepts data/demo/m1_coursework.db")
    if not DEMO_DB.is_file():
        raise RuntimeError("Demo database is missing; run alembic upgrade head on the dedicated URL first")
    return DEMO_DB


def validate_scenario(agent_id: str) -> None:
    """Require one M2 v3 scenario and one seeded roster identity."""
    try:
        dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("M2 v3 candidate dataset is unavailable") from exc
    if not isinstance(dataset, dict) or dataset.get("dataset_id") != "m2-coursework-candidates-v3":
        raise RuntimeError("Unexpected M2 coursework dataset")
    scenarios = dataset.get("scenarios")
    if not isinstance(scenarios, list):
        raise RuntimeError("M2 coursework scenarios are unavailable")
    matches = [row for row in scenarios if isinstance(row, dict)
               and row.get("agent_id") == agent_id
               and row.get("scenario_id") == f"SCN-{agent_id}"]
    if len(matches) != 1:
        raise RuntimeError("Agent ID must match one unique M2 v3 scenario")
    try:
        roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Seeded agent roster is unavailable") from exc
    if not isinstance(roster, list) or sum(
        isinstance(row, dict) and row.get("agent_id") == agent_id for row in roster
    ) != 1:
        raise RuntimeError("Agent ID must match one seeded agent roster entry")


async def check_migrated_schema(session: AsyncSession) -> None:
    """Reject missing or outdated schemas; this command never creates tables."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    expected = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()
    try:
        revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    except SQLAlchemyError as exc:
        raise RuntimeError("Demo schema is unavailable; run alembic upgrade head") from exc
    if revision != expected:
        raise RuntimeError("Demo schema is outdated; run alembic upgrade head")


async def setup_coursework_agent(
    session: AsyncSession, agent_id: str,
) -> dict[str, str]:
    """Read existing seed identity; never create users, roles, or passwords."""
    from admin.seeds import DEFAULT_TENANT_ID
    from admin.models.tenant import Tenant
    from admin.models.user import Role, User, user_roles

    validate_scenario(agent_id)
    try:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == "default"))
        if tenant is None:
            raise RuntimeError("Default tenant is missing; run admin.seeds in the isolated demo DB")
        if tenant.id != DEFAULT_TENANT_ID or not tenant.enabled:
            raise RuntimeError("Seeded default tenant ID is invalid or tenant is disabled")
        users = (await session.scalars(select(User).where(User.username == agent_id))).all()
        if not users:
            raise RuntimeError("Seeded agent login is missing; run admin.seeds in the isolated demo DB")
        if len(users) != 1 or users[0].tenant_id != tenant.id:
            raise RuntimeError("Agent login is ambiguous or belongs to another tenant")
        user = users[0]
        if not user.is_active or user.is_superadmin:
            raise RuntimeError("Seeded agent login is disabled or privileged")
        roles = (await session.scalars(
            select(Role).join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        )).all()
        if (not any(role.tenant_id == tenant.id and role.name == "agent_manager" for role in roles)
                or any(role.tenant_id != tenant.id or role.name != "agent_manager" for role in roles)):
            raise RuntimeError("Seeded agent must have only the default-tenant agent_manager role")
    except SQLAlchemyError as exc:
        raise RuntimeError("Demo schema is incompatible; run alembic upgrade head on the isolated DB") from exc
    return {"tenant_id": tenant.id, "agent_id": user.username, "scenario_id": f"SCN-{agent_id}"}


async def run_setup(agent_id: str) -> dict[str, str]:
    validate_demo_database_url(os.environ.get("ADMIN_DATABASE_URL"))
    from admin.db import AsyncSessionFactory, close_db

    try:
        async with AsyncSessionFactory() as session:
            await check_migrated_schema(session)
        async with AsyncSessionFactory() as session:
            return await setup_coursework_agent(session, agent_id)
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-id", default="AGT00690", help="M2 v3 scenario agent ID")
    args = parser.parse_args()
    result = asyncio.run(run_setup(args.agent_id))
    print(json.dumps(result, sort_keys=True))
    print(f"Set M1_COURSEWORK_DEMO_TENANT_ID={result['tenant_id']} for the backend")
    print(f"Set M1_COURSEWORK_DEMO_AGENT_ID={result['agent_id']} for the backend")


if __name__ == "__main__":
    main()
