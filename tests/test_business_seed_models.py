"""A5 M2 tests for business seed helpers and relational model constraints."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.db import Base
from admin.models.agent_data import (
    AgentAttribution,
    AgentPerformanceMetrics,
    AgentPolicy,
)
from admin.models.competition import Competition, CompetitionEntry
from admin.models.performance_target import PerformanceTarget
from admin.models.tenant import Tenant
from admin.seeds import (
    _performance_values,
    _period_bounds,
    _require_env,
    _seed_attribution,
    _seed_competitions,
    _seed_performance,
    _seed_policies,
    _seed_tenant,
)


class BusinessSeedModelTests(unittest.IsolatedAsyncioTestCase):
    """Verify deterministic seed updates and database-enforced uniqueness."""

    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[
                        Tenant.__table__,
                        AgentPerformanceMetrics.__table__,
                        PerformanceTarget.__table__,
                        AgentPolicy.__table__,
                        AgentAttribution.__table__,
                        Competition.__table__,
                        CompetitionEntry.__table__,
                    ],
                )
            )

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    def test_seed_secrets_and_periods_are_validated(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            RuntimeError,
            "ADMIN_DEFAULT_PASSWORD",
        ):
            _require_env("ADMIN_DEFAULT_PASSWORD")
        with patch.dict(os.environ, {"ADMIN_DEFAULT_PASSWORD": "safe-value"}):
            self.assertEqual(_require_env("ADMIN_DEFAULT_PASSWORD"), "safe-value")

        self.assertEqual(
            _period_bounds("2026-01-01 to 2026-12-31"),
            ("2026-01-01", "2026-12-31"),
        )
        with self.assertRaises(ValueError):
            _period_bounds("2026")

    def test_performance_mapping_calculates_rates_without_dividing_by_zero(self) -> None:
        values = _performance_values(
            {
                "metrics": {
                    "protection_premium": {"current": 45, "target": 90},
                    "conversion_rate": {"current": 0.4, "target": 0},
                }
            }
        )

        self.assertEqual(values["protection_premium_rate"], 0.5)
        self.assertIsNone(values["conversion_rate_rate"])

    async def test_business_seed_helpers_are_idempotent(self) -> None:
        performance = {
            "AGT001": {
                "period": "2026-01-01 to 2026-12-31",
                "metrics": {
                    "protection_premium": {
                        "label": "MDRT annual credit",
                        "current": 60_000,
                        "target": 100_000,
                        "unit": "Credit",
                    }
                },
            }
        }
        policies = {
            "AGT001": {
                "policies": [
                    {
                        "policy_id": "POL001",
                        "client_name": "Alex Client",
                        "premium": 20_000,
                        "product_en": "Protection Plan",
                        "status_en": "underwriting",
                    }
                ]
            }
        }
        attribution = {
            "AGT001": {
                "period": "2026 Q2",
                "activity": {"appointments": 18},
            }
        }
        competitions = {
            "AGT001": {
                "competitions": [
                    {
                        "id": "COMP001",
                        "name": "Annual Sales Sprint",
                        "name_en": "Annual Sales Sprint",
                        "type": "competition",
                        "target_metric": "protection_premium",
                        "target_value": 100_000,
                        "deadline": "2026-12-31",
                        "current_value": 60_000,
                        "gap": 40_000,
                    }
                ]
            }
        }

        async with self.sessions() as session:
            for _ in range(2):
                await _seed_tenant(session)
                await _seed_performance(session, performance)
                await _seed_policies(session, policies)
                await _seed_attribution(session, attribution)
                await _seed_competitions(session, competitions)
                await session.commit()

            table_counts = {
                "tenants": await session.scalar(select(func.count()).select_from(Tenant)),
                "performance": await session.scalar(
                    select(func.count()).select_from(AgentPerformanceMetrics)
                ),
                "targets": await session.scalar(
                    select(func.count()).select_from(PerformanceTarget)
                ),
                "policies": await session.scalar(
                    select(func.count()).select_from(AgentPolicy)
                ),
                "attribution": await session.scalar(
                    select(func.count()).select_from(AgentAttribution)
                ),
                "competitions": await session.scalar(
                    select(func.count()).select_from(Competition)
                ),
                "entries": await session.scalar(
                    select(func.count()).select_from(CompetitionEntry)
                ),
            }

        self.assertEqual(set(table_counts.values()), {1})

    async def test_models_reject_duplicate_period_and_competition_entry(self) -> None:
        async with self.sessions() as session:
            session.add_all(
                [
                    AgentPerformanceMetrics(
                        agent_id="AGT001",
                        period_start="2026-01-01",
                        period_end="2026-12-31",
                    ),
                    AgentPerformanceMetrics(
                        agent_id="AGT001",
                        period_start="2026-01-01",
                        period_end="2026-12-31",
                    ),
                ]
            )
            with self.assertRaises(IntegrityError):
                await session.commit()
            await session.rollback()

            session.add(
                Competition(
                    id="COMP001",
                    name="Annual Sales Sprint",
                    type="competition",
                    target_metric="protection_premium",
                    deadline="2026-12-31",
                )
            )
            await session.flush()
            session.add_all(
                [
                    CompetitionEntry(competition_id="COMP001", agent_id="AGT001"),
                    CompetitionEntry(competition_id="COMP001", agent_id="AGT001"),
                ]
            )
            with self.assertRaises(IntegrityError):
                await session.commit()


if __name__ == "__main__":
    unittest.main()
