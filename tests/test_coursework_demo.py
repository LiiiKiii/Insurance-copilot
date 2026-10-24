"""Isolated authorization and provenance tests for the M1 coursework adapter."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from nanobot.agent.coursework_demo import (
    CourseworkCandidateError,
    CourseworkCandidateSource,
    CourseworkDemoScope,
    recommendation_result,
    requested_coursework_top_k,
    with_requested_coursework_top_k,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import prioritize_followups
from admin.seeds import DEFAULT_TENANT_ID


_ROOT = Path(__file__).resolve().parents[1]
_DATASET = _ROOT / "data/evaluation/m2_candidate_scenarios_v4.json"
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

    def test_all_v4_scenarios_are_source_linked_and_only_in_horizon_rows_reach_m4(self) -> None:
        source = CourseworkCandidateSource()
        for scenario in self.dataset["scenarios"]:
            with self.subTest(agent=scenario["agent_id"]):
                with patch.dict(os.environ, {"M1_COURSEWORK_DEMO_AGENT_ID": scenario["agent_id"]}):
                    prepared = source.prepare(CourseworkDemoScope(DEFAULT_TENANT_ID, scenario["agent_id"]))
                expected_ids = set(scenario["candidate_partitions"]["in_horizon"])
                self.assertEqual(prepared.candidate_ids, expected_ids)
                excluded_ids = {row["candidate_id"] for row in scenario["candidates"]} - expected_ids
                self.assertTrue(excluded_ids.isdisjoint(prepared.candidate_ids))
                ranking = prioritize_followups(prepared.payload)
                self.assertEqual(ranking["excluded_candidates"], [])
                self.assertEqual(ranking["ranking_version"], "m4-horizon-weighted-v4")
                self.assertEqual(ranking["normalization_denominator"], {
                    "field": "horizon_open_gap", "value": scenario["objective"]["horizon_open_gap"],
                    "annual_gap_fallback": False,
                })
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
        dataset["scenarios"][0]["objective"]["horizon_open_gap"] = 1
        with self.assertRaises(CourseworkCandidateError):
            self._prepared_from(dataset)
        prepared = CourseworkCandidateSource().prepare(_SCOPE)
        ranking = prioritize_followups(prepared.payload)
        ranking["recommendations"][0]["candidate_id"] = "foreign-policy"
        with self.assertRaises(CourseworkCandidateError):
            recommendation_result(prepared, ranking, "trusted-call")

    def test_v4_objective_fields_and_source_rules_fail_closed(self) -> None:
        for field, value in (
            ("metric", "policy_count"), ("unit", "HKD"),
            ("horizon_target", None), ("horizon_current", 1),
            ("horizon_open_gap", 228250), ("annual_open_gap", None),
            ("planning_horizon_start", "2026-05-31"),
            ("planning_horizon_end", "2026-07-01"),
            ("horizon_target_source", {}), ("horizon_current_source", {}),
            ("is_synthetic", False),
        ):
            with self.subTest(field=field):
                data = copy.deepcopy(self.dataset)
                data["scenarios"][0]["objective"][field] = value
                with self.assertRaises(CourseworkCandidateError):
                    self._prepared_from(data)
        data = copy.deepcopy(self.dataset)
        data["dataset_id"] = "m2-coursework-candidates-v3"
        with self.assertRaises(CourseworkCandidateError):
            self._prepared_from(data)

    def test_v4_partition_timeline_and_contribution_tampering_fails_closed(self) -> None:
        changes = (
            ("metric", "policy_count"), ("within_planning_horizon", False),
            ("horizon_ranking_eligible", False),
            ("expected_realization_date", "2026-07-01"),
            ("realization_group", "future_follow_up"),
            ("expected_realization_source", {}), ("contribution_basis", {}),
            ("expected_contribution", 100000),
        )
        for field, value in changes:
            with self.subTest(field=field):
                data = copy.deepcopy(self.dataset)
                data["scenarios"][0]["candidates"][0][field] = value
                with self.assertRaises(CourseworkCandidateError):
                    self._prepared_from(data)
        data = copy.deepcopy(self.dataset)
        row = data["scenarios"][0]["candidates"][0]
        row["contribution_basis"]["probability"] = 0.99
        row["expected_contribution"] = round(row["premium"] * 0.99, 2)
        with self.assertRaises(CourseworkCandidateError):
            self._prepared_from(data)
        data = copy.deepcopy(self.dataset)
        row = data["scenarios"][0]["candidates"][0]
        data["scenarios"][0]["candidate_partitions"]["in_horizon"].remove(row["candidate_id"])
        data["scenarios"][0]["candidate_partitions"]["future_follow_up"].append(row["candidate_id"])
        with self.assertRaises(CourseworkCandidateError):
            self._prepared_from(data)
        data = copy.deepcopy(self.dataset)
        data["scenarios"][0]["candidates"][4]["horizon_ranking_eligible"] = True
        with self.assertRaises(CourseworkCandidateError):
            self._prepared_from(data)

    def test_source_and_annotation_files_are_unchanged(self) -> None:
        paths = [
            _ROOT / "data/evaluation/m2_candidate_scenarios.json",
            _DATASET,
            _ROOT / "data/config/m2_horizon_v4_rules.json",
            _ROOT / "data/evaluation/m2_candidate_annotations_v4.json",
        ]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        CourseworkCandidateSource().prepare(_SCOPE)
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in paths])

    def test_explicit_top_k_is_server_selected_without_changing_candidates(self) -> None:
        prepared = CourseworkCandidateSource().prepare(_SCOPE)
        cases = (
            ("top 1", 1), ("top 3", 3), ("top three", 3),
            ("recommend the first 3", 3), ("推荐前三名", 3),
            ("推荐前3个", 3), ("top 5", 5),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(requested_coursework_top_k(message), expected)
                selected = with_requested_coursework_top_k(prepared, message)
                self.assertEqual(selected.payload["constraints"], {"top_k": expected})
                self.assertEqual(selected.payload["candidates"], prepared.payload["candidates"])
                self.assertEqual(selected.candidate_ids, prepared.candidate_ids)
                ranking = prioritize_followups(selected.payload)
                card = recommendation_result(selected, ranking, "trusted-call")
                self.assertEqual(len(ranking["recommendations"]), min(expected, len(prepared.candidate_ids)))
                self.assertEqual([row["candidate_id"] for row in card["actions"]],
                                 [row["candidate_id"] for row in ranking["recommendations"]])
        self.assertEqual(prepared.payload["constraints"], {"top_k": 5})

    def test_invalid_or_ambiguous_top_k_preserves_prepared_default(self) -> None:
        prepared = CourseworkCandidateSource().prepare(_SCOPE)
        for message in ("What should I follow up first?", "top 0", "top 6",
                        "top 3.5", "top 3 or top 5", "top 3 or 5",
                        "top 3 and 5", "top three to five", "推荐前6个",
                        "推荐前三名或前五名", "推荐前三名或五名"):
            with self.subTest(message=message):
                self.assertIsNone(requested_coursework_top_k(message))
                self.assertIs(with_requested_coursework_top_k(prepared, message), prepared)

    def test_card_requires_exact_available_recommendation_count(self) -> None:
        prepared = CourseworkCandidateSource().prepare(_SCOPE)
        selected = with_requested_coursework_top_k(prepared, "top 3")
        ranking = prioritize_followups(selected.payload)
        ranking["recommendations"] = ranking["recommendations"][:2]
        with self.assertRaises(CourseworkCandidateError):
            recommendation_result(selected, ranking, "trusted-call")

        candidates = prepared.payload["candidates"][:2]
        limited = replace(prepared, payload={
            **prepared.payload, "candidates": candidates,
            "constraints": {"top_k": 3},
        }, candidate_ids=frozenset(row["candidate_id"] for row in candidates))
        ranking = prioritize_followups(limited.payload)
        card = recommendation_result(limited, ranking, "trusted-call")
        self.assertEqual(len(ranking["recommendations"]), 2)
        self.assertEqual(len(card["actions"]), 2)


if __name__ == "__main__":
    unittest.main()
