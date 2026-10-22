"""A5 M2 integration tests for database-backed insurance data tools."""

from __future__ import annotations

import asyncio
import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin.db import Base
from admin.models.agent_data import (
    AgentAttribution,
    AgentClient,
    AgentPerformanceMetrics,
    AgentPolicy,
)
from admin.models.competition import Competition, CompetitionEntry
from nanobot.agent.tools.insurance.data_layer.attribution import (
    GetAttributionAnalysisTool,
)
from nanobot.agent.tools.insurance.data_layer.competition import (
    GetCompetitionStatusTool,
)
from nanobot.agent.tools.insurance.data_layer.pending import GetPendingPoliciesTool
from nanobot.agent.tools.insurance.data_layer.performance import (
    GetPerformanceSnapshotTool,
)


class DataLayerToolTests(unittest.TestCase):
    """Exercise tool queries against an isolated relational database."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        Base.metadata.create_all(
            self.engine,
            tables=[
                AgentPerformanceMetrics.__table__,
                AgentPolicy.__table__,
                AgentAttribution.__table__,
                AgentClient.__table__,
                Competition.__table__,
                CompetitionEntry.__table__,
            ],
        )
        self.workspace = Path(".")
        self._seed_rows()

        self.db_patch = patch(
            "nanobot.agent.tools.insurance.data_layer._db.get_sync_db",
            self._database_session,
        )
        self.pending_db_patch = patch(
            "nanobot.agent.tools.insurance.data_layer.pending.get_sync_db",
            self._database_session,
        )
        self.db_patch.start()
        self.pending_db_patch.start()

    def tearDown(self) -> None:
        self.pending_db_patch.stop()
        self.db_patch.stop()
        self.engine.dispose()

    @contextmanager
    def _database_session(self):
        session = self.sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _seed_rows(self) -> None:
        with self.sessions.begin() as session:
            session.add_all(
                [
                    AgentPerformanceMetrics(
                        agent_id="AGT001",
                        period_start="2025-01-01",
                        period_end="2025-12-31",
                        protection_premium_current=40_000,
                        protection_premium_target=100_000,
                    ),
                    AgentPerformanceMetrics(
                        agent_id="AGT001",
                        period_start="2026-01-01",
                        period_end="2026-12-31",
                        protection_premium_current=75_000,
                        protection_premium_target=120_000,
                        protection_premium_rate=0.625,
                        pending_premium_current=31_000,
                        policy_count=4,
                        ytd_fyc=20_000,
                    ),
                    AgentClient(
                        agent_id="AGT001",
                        client_id="CLI001",
                        name="Alex Client",
                        age=42,
                        tag_categories=["life_stage"],
                        tag_labels=["family"],
                    ),
                    AgentPolicy(
                        agent_id="AGT001",
                        policy_id="POL001",
                        customer_id="CLI001",
                        client_name="Alex Client",
                        premium=20_000,
                        product="Protection Plan",
                        status="underwriting",
                        submit_date="2026-04-12",
                        est_days_min=2,
                        est_days_max=5,
                    ),
                    AgentPolicy(
                        agent_id="AGT001",
                        policy_id="POL002",
                        client_name="Taylor Client",
                        premium=11_000,
                        product="Savings Plan",
                        status="documents_required",
                        submit_date="2026-04-10",
                    ),
                    AgentAttribution(
                        agent_id="AGT001",
                        period="2026 Q2",
                        data_json=json.dumps(
                            {
                                "agent_id": "AGT001",
                                "activity": {"appointments": 18},
                                "training": {"sessions": 3},
                                "key_metrics": {"conversion_rate": 0.4},
                            }
                        ),
                    ),
                    Competition(
                        id="COMP-SALES",
                        name="Annual Sales Sprint",
                        name_en="Annual Sales Sprint",
                        type="competition",
                        target_metric="protection_premium",
                        target_value=100_000,
                        unit="USD",
                        deadline="2099-12-31",
                        is_active=True,
                    ),
                    Competition(
                        id="HONOR-ELITE",
                        name="Elite Honour",
                        name_en="Elite Honour",
                        type="honor",
                        target_metric="policy_count",
                        target_value=12,
                        deadline="invalid-date",
                        is_active=True,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    CompetitionEntry(
                        competition_id="COMP-SALES",
                        agent_id="AGT001",
                        current_value=70_000,
                        gap=30_000,
                        status="in_progress",
                    ),
                    CompetitionEntry(
                        competition_id="HONOR-ELITE",
                        agent_id="AGT001",
                        current_value=8,
                        gap=4,
                        status="in_progress",
                    ),
                ]
            )

    @staticmethod
    def _run(tool, **kwargs):
        return json.loads(asyncio.run(tool.execute(**kwargs)))

    def test_performance_tool_uses_latest_period_and_metric_filter(self) -> None:
        result = self._run(
            GetPerformanceSnapshotTool(self.workspace),
            agent_id="AGT001",
            metrics=["protection_premium", "avg_fyc_per_policy"],
        )

        self.assertEqual(result["period"], "2026-01-01 to 2026-12-31")
        self.assertEqual(
            set(result["metrics"]),
            {"protection_premium", "avg_fyc_per_policy"},
        )
        self.assertEqual(result["metrics"]["protection_premium"]["current"], 75_000)
        self.assertEqual(result["metrics"]["protection_premium"]["unit"], "USD")
        self.assertEqual(result["metrics"]["avg_fyc_per_policy"]["current"], 5_000)

    def test_performance_tool_reports_missing_agent(self) -> None:
        result = self._run(
            GetPerformanceSnapshotTool(self.workspace),
            agent_id="UNKNOWN",
        )

        self.assertIn("No performance data found", result["error"])

    def test_pending_policy_tool_enriches_clients_and_uses_stored_total(self) -> None:
        result = self._run(GetPendingPoliciesTool(self.workspace), agent_id="AGT001")

        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["total_pending_premium"], 31_000)
        self.assertEqual({row["currency"] for row in result["policies"]}, {"USD"})
        self.assertEqual(result["policies"][0]["policy_id"], "POL001")
        self.assertEqual(result["policies"][0]["client_age"], 42)
        self.assertEqual(result["policies"][0]["client_tag_labels"], ["family"])

    def test_competition_tool_filters_honours_and_preserves_progress(self) -> None:
        tool = GetCompetitionStatusTool(self.workspace)
        without_honours = self._run(
            tool,
            agent_id="AGT001",
            include_honors=False,
        )
        selected_honour = self._run(
            tool,
            agent_id="AGT001",
            competition_id="HONOR-ELITE",
        )

        self.assertEqual(without_honours["total"], 1)
        self.assertEqual(without_honours["competitions"][0]["unit"], "USD")
        self.assertEqual(without_honours["competitions"][0]["gap"], 30_000)
        self.assertEqual(selected_honour["competitions"][0]["type"], "honor")
        self.assertIsNone(selected_honour["competitions"][0]["days_remaining"])

    def test_attribution_tool_filters_requested_dimensions(self) -> None:
        result = self._run(
            GetAttributionAnalysisTool(self.workspace),
            agent_id="AGT001",
            dimensions=["activity"],
        )

        self.assertEqual(result["agent_id"], "AGT001")
        self.assertEqual(result["period"], "2026 Q2")
        self.assertEqual(result["activity"], {"appointments": 18})
        self.assertNotIn("training", result)


if __name__ == "__main__":
    unittest.main()
