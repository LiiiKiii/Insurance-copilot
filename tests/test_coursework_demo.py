"""Isolated authorization and provenance tests for the M1 coursework adapter."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nanobot.agent.coursework_demo import (
    CourseworkCandidateError,
    CourseworkCandidateSource,
    CourseworkDemoScope,
    recommendation_result,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import prioritize_followups
from admin.seeds import DEFAULT_TENANT_ID


_ROOT = Path(__file__).resolve().parents[1]
_DATASET = _ROOT / "data/evaluation/m2_candidate_scenarios.json"
_SCOPE = CourseworkDemoScope(DEFAULT_TENANT_ID, "AGT00690")


class CourseworkDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {
            "M1_COURSEWORK_DEMO_TENANT_ID": DEFAULT_TENANT_ID,
            "M1_COURSEWORK_DEMO_AGENT_ID": "AGT00690",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.dataset = json.loads(_DATASET.read_text(encoding="utf-8"))

    def _prepared_from(self, dataset: dict):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidates.json"
            path.write_text(json.dumps(dataset), encoding="utf-8")
            return CourseworkCandidateSource(path, _ROOT / "data/mock").prepare(_SCOPE)

    def test_all_v3_scenarios_are_source_linked_and_only_allowed_rows_reach_m4(self) -> None:
        source = CourseworkCandidateSource()
        for scenario in self.dataset["scenarios"]:
            with self.subTest(agent=scenario["agent_id"]):
                with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_AGENT_ID": scenario["agent_id"]}):
                    prepared = source.prepare(CourseworkDemoScope(DEFAULT_TENANT_ID, scenario["agent_id"]))
                self.assertEqual(len(prepared.payload["candidates"]), 6)
                excluded_ids = {
                    row["candidate_id"] for row in scenario["candidates"]
                    if not all(row[key] for key in (
                        "eligible", "permission_allowed", "compliance_allowed",
                    ))
                }
                self.assertTrue(excluded_ids.isdisjoint(prepared.candidate_ids))
                ranking = prioritize_followups(prepared.payload)
                self.assertEqual(ranking["excluded_candidates"], [])
                card = recommendation_result(prepared, ranking, "trusted-call")
                self.assertTrue({row["candidate_id"] for row in card["actions"]} <= prepared.candidate_ids)

    def test_scope_requires_explicit_tenant_configuration_and_agent_scenario(self) -> None:
        source = CourseworkCandidateSource()
        with self.assertRaises(CourseworkCandidateError):
            source.prepare(CourseworkDemoScope("other-tenant", "AGT00690"))
        with self.assertRaises(CourseworkCandidateError):
            source.prepare(CourseworkDemoScope(DEFAULT_TENANT_ID, "unknown-agent"))
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_AGENT_ID": ""}):
            with self.assertRaises(CourseworkCandidateError):
                source.prepare(_SCOPE)
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_AGENT_ID": "AGT00770"}):
            with self.assertRaises(CourseworkCandidateError):
                source.prepare(_SCOPE)
        with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_TENANT_ID": ""}):
            with self.assertRaises(CourseworkCandidateError):
                source.prepare(_SCOPE)

    def test_malformed_or_inconsistent_candidate_fails_closed(self) -> None:
        changes = (
            ("owner_agent_id", "other-agent"),
            ("tenant_id", "other-tenant"),
            ("currency", "HKD"),
            ("candidate_id", "unknown-policy"),
            ("expected_contribution", None),
            ("expected_contribution", 10 ** 400),
            ("urgency", 2),
            ("source_path", "data/mock/other.json"),
            ("source_record_id", "different-id"),
        )
        for field, value in changes:
            with self.subTest(field=field):
                dataset = copy.deepcopy(self.dataset)
                dataset["scenarios"][0]["candidates"][0][field] = value
                with self.assertRaises(CourseworkCandidateError):
                    self._prepared_from(dataset)
        dataset = copy.deepcopy(self.dataset)
        dataset["scenarios"][0]["candidates"][0]["permission_information"]["decision"] = False
        with self.assertRaises(CourseworkCandidateError):
            self._prepared_from(dataset)

    def test_objective_and_ranked_output_must_match_authorized_scenario(self) -> None:
        dataset = copy.deepcopy(self.dataset)
        dataset["scenarios"][0]["objective"]["open_gap"] = 1
        with self.assertRaises(CourseworkCandidateError):
            self._prepared_from(dataset)
        prepared = CourseworkCandidateSource().prepare(_SCOPE)
        ranking = prioritize_followups(prepared.payload)
        ranking["recommendations"][0]["candidate_id"] = "foreign-policy"
        with self.assertRaises(CourseworkCandidateError):
            recommendation_result(prepared, ranking, "trusted-call")


if __name__ == "__main__":
    unittest.main()
