"""Reproducible M1 objective inputs from isolated business-data rows."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import admin.models  # noqa: F401 - register the complete isolated schema
from admin.db import Base
from admin.models.agent_data import AgentPerformanceMetrics
from admin.models.competition import Competition, CompetitionEntry
from nanobot.agent.tools.insurance.data_layer import _db
from nanobot.agent.tools.insurance.reasoning_layer.gap_analysis import compute_gap_analysis


class _FixedDate(date):
    @classmethod
    def today(cls) -> _FixedDate:
        return cls(2026, 10, 22)


class M1EvaluationScenarioTests(unittest.TestCase):
    def test_objective_sources_and_pending_adjusted_gap(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            engine = create_engine(f"sqlite:///{Path(folder, 'scenario.db').as_posix()}")
            try:
                Base.metadata.create_all(engine)
                with Session(engine) as db:
                    db.add(Competition(
                        id="COMP-1", name="Annual Challenge", type="competition",
                        target_metric="protection_premium", target_value=170_000,
                        unit="HKD", deadline="2026-12-31", is_active=True,
                    ))
                    db.add(CompetitionEntry(
                        id="ENTRY-1", competition_id="COMP-1", agent_id="AGT001",
                        current_value=100_000, gap=70_000, status="active",
                    ))
                    db.add(AgentPerformanceMetrics(
                        id="PERF-1", agent_id="AGT001", period_start="2026-01-01",
                        period_end="2026-12-31", protection_premium_current=100_000,
                        protection_premium_target=170_000, pending_premium_current=14_000,
                    ))
                    db.commit()

                @contextmanager
                def isolated_db():
                    with Session(engine) as db:
                        yield db

                with patch.object(_db, "get_sync_db", isolated_db), patch.object(_db, "date", _FixedDate):
                    competition = _db.load_competitions_from_db(Path(folder), "AGT001")[0]
                    performance = _db.load_performance_row("AGT001")
                gap = compute_gap_analysis(
                    [competition], performance.pending_premium_current,
                    pending_unit="HKD",
                )[0]

                self.assertEqual(competition["target_value"], 170_000)
                self.assertEqual(competition["current_value"], 100_000)
                self.assertEqual(competition["gap"], 70_000)
                self.assertEqual(competition["deadline"], "2026-12-31")
                self.assertEqual(competition["days_remaining"], 70)
                self.assertEqual(performance.protection_premium_current, 100_000)
                self.assertEqual(gap["pending_deduction"], 14_000)
                self.assertEqual(gap["actual_gap"], 56_000)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
