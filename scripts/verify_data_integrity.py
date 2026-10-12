#!/usr/bin/env python3
"""Verify the A3 business database after migrations and seeding."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from typing import Any

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from admin.db import SYNC_DATABASE_URL
from admin.models.agent_data import (
    AgentAttribution,
    AgentPerformanceMetrics,
    AgentPolicy,
    AgentProfile,
)
from admin.models.competition import Competition, CompetitionEntry
from admin.models.performance_target import PerformanceTarget
from admin.models.tenant import Tenant


REQUIRED_MODELS = (
    Tenant,
    AgentProfile,
    AgentPerformanceMetrics,
    AgentPolicy,
    AgentAttribution,
    Competition,
    CompetitionEntry,
    PerformanceTarget,
)

RATE_FIELDS = (
    ("protection_premium_current", "protection_premium_target", "protection_premium_rate"),
    ("avg_case_size_current", "avg_case_size_target", "avg_case_size_rate"),
    ("submission_count_current", "submission_count_target", "submission_count_rate"),
    ("conversion_rate_current", "conversion_rate_target", "conversion_rate_rate"),
    ("new_clients_current", "new_clients_target", "new_clients_rate"),
    ("client_retention_current", "client_retention_target", "client_retention_rate"),
    ("ai_training_usage_current", "ai_training_usage_target", "ai_training_usage_rate"),
    ("fyc_current", "fyc_target", "fyc_rate"),
)


def _sync_url(url: str) -> str:
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


def _row_count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def verify_database(database_url: str = SYNC_DATABASE_URL) -> dict[str, Any]:
    """Return counts, warnings, and validation errors for a database."""
    engine = create_engine(_sync_url(database_url))
    errors: list[str] = []
    warnings: list[str] = []
    counts: dict[str, int] = {}

    try:
        existing_tables = set(inspect(engine).get_table_names())
        required_tables = {model.__tablename__ for model in REQUIRED_MODELS}
        missing_tables = sorted(required_tables - existing_tables)
        if missing_tables:
            errors.append(f"Missing required tables: {', '.join(missing_tables)}")
            return {"counts": counts, "warnings": warnings, "errors": errors}

        with Session(engine) as session:
            for model in REQUIRED_MODELS:
                counts[model.__tablename__] = _row_count(session, model)

            required_seeded = (
                Tenant,
                AgentProfile,
                AgentPerformanceMetrics,
                AgentPolicy,
                AgentAttribution,
                Competition,
                CompetitionEntry,
                PerformanceTarget,
            )
            for model in required_seeded:
                if counts[model.__tablename__] == 0:
                    errors.append(f"Table {model.__tablename__} contains no seed records")

            profiles = set(session.scalars(select(AgentProfile.agent_id)))
            performance_agents = set(
                session.scalars(select(AgentPerformanceMetrics.agent_id))
            )
            missing_profiles = sorted(performance_agents - profiles)
            if missing_profiles:
                errors.append(
                    "Performance rows without agent profiles: " + ", ".join(missing_profiles)
                )

            for row in session.scalars(select(AgentPerformanceMetrics)):
                for current_name, target_name, rate_name in RATE_FIELDS:
                    current = getattr(row, current_name)
                    target = getattr(row, target_name)
                    rate = getattr(row, rate_name)
                    if current is None or target in (None, 0) or rate is None:
                        continue
                    expected = current / target
                    if not math.isclose(rate, expected, rel_tol=1e-6, abs_tol=1e-6):
                        errors.append(
                            f"Rate mismatch for {row.agent_id}.{rate_name}: "
                            f"stored={rate}, expected={expected}"
                        )

            competition_ids = set(session.scalars(select(Competition.id)))
            for entry in session.scalars(select(CompetitionEntry)):
                if entry.competition_id not in competition_ids:
                    errors.append(
                        f"Competition entry {entry.id} references missing "
                        f"competition {entry.competition_id}"
                    )
                status = (entry.status or "").strip().lower()
                if "achieved" in status and (entry.gap is None or entry.gap > 0):
                    errors.append(
                        f"Achieved competition entry {entry.id} has positive or missing gap"
                    )

            for row in session.scalars(select(AgentAttribution)):
                try:
                    payload = json.loads(row.data_json)
                except (TypeError, json.JSONDecodeError):
                    errors.append(f"Invalid attribution JSON for agent {row.agent_id}")
                    continue
                if not isinstance(payload, dict):
                    errors.append(f"Attribution data for agent {row.agent_id} is not an object")
                elif payload.get("agent_id") not in (None, row.agent_id):
                    errors.append(f"Attribution agent mismatch for {row.agent_id}")

            target_keys = [
                (row.agent_id, row.metric_key, row.period_start, row.period_end)
                for row in session.scalars(select(PerformanceTarget))
            ]
            duplicates = [key for key, count in Counter(target_keys).items() if count > 1]
            if duplicates:
                errors.append(f"Duplicate performance targets: {duplicates}")

            pending_by_agent: dict[str, float] = {}
            for policy in session.scalars(select(AgentPolicy)):
                pending_by_agent[policy.agent_id] = (
                    pending_by_agent.get(policy.agent_id, 0.0) + (policy.premium or 0.0)
                )
            for row in session.scalars(select(AgentPerformanceMetrics)):
                policy_total = pending_by_agent.get(row.agent_id)
                stored_total = row.pending_premium_current
                if policy_total is None or stored_total is None:
                    continue
                if not math.isclose(policy_total, stored_total, rel_tol=1e-6, abs_tol=1e-6):
                    warnings.append(
                        f"Pending premium differs for {row.agent_id}: "
                        f"policies={policy_total}, performance={stored_total}"
                    )
    finally:
        engine.dispose()

    return {"counts": counts, "warnings": warnings, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=SYNC_DATABASE_URL,
        help="SQLAlchemy database URL; defaults to ADMIN_DATABASE_URL",
    )
    args = parser.parse_args()
    report = verify_database(args.database_url)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
