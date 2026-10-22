"""Idempotent seed data for the A4 business and administration database."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import date
from numbers import Real
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.db import AsyncSessionFactory, close_db, init_db
from admin.models.agent_data import (
    AgentAttribution,
    AgentClient,
    AgentPerformanceMetrics,
    AgentPolicy,
    AgentProfile,
)
from admin.models.assessment import AgentAssessment
from admin.models.competition import Competition, CompetitionEntry
from admin.models.config import SystemConfig
from admin.models.performance_target import PerformanceTarget
from admin.models.tenant import Tenant
from admin.models.user import Permission, Role, User, role_permissions, user_roles
from admin.services.auth_service import hash_password

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MOCK_DIR = PROJECT_ROOT / "data" / "mock"
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
ACTION_TEMPLATES_CONFIG_KEY = "planning.action_templates"
LEGACY_COMPETITION_IDS = frozenset(
    {
        "COMP_STARLIGHT_2026",
        "COMP_SPRINT_2026Q1",
        "COMP_ELITE_2026",
        "COMP_ROOKIE_2026",
        "HONOR_MDRT_2026",
        "HONOR_COT_2026",
    }
)


def _require_env(name: str) -> str:
    """Read a required seed secret without supplying an insecure default."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} must be set before the initial admin account can be created."
        )
    return value


def _read_json(mock_dir: Path, filename: str) -> Any:
    path = mock_dir / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required seed file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in seed file {path}: {exc}") from exc


async def _upsert(
    session: AsyncSession,
    model: type,
    lookup: dict[str, Any],
    values: dict[str, Any],
) -> tuple[Any, bool]:
    instance = await session.scalar(select(model).filter_by(**lookup))
    created = instance is None
    if instance is None:
        instance = model(**lookup, **values)
        session.add(instance)
    else:
        primary_keys = {column.key for column in model.__mapper__.primary_key}
        for key, value in values.items():
            if key not in primary_keys:
                setattr(instance, key, value)
    return instance, created


def _period_bounds(period: str) -> tuple[str, str]:
    start, separator, end = period.partition(" to ")
    if not separator or not start or not end:
        raise ValueError(f"Unsupported reporting period: {period!r}")
    return start, end


def _metric(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return payload.get("metrics", {}).get(key, {})


def _calculated_rate(metric: dict[str, Any]) -> float | None:
    current = metric.get("current")
    target = metric.get("target")
    if current is None or target in (None, 0):
        return metric.get("rate")
    return current / target


def _performance_values(payload: dict[str, Any]) -> dict[str, Any]:
    protection = _metric(payload, "protection_premium")
    pending = _metric(payload, "pending_premium")
    average_case = _metric(payload, "avg_case_size")
    submissions = _metric(payload, "submission_count")
    conversion = _metric(payload, "conversion_rate")
    new_clients = _metric(payload, "new_clients")
    retention = _metric(payload, "client_retention")
    training = _metric(payload, "ai_training_usage")
    fyc = _metric(payload, "fyc")
    policy_count = _metric(payload, "policy_count")
    quarter_fyc = _metric(payload, "quarter_fyc")
    ytd_fyc = _metric(payload, "ytd_fyc")
    daily_fyc = _metric(payload, "daily_fyc")
    total_clients = _metric(payload, "total_clients")
    churn_rate = _metric(payload, "churn_rate")
    churn_clients = _metric(payload, "churn_clients")
    renewal_due = _metric(payload, "renewal_due_clients")
    ai_practice = _metric(payload, "ai_practice_rate")
    ranking = payload.get("ranking", {})
    history = payload.get("history", {})
    team = payload.get("team_breakdown", {})

    return {
        "protection_premium_current": protection.get("current"),
        "protection_premium_target": protection.get("target"),
        "protection_premium_rate": _calculated_rate(protection),
        "pending_premium_current": pending.get("current"),
        "avg_case_size_current": average_case.get("current"),
        "avg_case_size_target": average_case.get("target"),
        "avg_case_size_rate": _calculated_rate(average_case),
        "avg_case_size_peer_avg": average_case.get("peer_avg"),
        "submission_count_current": submissions.get("current"),
        "submission_count_target": submissions.get("target"),
        "submission_count_rate": _calculated_rate(submissions),
        "conversion_rate_current": conversion.get("current"),
        "conversion_rate_target": conversion.get("target"),
        "conversion_rate_rate": _calculated_rate(conversion),
        "conversion_rate_peer_avg": conversion.get("peer_avg"),
        "new_clients_current": new_clients.get("current"),
        "new_clients_target": new_clients.get("target"),
        "new_clients_rate": _calculated_rate(new_clients),
        "client_retention_current": retention.get("current"),
        "client_retention_target": retention.get("target"),
        "client_retention_rate": _calculated_rate(retention),
        "ai_training_usage_current": training.get("current"),
        "ai_training_usage_target": training.get("target"),
        "ai_training_usage_rate": _calculated_rate(training),
        "fyc_current": fyc.get("current"),
        "fyc_target": fyc.get("target"),
        "fyc_rate": _calculated_rate(fyc),
        "history_last_month_pp": history.get("last_month_protection_premium"),
        "history_last_quarter_pp": history.get("last_quarter_protection_premium"),
        "history_last_year_pp": history.get("last_year_protection_premium"),
        "ranking_team_rank": ranking.get("team_rank"),
        "ranking_team_total": ranking.get("team_total"),
        "ranking_region_rank": ranking.get("region_rank"),
        "ranking_region_total": ranking.get("region_total"),
        "ranking_team_percentile": ranking.get("team_percentile"),
        "ranking_top_performer_premium": ranking.get("top_performer_premium"),
        "team_personal_premium": team.get("personal_premium"),
        "team_subordinate_premium": team.get("subordinate_premium"),
        "policy_count": policy_count.get("current"),
        "quarter_fyc": quarter_fyc.get("current"),
        "ytd_fyc": ytd_fyc.get("current"),
        "daily_fyc": daily_fyc.get("current"),
        "total_clients": total_clients.get("current"),
        "churn_rate": churn_rate.get("current"),
        "churn_clients": churn_clients.get("current"),
        "renewal_due_clients": renewal_due.get("current"),
        "ai_practice_rate": ai_practice.get("current"),
        "online_university": _metric(payload, "online_university").get("current"),
        "no_train_no_sell": _metric(payload, "no_train_no_sell").get("current"),
    }


async def _seed_tenant(session: AsyncSession) -> int:
    await _upsert(
        session,
        Tenant,
        {"slug": "default"},
        {
            "id": DEFAULT_TENANT_ID,
            "name": "Default Tenant",
            "plan": "pro",
            "max_users": 100,
            "max_knowledge_bases": 20,
            "max_tokens_per_month": 10_000_000,
            "enabled": True,
        },
    )
    return 1


async def _seed_admin_access(
    session: AsyncSession,
    tenant_id: str,
) -> tuple[int, int, int]:
    """Create the A4 knowledge-management permissions, roles, and first admin."""
    permission_defs = {
        "read": "View knowledge bases and imported documents",
        "write": "Create knowledge bases and import documents",
        "delete": "Delete knowledge bases and documents",
    }
    permissions: dict[str, Permission] = {}
    for action, description in permission_defs.items():
        permission = await session.scalar(
            select(Permission).where(
                Permission.resource == "knowledge_bases",
                Permission.action == action,
            )
        )
        if permission is None:
            permission = Permission(
                id=str(uuid.uuid4()),
                resource="knowledge_bases",
                action=action,
                description=description,
            )
            session.add(permission)
            await session.flush()
        permissions[action] = permission

    role_defs = {
        "super_admin": ("Full A4 administration access", tuple(permissions)),
        "admin": ("Knowledge-base administration", tuple(permissions)),
        "agent_manager": ("Knowledge-base editing", ("read", "write")),
        "readonly": ("Read-only knowledge access", ("read",)),
    }
    roles: dict[str, Role] = {}
    for name, (description, actions) in role_defs.items():
        role = await session.scalar(
            select(Role).where(Role.tenant_id == tenant_id, Role.name == name)
        )
        if role is None:
            role = Role(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                name=name,
                description=description,
                is_system=True,
            )
            session.add(role)
            await session.flush()
        roles[name] = role

        for action in actions:
            permission = permissions[action]
            link = (
                await session.execute(
                    select(role_permissions).where(
                        role_permissions.c.role_id == role.id,
                        role_permissions.c.permission_id == permission.id,
                    )
                )
            ).first()
            if link is None:
                await session.execute(
                    insert(role_permissions).values(
                        role_id=role.id,
                        permission_id=permission.id,
                    )
                )

    admin = await session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.username == "admin")
    )
    if admin is None:
        admin = User(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            username="admin",
            email="admin@insurance-copilot.local",
            password_hash=hash_password(_require_env("ADMIN_DEFAULT_PASSWORD")),
            display_name="System Administrator",
            is_superadmin=True,
            is_active=True,
            tier="director",
        )
        session.add(admin)
        await session.flush()

    super_admin_role = roles["super_admin"]
    user_role_link = (
        await session.execute(
            select(user_roles).where(
                user_roles.c.user_id == admin.id,
                user_roles.c.role_id == super_admin_role.id,
            )
        )
    ).first()
    if user_role_link is None:
        await session.execute(
            insert(user_roles).values(
                user_id=admin.id,
                role_id=super_admin_role.id,
            )
        )

    return len(permissions), len(roles), 1


# Rank-to-tier mapping and reporting lines, as in the Original agent accounts.
AGENT_TIERS = {
    "Team Lead": "team_lead",
    "Senior Business Manager": "senior_agent",
}
AGENT_SUPERVISORS = {
    "AGT001": "AGT_TL01",
    "AGT002": "AGT_TL01",
    "AGT003": "AGT001",
}


async def _seed_agent_users(
    session: AsyncSession,
    tenant_id: str,
    agents: list[dict[str, Any]],
) -> int:
    """Create a login account for every mock agent so agent IDs match users."""
    manager_role = await session.scalar(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == "agent_manager")
    )
    if manager_role is None:
        raise RuntimeError("agent_manager role must be seeded before agent users")

    users: dict[str, User] = {}
    for agent in agents:
        username = agent["agent_id"]
        tier = AGENT_TIERS.get(agent.get("rank_en") or "", "agent")
        user = await session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.username == username)
        )
        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                username=username,
                email=agent.get("email") or f"{username.lower()}@insurance-copilot.local",
                password_hash=hash_password(_require_env("AGENT_DEFAULT_PASSWORD")),
                display_name=agent.get("name_en") or username,
                is_superadmin=False,
                is_active=True,
                tier=tier,
            )
            session.add(user)
            await session.flush()
        else:
            user.tier = tier
        users[username] = user

        role_link = (
            await session.execute(
                select(user_roles).where(
                    user_roles.c.user_id == user.id,
                    user_roles.c.role_id == manager_role.id,
                )
            )
        ).first()
        if role_link is None:
            await session.execute(
                insert(user_roles).values(user_id=user.id, role_id=manager_role.id)
            )

    for agent in agents:
        username = agent["agent_id"]
        supervisor = agent.get("supervisor_agent_id") or AGENT_SUPERVISORS.get(username)
        users[username].supervisor_id = (
            users[supervisor].id if supervisor in users else None
        )

    return len(users)


async def _seed_profiles(session: AsyncSession, agents: list[dict[str, Any]]) -> int:
    for agent in agents:
        specialties = agent.get("specialties") or agent.get("career_highlights") or []
        await _upsert(
            session,
            AgentProfile,
            {"agent_id": agent["agent_id"]},
            {
                "name_en": agent.get("name_en"),
                "license_no": agent.get("license_no"),
                "team": agent.get("team_en") or agent.get("team"),
                "join_date": agent.get("join_date"),
                "specialties": json.dumps(specialties, ensure_ascii=False),
                "years_of_service": agent.get("years_of_service") or (
                    date.today().year - agent["join_year"]
                    if agent.get("join_year") else None
                ),
                "rank_level": agent.get("rank_level"),
                "phone": agent.get("phone"),
                "email": agent.get("email"),
                "avatar_url": agent.get("avatar_url"),
            },
        )
    return len(agents)


async def _seed_performance(
    session: AsyncSession,
    performance: dict[str, dict[str, Any]],
    tenant_id: str,
) -> tuple[int, int]:
    performance_count = 0
    target_count = 0

    for agent_id, payload in performance.items():
        period_start, period_end = _period_bounds(payload["period"])
        await _upsert(
            session,
            AgentPerformanceMetrics,
            {
                "agent_id": agent_id,
                "period_start": period_start,
                "period_end": period_end,
            },
            _performance_values(payload),
        )
        performance_count += 1

        for metric_key, metric in payload.get("metrics", {}).items():
            target = metric.get("target")
            if not isinstance(target, Real) or isinstance(target, bool):
                continue
            await _upsert(
                session,
                PerformanceTarget,
                {
                    "agent_id": agent_id,
                    "metric_key": metric_key,
                    "period_start": period_start,
                    "period_end": period_end,
                },
                {
                    "tenant_id": tenant_id,
                    "metric_label": metric.get("label", metric_key),
                    "target_value": target,
                    "unit": metric.get("unit", ""),
                    "period_type": "annual",
                },
            )
            target_count += 1

    return performance_count, target_count


def _policy_sources(
    policies: dict[str, dict[str, Any]],
    competitions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    sources = {
        agent_id: payload.get("pending_policies", {})
        for agent_id, payload in competitions.items()
        if payload.get("pending_policies")
    }
    sources.update(policies)
    return sources


async def _seed_policies(
    session: AsyncSession,
    policies: dict[str, dict[str, Any]],
) -> int:
    count = 0
    for agent_id, payload in policies.items():
        for policy in payload.get("policies", []):
            await _upsert(
                session,
                AgentPolicy,
                {"policy_id": policy["policy_id"]},
                {
                    "agent_id": agent_id,
                    "client_name": policy.get("client_name"),
                    "customer_id": policy.get("customer_id"),
                    "premium": policy.get("premium"),
                    "product": policy.get("product_en") or policy.get("product"),
                    "status": policy.get("status_en") or policy.get("status"),
                    "status_detail": policy.get("status_detail"),
                    "submit_date": policy.get("submit_date"),
                    "est_days_min": policy.get("estimated_approval_days_min"),
                    "est_days_max": policy.get("estimated_approval_days_max"),
                },
            )
            count += 1
    return count


async def _seed_clients(
    session: AsyncSession,
    client_data: dict[str, dict[str, Any]],
) -> int:
    count = 0
    for agent_id, payload in client_data.items():
        for client in payload.get("clients", []):
            await _upsert(
                session,
                AgentClient,
                {"agent_id": agent_id, "client_id": client["client_id"]},
                {
                    "name": client.get("name"),
                    "age": client.get("age"),
                    "premium": client.get("premium"),
                    "tag_categories": client.get("tag_categories"),
                    "tag_labels": client.get("tag_labels"),
                },
            )
            count += 1
    return count


async def _seed_assessments(
    session: AsyncSession,
    assessment_data: dict[str, dict[str, Any]],
    tenant_id: str,
) -> int:
    count = 0
    for agent_id, payload in assessment_data.items():
        for assessment in payload.get("assessments", []):
            await _upsert(
                session,
                AgentAssessment,
                {
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "subject": assessment["subject"],
                },
                {
                    "target_value": assessment.get("target_value"),
                    "current_value": assessment.get("current_value"),
                    "status": assessment.get("status"),
                    "remark": assessment.get("remark"),
                },
            )
            count += 1
    return count


async def _seed_attribution(
    session: AsyncSession,
    attribution: dict[str, dict[str, Any]],
) -> int:
    for agent_id, payload in attribution.items():
        await _upsert(
            session,
            AgentAttribution,
            {"agent_id": agent_id},
            {
                "period": payload.get("period"),
                "data_json": json.dumps(payload, ensure_ascii=False),
            },
        )
    return len(attribution)


async def _seed_competitions(
    session: AsyncSession,
    competition_data: dict[str, dict[str, Any]],
    tenant_id: str,
) -> tuple[int, int]:
    definitions: dict[str, dict[str, Any]] = {}
    entries: list[tuple[str, dict[str, Any]]] = []

    for agent_id, payload in competition_data.items():
        for competition in payload.get("competitions", []):
            definitions.setdefault(competition["id"], competition)
            entries.append((agent_id, competition))

    # These identifiers belong to the retired HKD-era seed.  Deactivate only
    # known seed records so that reruns do not hide administrator-created
    # competitions that are not present in the current mock dataset.
    retired_ids = LEGACY_COMPETITION_IDS.difference(definitions)
    if retired_ids:
        retired_competitions = await session.scalars(
            select(Competition).where(Competition.id.in_(retired_ids))
        )
        for competition in retired_competitions:
            competition.is_active = False

    for competition_id, competition in definitions.items():
        await _upsert(
            session,
            Competition,
            {"id": competition_id},
            {
                "tenant_id": tenant_id,
                "name": competition["name"],
                "name_en": competition.get("name_en", ""),
                "type": competition["type"],
                "target_metric": competition["target_metric"],
                "target_value": competition.get("target_value"),
                "unit": competition.get("unit", "USD"),
                "deadline": competition["deadline"],
                "reward": competition.get("reward", ""),
                "description": competition.get("description", ""),
                "is_active": True,
            },
        )

    for agent_id, competition in entries:
        await _upsert(
            session,
            CompetitionEntry,
            {"competition_id": competition["id"], "agent_id": agent_id},
            {
                "current_value": competition.get("current_value"),
                "gap": competition.get("gap"),
                "status": competition.get("status", ""),
            },
        )

    return len(definitions), len(entries)


async def _seed_planning_configuration(session: AsyncSession) -> int:
    """Seed the editable action-plan templates used by the planning layer."""
    existing = await session.scalar(
        select(SystemConfig).where(
            SystemConfig.tenant_id.is_(None),
            SystemConfig.config_key == ACTION_TEMPLATES_CONFIG_KEY,
        )
    )
    if existing is not None:
        # Seed reruns must not erase a super administrator's saved templates.
        return 1

    templates = _read_json(PROJECT_ROOT / "data" / "config", "action_templates.json")
    session.add(
        SystemConfig(
            tenant_id=None,
            config_key=ACTION_TEMPLATES_CONFIG_KEY,
            config_value=json.dumps(templates, ensure_ascii=False),
            config_type="json",
            description="Action templates for competition chase plans",
            is_public=False,
        )
    )
    return 1


async def seed(mock_dir: Path = DEFAULT_MOCK_DIR) -> dict[str, int]:
    """Create or update the A4 business and admin seed records."""
    agents = _read_json(mock_dir, "agents.json")
    performance = _read_json(mock_dir, "performance.json")
    policies = _read_json(mock_dir, "policies.json")
    competitions = _read_json(mock_dir, "competitions.json")
    clients = _read_json(mock_dir, "clients.json")
    assessments = _read_json(mock_dir, "assessments.json")
    attribution = _read_json(mock_dir, "attribution.json")

    await init_db()
    async with AsyncSessionFactory() as session:
        try:
            tenant_count = await _seed_tenant(session)
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == "default"))
            if tenant is None:
                raise RuntimeError("Default tenant was not created")
            permission_count, role_count, admin_count = await _seed_admin_access(
                session,
                tenant.id,
            )
            agent_user_count = await _seed_agent_users(session, tenant.id, agents)
            profile_count = await _seed_profiles(session, agents)
            performance_count, target_count = await _seed_performance(
                session,
                performance,
                tenant.id,
            )
            policy_count = await _seed_policies(
                session,
                _policy_sources(policies, competitions),
            )
            client_count = await _seed_clients(session, clients)
            assessment_count = await _seed_assessments(
                session,
                assessments,
                tenant.id,
            )
            attribution_count = await _seed_attribution(session, attribution)
            competition_count, entry_count = await _seed_competitions(
                session,
                competitions,
                tenant.id,
            )
            planning_config_count = await _seed_planning_configuration(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "tenants": tenant_count,
        "knowledge_permissions": permission_count,
        "admin_roles": role_count,
        "admin_users": admin_count,
        "agent_users": agent_user_count,
        "agent_profiles": profile_count,
        "performance_rows": performance_count,
        "performance_targets": target_count,
        "policies": policy_count,
        "agent_clients": client_count,
        "agent_assessments": assessment_count,
        "attribution_rows": attribution_count,
        "competitions": competition_count,
        "competition_entries": entry_count,
        "planning_configs": planning_config_count,
    }


async def _run_seed_command() -> dict[str, int]:
    try:
        return await seed()
    finally:
        await close_db()


def main() -> None:
    summary = asyncio.run(_run_seed_command())
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
