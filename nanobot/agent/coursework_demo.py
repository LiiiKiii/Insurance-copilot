"""Read-only, fail-closed M2 v3 candidate source for the coursework demo."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[2]
_DATASET_TENANT = "coursework-demo"  # Source provenance, not the database tenant.
_DATASET_ID = "m2-coursework-candidates-v3"


class CourseworkCandidateError(ValueError):
    """The authenticated agent has no complete, verified demo scenario."""


@dataclass(frozen=True)
class CourseworkDemoScope:
    tenant_id: str
    agent_id: str


@dataclass(frozen=True)
class PreparedCoursework:
    scenario_id: str
    as_of_date: str
    payload: dict[str, Any]
    candidate_ids: frozenset[str]


def _number(value: Any, *, minimum: float = 0, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CourseworkCandidateError("Invalid demo numeric field")
    try:
        result = float(value)
    except OverflowError as exc:
        raise CourseworkCandidateError("Invalid demo numeric field") from exc
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise CourseworkCandidateError("Invalid demo numeric field")
    return result


class CourseworkCandidateSource:
    """Validate source-linked M2 data without deriving or changing M2 scores."""

    def __init__(self, dataset_path: Path | None = None, mock_dir: Path | None = None) -> None:
        self.dataset_path = dataset_path or _ROOT / "data/evaluation/m2_candidate_scenarios.json"
        self.mock_dir = mock_dir or _ROOT / "data/mock"

    def _load_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CourseworkCandidateError("Demo source unavailable") from exc

    def prepare(self, scope: CourseworkDemoScope) -> PreparedCoursework:
        configured_tenant = os.getenv("M1_COURSEWORK_DEMO_TENANT_ID", "").strip()
        configured_agent = os.getenv("M1_COURSEWORK_DEMO_AGENT_ID", "").strip()
        if (not configured_tenant or scope.tenant_id != configured_tenant
                or not configured_agent or scope.agent_id != configured_agent):
            raise CourseworkCandidateError("Demo scope unavailable")
        dataset = self._load_json(self.dataset_path)
        if not isinstance(dataset, dict) or dataset.get("dataset_id") != _DATASET_ID:
            raise CourseworkCandidateError("Unexpected demo dataset")
        currency = dataset.get("currency")
        as_of_date = dataset.get("as_of_date")
        scenarios = dataset.get("scenarios")
        if currency != "USD" or not isinstance(scenarios, list):
            raise CourseworkCandidateError("Invalid demo dataset")
        try:
            date.fromisoformat(as_of_date)
        except (TypeError, ValueError) as exc:
            raise CourseworkCandidateError("Invalid demo snapshot date") from exc
        matches = [row for row in scenarios if isinstance(row, dict) and row.get("agent_id") == scope.agent_id]
        if len(matches) != 1:
            raise CourseworkCandidateError("Agent scenario unavailable")
        scenario = matches[0]
        scenario_id = scenario.get("scenario_id")
        objective = scenario.get("objective")
        candidates = scenario.get("candidates")
        if scenario_id != f"SCN-{scope.agent_id}" or not isinstance(objective, dict) or not isinstance(candidates, list):
            raise CourseworkCandidateError("Invalid agent scenario")
        if objective.get("unit") != currency:
            raise CourseworkCandidateError("Objective currency mismatch")
        try:
            date.fromisoformat(objective["deadline"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseworkCandidateError("Invalid demo deadline") from exc
        current = _number(objective.get("current"))
        target = _number(objective.get("target"))
        gap = _number(objective.get("open_gap"))
        if abs(gap - max(target - current, 0)) > 0.01:
            raise CourseworkCandidateError("Objective gap mismatch")
        constraints = scenario.get("constraints")
        if not isinstance(constraints, dict):
            raise CourseworkCandidateError("Invalid demo constraints")
        top_k = constraints.get("top_k")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 50:
            raise CourseworkCandidateError("Invalid demo top_k")

        policies = self._load_json(self.mock_dir / "policies.json")
        clients = self._load_json(self.mock_dir / "clients.json")
        if not isinstance(policies, dict) or not isinstance(clients, dict):
            raise CourseworkCandidateError("Invalid demo source records")
        source_groups = {
            "policy": (policies, "policies", "policy_id", "policies.json", "unit"),
            "client": (clients, "clients", "client_id", "clients.json", "currency"),
        }
        prepared: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in candidates:
            if not isinstance(row, dict):
                raise CourseworkCandidateError("Invalid demo candidate")
            candidate_id = row.get("candidate_id")
            kind = row.get("candidate_type")
            if (not isinstance(candidate_id, str) or not candidate_id.strip()
                    or candidate_id in seen or kind not in source_groups):
                raise CourseworkCandidateError("Invalid demo candidate identity")
            seen.add(candidate_id)
            if (row.get("scenario_id") != scenario_id or row.get("agent_id") != scope.agent_id
                    or row.get("owner_agent_id") != scope.agent_id
                    or row.get("tenant_id") != _DATASET_TENANT
                    or row.get("currency") != currency
                    or row.get("source_record_id") != candidate_id):
                raise CourseworkCandidateError("Demo candidate ownership mismatch")
            group, collection, id_field, filename, currency_field = source_groups[kind]
            agent_group = group.get(scope.agent_id)
            source_rows = agent_group.get(collection) if isinstance(agent_group, dict) else None
            if not isinstance(source_rows, list):
                raise CourseworkCandidateError("Demo source records unavailable")
            source_matches = [item for item in source_rows if isinstance(item, dict) and item.get(id_field) == candidate_id]
            if len(source_matches) != 1:
                raise CourseworkCandidateError("Demo source record mismatch")
            source = source_matches[0]
            expected_path = f"data/mock/{filename}#{scope.agent_id}/{candidate_id}"
            origin = row.get("data_origin")
            if (row.get("source_path") != expected_path
                    or source.get(currency_field) != currency
                    or _number(row.get("premium")) != _number(source.get("premium"))
                    or row.get("source_client_id") != (
                        source.get("customer_id") if kind == "policy" else candidate_id
                    )
                    or not isinstance(origin, dict)
                    or origin.get("candidate_record") != source.get("data_origin")
                    or origin.get("scenario_evidence") != "synthetic_coursework_scenario_profile"
                    or origin.get("scores") != "deterministic_derived"):
                raise CourseworkCandidateError("Demo candidate provenance mismatch")
            contribution = _number(row.get("expected_contribution"))
            urgency = _number(row.get("urgency"), maximum=1)
            actionability = _number(row.get("actionability"), maximum=1)
            business_fit = _number(row.get("business_fit"), maximum=1)
            gates = (row.get("eligible"), row.get("permission_allowed"), row.get("compliance_allowed"))
            if any(type(gate) is not bool for gate in gates):
                raise CourseworkCandidateError("Invalid demo decision")
            for name, decision in zip(("eligibility", "permission", "compliance"), gates):
                information = row.get(f"{name}_information")
                if (not isinstance(information, dict)
                        or information.get("decision") is not decision
                        or not isinstance(information.get("basis"), str)
                        or not information["basis"].strip()):
                    raise CourseworkCandidateError("Inconsistent demo decision")
            if gates != (True, True, True):
                continue
            action = row.get("recommended_action")
            signal = row.get("action_signal")
            deadline = row.get("action_deadline")
            if not all(isinstance(value, str) and value.strip() for value in (action, signal, deadline)):
                raise CourseworkCandidateError("Invalid demo action evidence")
            prepared.append({
                "candidate_id": candidate_id,
                "expected_contribution": contribution,
                "urgency": urgency,
                "actionability": actionability,
                "business_fit": business_fit,
                "eligible": True,
                "permission_allowed": True,
                "compliance_allowed": True,
                "recommended_action": action,
                "evidence": {
                    "candidate_type": kind,
                    "action_signal": signal,
                    "action_deadline": deadline,
                },
            })
        if not prepared:
            raise CourseworkCandidateError("No authorized demo candidates")
        return PreparedCoursework(
            scenario_id=scenario_id,
            as_of_date=as_of_date,
            payload={
                "agent_id": scope.agent_id,
                "objective": dict(objective),
                "constraints": {"top_k": top_k},
                "candidates": prepared,
            },
            candidate_ids=frozenset(row["candidate_id"] for row in prepared),
        )


def recommendation_result(prepared: PreparedCoursework, ranking: Any, call_id: str) -> dict[str, Any]:
    """Project validated M4 output into M5's action_plan-compatible result."""
    if not isinstance(ranking, dict) or ranking.get("agent_id") != prepared.payload["agent_id"]:
        raise CourseworkCandidateError("Invalid ranking identity")
    if (ranking.get("objective") != prepared.payload["objective"]
            or ranking.get("eligible_count") != len(prepared.candidate_ids)
            or ranking.get("candidate_count") != len(prepared.candidate_ids)
            or ranking.get("excluded_candidates") != []):
        raise CourseworkCandidateError("Invalid ranking scope")
    recommendations = ranking.get("recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        raise CourseworkCandidateError("Invalid ranking result")
    seen: set[str] = set()
    actions: list[dict[str, Any]] = []
    for expected_rank, row in enumerate(recommendations, start=1):
        if not isinstance(row, dict):
            raise CourseworkCandidateError("Invalid ranking item")
        candidate_id = row.get("candidate_id")
        if (candidate_id not in prepared.candidate_ids or candidate_id in seen
                or row.get("rank") != expected_rank
                or row.get("priority_level") not in {"P0", "P1", "P2"}):
            raise CourseworkCandidateError("Invalid ranked candidate")
        seen.add(candidate_id)
        source = next(item for item in prepared.payload["candidates"] if item["candidate_id"] == candidate_id)
        if (row.get("recommended_action") != source["recommended_action"]
                or row.get("evidence") != source["evidence"]
                or not isinstance(row.get("recommended_timing"), str)
                or not row["recommended_timing"].strip()
                or not isinstance(row.get("score_components"), dict)):
            raise CourseworkCandidateError("Invalid ranking evidence")
        score = _number(row.get("priority_score"), maximum=100)
        actions.append({
            "rank": expected_rank,
            "candidate_id": candidate_id,
            "priority": row["priority_level"],
            "action": row["recommended_action"],
            "timing": row["recommended_timing"],
            "evidence": row["evidence"],
            "priority_score": score,
            "score_components": row["score_components"],
        })
    return {
        "kind": "action_plan",
        "title": "Coursework follow-up priorities",
        "source": _DATASET_ID,
        "scenario_id": prepared.scenario_id,
        "as_of_date": prepared.as_of_date,
        "tool_call_id": call_id,
        "actions": actions,
    }
