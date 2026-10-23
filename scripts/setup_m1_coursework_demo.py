"""Create one authenticated coursework agent in the dedicated local demo DB."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path

from sqlalchemy import insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession


ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / "data/demo/m1_coursework.db"
DATASET = ROOT / "data/evaluation/m2_candidate_scenarios.json"
DEMO_SLUG = "coursework-demo"


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
    """Allow only a unique agent identifier in the checked-in M2 v3 source."""
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
    session: AsyncSession, agent_id: str, password: str | None,
) -> dict[str, str]:
    """Create or validate an isolated tenant and login without resetting secrets."""
    from admin.models.tenant import Tenant
    from admin.models.user import Role, User, role_permissions, user_roles
    from admin.services.auth_service import hash_password

    validate_scenario(agent_id)
    try:
        async with session.begin():
            tenants = (await session.scalars(select(Tenant))).all()
            if any(tenant.slug != DEMO_SLUG for tenant in tenants):
                raise RuntimeError("Database contains a non-demo tenant; use the dedicated isolated DB")
            tenant = tenants[0] if tenants else None
            if tenant is not None and not tenant.enabled:
                raise RuntimeError("Existing coursework tenant is disabled")
            if tenant is None:
                tenant = Tenant(id=str(uuid.uuid4()), slug=DEMO_SLUG, name="Coursework Demo")
                session.add(tenant)
                await session.flush()

            users = (await session.scalars(select(User))).all()
            if any(user.tenant_id != tenant.id for user in users):
                raise RuntimeError("Database contains an account outside the demo tenant")
            matches = [user for user in users if user.username == agent_id]
            if len(matches) > 1:
                raise RuntimeError("Agent username is ambiguous")
            user = matches[0] if matches else None
            if user is not None and (not user.is_active or user.is_superadmin):
                raise RuntimeError("Existing demo agent is disabled or privileged")
            if user is not None:
                assigned_roles = (await session.scalars(
                    select(Role).join(user_roles, Role.id == user_roles.c.role_id)
                    .where(user_roles.c.user_id == user.id)
                )).all()
                if any(role.tenant_id != tenant.id or role.name != "readonly"
                       for role in assigned_roles):
                    raise RuntimeError("Existing demo agent has privileged or foreign roles")
            if user is None:
                if not password:
                    raise RuntimeError("Set M1_COURSEWORK_DEMO_PASSWORD for a new demo agent")
                if len(password) < 12:
                    raise RuntimeError("Demo agent password must have at least 12 characters")
                email = f"m1-demo-{agent_id.lower()}@example.invalid"
                if any(existing.email == email for existing in users):
                    raise RuntimeError("Demo agent email is already in use")
                user = User(
                    id=str(uuid.uuid4()), tenant_id=tenant.id, username=agent_id,
                    email=email, password_hash=hash_password(password),
                    display_name=agent_id, is_active=True, is_superadmin=False,
                    tier="agent",
                )
                session.add(user)
                await session.flush()

            role = await session.scalar(select(Role).where(
                Role.tenant_id == tenant.id, Role.name == "readonly",
            ))
            if role is None:
                role = Role(id=str(uuid.uuid4()), tenant_id=tenant.id, name="readonly",
                            description="Coursework demo login", is_system=True)
                session.add(role)
                await session.flush()
            elif (await session.execute(select(role_permissions).where(
                role_permissions.c.role_id == role.id,
            ))).first() is not None:
                raise RuntimeError("Existing demo readonly role has resource permissions")
            linked = (await session.execute(select(user_roles).where(
                user_roles.c.user_id == user.id, user_roles.c.role_id == role.id,
            ))).first()
            if linked is None:
                await session.execute(insert(user_roles).values(user_id=user.id, role_id=role.id))
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
            return await setup_coursework_agent(
                session, agent_id, os.environ.get("M1_COURSEWORK_DEMO_PASSWORD"),
            )
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-id", default="AGT00690", help="M2 v3 scenario agent ID")
    args = parser.parse_args()
    result = asyncio.run(run_setup(args.agent_id))
    print(json.dumps(result, sort_keys=True))
    print(f"Set M1_COURSEWORK_DEMO_TENANT_ID={result['tenant_id']} for the backend")


if __name__ == "__main__":
    main()
