"""Idempotent seed data for the A3 business database."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.db import AsyncSessionFactory, close_db, init_db
from admin.models.agent_data import (
    AgentAttribution,
    AgentPerformanceMetrics,
    AgentPolicy,
    AgentProfile,
)
from admin.models.competition import Competition, CompetitionEntry
from admin.models.performance_target import PerformanceTarget
from admin.models.tenant import Tenant


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MOCK_DIR = PROJECT_ROOT / "data" / "mock"
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


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


async def _seed_profiles(session: AsyncSession, agents: list[dict[str, Any]]) -> int:
    for agent in agents:
        highlights = agent.get("career_highlights") or []
        await _upsert(
            session,
            AgentProfile,
            {"agent_id": agent["agent_id"]},
            {
                "name_en": agent.get("name_en"),
                "license_no": agent.get("license_no"),
                "team": agent.get("team_en") or agent.get("team"),
                "join_date": agent.get("join_date"),
                "specialties": json.dumps(highlights, ensure_ascii=False),
                "years_of_service": (
                    date.today().year - agent["join_year"]
                    if agent.get("join_year")
                    else None
                ),
                "phone": agent.get("phone"),
                "email": agent.get("email"),
            },
        )
    return len(agents)


async def _seed_performance(
    session: AsyncSession,
    performance: dict[str, dict[str, Any]],
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
            if target is None:
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
                    "tenant_id": DEFAULT_TENANT_ID,
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
) -> tuple[int, int]:
    definitions: dict[str, dict[str, Any]] = {}
    entries: list[tuple[str, dict[str, Any]]] = []

    for agent_id, payload in competition_data.items():
        for competition in payload.get("competitions", []):
            definitions.setdefault(competition["id"], competition)
            entries.append((agent_id, competition))

    for competition_id, competition in definitions.items():
        await _upsert(
            session,
            Competition,
            {"id": competition_id},
            {
                "tenant_id": DEFAULT_TENANT_ID,
                "name": competition["name"],
                "name_en": competition.get("name_en", ""),
                "type": competition["type"],
                "target_metric": competition["target_metric"],
                "target_value": competition.get("target_value"),
                "unit": competition.get("unit", "HKD"),
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


async def seed(mock_dir: Path = DEFAULT_MOCK_DIR) -> dict[str, int]:
    """Create or update the A3 business seed records."""
    agents = _read_json(mock_dir, "agents.json")
    performance = _read_json(mock_dir, "performance.json")
    policies = _read_json(mock_dir, "policies.json")
    competitions = _read_json(mock_dir, "competitions.json")
    attribution = _read_json(mock_dir, "attribution.json")

    await init_db()
    async with AsyncSessionFactory() as session:
        try:
            tenant_count = await _seed_tenant(session)
            profile_count = await _seed_profiles(session, agents)
            performance_count, target_count = await _seed_performance(session, performance)
            policy_count = await _seed_policies(
                session,
                _policy_sources(policies, competitions),
            )
            attribution_count = await _seed_attribution(session, attribution)
            competition_count, entry_count = await _seed_competitions(session, competitions)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return {
        "tenants": tenant_count,
        "agent_profiles": profile_count,
        "performance_rows": performance_count,
        "performance_targets": target_count,
        "policies": policy_count,
        "attribution_rows": attribution_count,
        "competitions": competition_count,
        "competition_entries": entry_count,
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
