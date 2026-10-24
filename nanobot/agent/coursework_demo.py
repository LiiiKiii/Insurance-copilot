"""Read-only, fail-closed M2 v4 candidate source for the coursework demo."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_DATASET_TENANT = "coursework-demo"  # Source provenance, not the database tenant.
_DATASET_ID = "m2-coursework-candidates-v4"
_RULES_PATH = "data/config/m2_horizon_v4_rules.json"
_PARTITIONS = frozenset({"in_horizon", "future_follow_up", "before_horizon",
                         "realization_unavailable", "gate_excluded"})


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


_TOP_K_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
_QUANTITY = r"\d+(?:\.\d+)?|[A-Za-z]+|[一二三四五六七八九十]+"
_TOP_K_PATTERNS = (
    re.compile(rf"\btop\s+({_QUANTITY})\b", re.IGNORECASE),
    re.compile(rf"\brecommend\s+(?:the\s+)?first\s+({_QUANTITY})\b", re.IGNORECASE),
    re.compile(rf"(?:推荐|推薦)\s*前\s*({_QUANTITY})(?:名|个|個)?"),
    re.compile(rf"前\s*({_QUANTITY})(?:名|个|個)"),
)
_AMBIGUOUS_TOP_K = re.compile(
    rf"\b(?:top|first)\s+(?:{_QUANTITY})\s+(?:or|and|to|through|-)\s+"
    rf"(?:top\s+|first\s+)?(?:{_QUANTITY})\b|"
    rf"前\s*(?:{_QUANTITY})(?:名|个|個)?\s*(?:或|和|到|至)\s*"
    rf"(?:前\s*)?(?:{_QUANTITY})(?:名|个|個)?",
    re.IGNORECASE,
)


def requested_coursework_top_k(message: str) -> int | None:
    """Read only an unambiguous 1–5 request from the authenticated user's text."""
    if not isinstance(message, str) or len(message) > 4096 or _AMBIGUOUS_TOP_K.search(message):
        return None
    matches = [match.group(1).lower() for pattern in _TOP_K_PATTERNS
               for match in pattern.finditer(message)]
    if not matches:
        return None
    values: set[int] = set()
    for token in matches:
        value = int(token) if token.isdecimal() else _TOP_K_WORDS.get(token)
        if value is None or not 1 <= value <= 5:
            return None
        values.add(value)
    return next(iter(values)) if len(values) == 1 else None


def with_requested_coursework_top_k(
    prepared: PreparedCoursework, message: str,
) -> PreparedCoursework:
    """Copy only the validated constraint; leave source and candidate evidence intact."""
    requested = requested_coursework_top_k(message)
    if requested is None:
        return prepared
    return replace(prepared, payload={
        **prepared.payload,
        "constraints": {**prepared.payload["constraints"], "top_k": requested},
    })


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


def _supported_realization(row: dict[str, Any]) -> tuple[date | None, str]:
    """Check the recorded v4 timeline against its source dates and rule."""
    try:
        action = date.fromisoformat(row["action_deadline"]) if row.get("action_deadline") else None
        approval = row.get("estimated_approval_days")
        if approval is not None and not isinstance(approval, dict):
            raise ValueError("Invalid approval evidence")
        maximum = approval.get("max") if approval else None
        if maximum is not None and (isinstance(maximum, bool)
                                    or not isinstance(maximum, int) or maximum < 0):
            raise ValueError("Invalid approval interval")
        if row["candidate_type"] == "policy":
            status = row.get("policy_status")
            if status == "Awaiting Documents" and action and maximum is not None:
                return action + timedelta(days=maximum), "documents"
            if status == "Underwriter Query" and action and maximum is not None:
                return action + timedelta(days=maximum + 2), "query"
            if status == "Client Confirmation Pending" and action:
                return action + timedelta(days=2), "confirmation"
            if status == "Underwriting" and maximum is not None:
                return date.fromisoformat(row["submit_date"]) + timedelta(days=maximum), "passive_underwriting"
            return None, "unsupported_policy_evidence"
        signal = row["action_signal"].lower()
        for term, days, assumption in (("callback", 10, "callback"),
                                        ("renewal", 5, "renewal"),
                                        ("quotation", 35, "quotation")):
            if action and term in signal:
                return action + timedelta(days=days), assumption
        return None, "review" if "review" in signal else "unsupported_client_evidence"
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise CourseworkCandidateError("Invalid demo realization evidence") from exc


class CourseworkCandidateSource:
    """Validate source-linked M2 data without deriving or changing M2 scores."""

    def __init__(self, dataset_path: Path | None = None, mock_dir: Path | None = None) -> None:
        self.dataset_path = dataset_path or _ROOT / "data/evaluation/m2_candidate_scenarios_v4.json"
        self.mock_dir = mock_dir or _ROOT / "data/mock"
        self._use_frozen_source = mock_dir is None

    def _load_json(self, path: Path) -> Any:
        try:
            if self._use_frozen_source and path.parent == self.mock_dir:
                # M2 v4 retains source_path lineage from the frozen v3 snapshot.
                from scripts.build_life_demo_dataset import load_source
                return load_source(path.stem)
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
        rules_path = _ROOT / _RULES_PATH
        try:
            rules = json.loads(rules_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CourseworkCandidateError("Demo horizon rules unavailable") from exc
        if (not isinstance(rules, dict) or dataset.get("rules_reference") != _RULES_PATH
                or dataset.get("contract") != "M1 Horizon-Aligned Gap v1, commit 2a50a94"
                or not isinstance(dataset.get("rules_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", dataset["rules_sha256"]) is None
                or dataset.get("formal_normalization_denominator") != "objective.horizon_open_gap"
                or rules.get("horizon_calendar_days") != 30
                or rules.get("metric") != "written_premium" or rules.get("currency") != "USD"):
            raise CourseworkCandidateError("Invalid demo horizon contract")
        currency = dataset.get("currency")
        as_of_date = dataset.get("as_of_date")
        scenarios = dataset.get("scenarios")
        if (currency != "USD" or not isinstance(scenarios, list) or len(scenarios) != 10
                or dataset.get("business_timezone") != rules.get("timezone")
                or as_of_date != rules.get("as_of_date")):
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
        if (scenario_id != f"SCN-{scope.agent_id}" or not isinstance(objective, dict)
                or not isinstance(candidates, list) or len(candidates) != 10):
            raise CourseworkCandidateError("Invalid agent scenario")
        if (objective.get("metric") != "written_premium" or objective.get("unit") != currency
                or objective.get("as_of_date") != as_of_date
                or objective.get("business_timezone") != rules["timezone"]
                or objective.get("status") != "available"
                or objective.get("is_synthetic") is not True
                or "open_gap" in objective):
            raise CourseworkCandidateError("Objective currency mismatch")
        try:
            snapshot = date.fromisoformat(as_of_date)
            annual_deadline = date.fromisoformat(objective["annual_deadline"])
            start = date.fromisoformat(objective["planning_horizon_start"])
            end = date.fromisoformat(objective["planning_horizon_end"])
            cutoff = datetime.fromisoformat(objective["data_cutoff"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseworkCandidateError("Invalid demo horizon date") from exc
        if (start != snapshot + timedelta(days=1) or end != start + timedelta(days=29)
                or annual_deadline < end or cutoff.date() != snapshot
                or cutoff.tzinfo is None):
            raise CourseworkCandidateError("Invalid demo horizon boundaries")
        _number(objective.get("annual_open_gap"))
        target = _number(objective.get("horizon_target"))
        current = _number(objective.get("horizon_current"))
        gap = _number(objective.get("horizon_open_gap"))
        if gap <= 0 or abs(gap - max(target - current, 0)) > 0.005:
            raise CourseworkCandidateError("Objective horizon gap mismatch")
        target_source = objective.get("horizon_target_source")
        current_source = objective.get("horizon_current_source")
        index = scenarios.index(scenario)
        if (not isinstance(rules.get("planned_bound_cases"), list)
                or not isinstance(rules.get("planned_average_written_premium_usd"), list)
                or index >= len(rules["planned_bound_cases"])
                or index >= len(rules["planned_average_written_premium_usd"])):
            raise CourseworkCandidateError("Invalid demo horizon rules")
        inputs = target_source.get("inputs") if isinstance(target_source, dict) else None
        if (not isinstance(inputs, dict)
                or target_source.get("type") != "synthetic_planning_rule"
                or target_source.get("rule_id") != rules.get("rule_id")
                or target_source.get("version") != rules.get("version")
                or target_source.get("reference") != _RULES_PATH
                or target_source.get("scenario_index") != index
                or target_source.get("rationale") != rules.get("target_rationale")
                or isinstance(inputs.get("planned_bound_cases"), bool)
                or not isinstance(inputs.get("planned_bound_cases"), int)
                or inputs["planned_bound_cases"] <= 0
                or inputs["planned_bound_cases"] != rules["planned_bound_cases"][index]
                or _number(inputs.get("planned_average_written_premium_usd"))
                != _number(rules["planned_average_written_premium_usd"][index])
                or abs(target - inputs["planned_bound_cases"]
                       * inputs["planned_average_written_premium_usd"]) > 0.005):
            raise CourseworkCandidateError("Invalid horizon target provenance")
        if (not isinstance(current_source, dict)
                or current_source.get("type") != "synthetic_credit_ledger"
                or current_source.get("reference") != _RULES_PATH + "#known_horizon_credit_ledger"
                or current_source.get("entries") != rules.get("known_horizon_credit_ledger")
                or current_source.get("entries") != []
                or current_source.get("verified_in_window_credit_count") != 0
                or current_source.get("crediting_rule") != rules.get("crediting_rule")
                or current_source.get("known_at_cutoff") != objective.get("data_cutoff")
                or current != 0):
            raise CourseworkCandidateError("Invalid horizon current provenance")
        constraints = scenario.get("constraints")
        if not isinstance(constraints, dict):
            raise CourseworkCandidateError("Invalid demo constraints")
        top_k = constraints.get("top_k")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
            raise CourseworkCandidateError("Invalid demo top_k")
        partitions = scenario.get("candidate_partitions")
        if (not isinstance(partitions, dict) or set(partitions) != _PARTITIONS
                or any(not isinstance(ids, list) or any(not isinstance(cid, str) for cid in ids)
                       for ids in partitions.values())):
            raise CourseworkCandidateError("Invalid demo partitions")

        policies = self._load_json(self.mock_dir / "policies.json")
        clients = self._load_json(self.mock_dir / "clients.json")
        try:
            from scripts.build_life_demo_dataset import load_source
            performance = load_source("performance")
        except (OSError, ValueError, KeyError) as exc:
            raise CourseworkCandidateError("Demo performance source unavailable") from exc
        if not isinstance(policies, dict) or not isinstance(clients, dict):
            raise CourseworkCandidateError("Invalid demo source records")
        source_groups = {
            "policy": (policies, "policies", "policy_id", "policies.json", "unit"),
            "client": (clients, "clients", "client_id", "clients.json", "currency"),
        }
        prepared: list[dict[str, Any]] = []
        seen: set[str] = set()
        actual_partitions = {name: set() for name in _PARTITIONS}
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
            if row.get("metric") != objective["metric"]:
                raise CourseworkCandidateError("Demo candidate metric mismatch")
            realization_source = row.get("expected_realization_source")
            basis = row.get("contribution_basis")
            approval_days = row.get("estimated_approval_days")
            if approval_days is not None and not isinstance(approval_days, dict):
                raise CourseworkCandidateError("Invalid demo approval evidence")
            if (not isinstance(realization_source, dict) or not isinstance(basis, dict)
                    or realization_source.get("type") != "synthetic_timeline_assumption"
                    or realization_source.get("rule_id") != rules.get("realization_rule_id")
                    or realization_source.get("reference") != _RULES_PATH
                    or realization_source.get("source_record_id") != candidate_id
                    or realization_source.get("action_deadline") != row.get("action_deadline")
                    or realization_source.get("source_submit_date") != row.get("submit_date")
                    or realization_source.get("source_max_approval_days") != (
                        (approval_days or {}).get("max"))
                    or realization_source.get("is_synthetic") is not True
                    or basis.get("type") != "synthetic_rule_based_estimate"
                    or basis.get("rule_id") != rules.get("contribution_rule_id")
                    or basis.get("reference") != _RULES_PATH
                    or basis.get("source_record_id") != candidate_id
                    or basis.get("source_snapshot") != "data/source/agencyperformance-50-v1.zip"
                    or _number(basis.get("premium_usd")) != _number(row.get("premium"))
                    or basis.get("metric") != objective["metric"]
                    or basis.get("currency") != currency
                    or basis.get("is_synthetic") is not True):
                raise CourseworkCandidateError("Demo horizon provenance mismatch")
            probability = _number(basis.get("probability"), maximum=1)
            probability_key = (
                    "client_retention" if realization_source.get("assumption") == "renewal"
                    else "conversion_rate")
            try:
                source_probability = performance[scope.agent_id]["metrics"][probability_key]["current"]
            except (KeyError, TypeError) as exc:
                raise CourseworkCandidateError("Demo conversion source unavailable") from exc
            if (basis.get("probability_metric") != probability_key
                    or probability != _number(source_probability, maximum=1)):
                raise CourseworkCandidateError("Demo contribution probability mismatch")
            raw_realization = row.get("expected_realization_date")
            try:
                realization = date.fromisoformat(raw_realization) if raw_realization is not None else None
            except (TypeError, ValueError) as exc:
                raise CourseworkCandidateError("Invalid demo realization date") from exc
            expected_realization, assumption = _supported_realization(row)
            if (realization != expected_realization
                    or realization_source.get("assumption") != assumption
                    or (realization is not None
                        and assumption not in rules.get("realization_assumptions", {}))):
                raise CourseworkCandidateError("Demo realization lineage mismatch")
            within = realization is not None and start <= realization <= end
            group = ("realization_unavailable" if realization is None else
                     "before_horizon" if realization < start else
                     "future_follow_up" if realization > end else "in_horizon")
            gates = (row.get("eligible"), row.get("permission_allowed"), row.get("compliance_allowed"))
            if any(type(gate) is not bool for gate in gates):
                raise CourseworkCandidateError("Invalid demo decision")
            partition = group if all(gates) else "gate_excluded"
            actual_partitions[partition].add(candidate_id)
            if (row.get("realization_group") != group
                    or row.get("within_planning_horizon") is not within
                    or row.get("horizon_ranking_eligible") is not (all(gates) and within)
                    or (within and row.get("out_of_horizon_reason") is not None)
                    or (not within and (not isinstance(row.get("out_of_horizon_reason"), str)
                                        or not row["out_of_horizon_reason"].strip()))
                    or abs(contribution - (round(_number(row.get("premium")) * probability, 2)
                                           if within else 0)) > 0.005):
                raise CourseworkCandidateError("Invalid demo horizon partition or contribution")
            for name, decision in zip(("eligibility", "permission", "compliance"), gates):
                information = row.get(f"{name}_information")
                if (not isinstance(information, dict)
                        or information.get("decision") is not decision
                        or not isinstance(information.get("basis"), str)
                        or not information["basis"].strip()):
                    raise CourseworkCandidateError("Inconsistent demo decision")
            if partition != "in_horizon":
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
                "metric": row["metric"],
                "currency": row["currency"],
                "horizon_ranking_eligible": True,
                "within_planning_horizon": True,
                "expected_realization_date": raw_realization,
                "recommended_action": action,
                "evidence": {
                    "candidate_type": kind,
                    "action_signal": signal,
                    "action_deadline": deadline,
                    "expected_realization_date": raw_realization,
                },
            })
        if (any(len(ids) != len(set(ids)) for ids in partitions.values())
                or any(set(partitions[name]) != actual_partitions[name] for name in _PARTITIONS)
                or sum(len(ids) for ids in partitions.values()) != len(candidates)):
            raise CourseworkCandidateError("Demo partition membership mismatch")
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
            or ranking.get("ranking_version") != "m4-horizon-weighted-v4"
            or ranking.get("normalization_denominator") != {
                "field": "horizon_open_gap",
                "value": prepared.payload["objective"]["horizon_open_gap"],
                "annual_gap_fallback": False,
            }
            or ranking.get("eligible_count") != len(prepared.candidate_ids)
            or ranking.get("candidate_count") != len(prepared.candidate_ids)
            or ranking.get("excluded_candidates") != []):
        raise CourseworkCandidateError("Invalid ranking scope")
    recommendations = ranking.get("recommendations")
    expected_count = min(prepared.payload["constraints"]["top_k"], len(prepared.candidate_ids))
    if (not isinstance(recommendations, list)
            or len(recommendations) != expected_count):
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
        "ranking_version": ranking["ranking_version"],
        "normalization_denominator": ranking["normalization_denominator"],
        "planning_horizon_start": prepared.payload["objective"]["planning_horizon_start"],
        "planning_horizon_end": prepared.payload["objective"]["planning_horizon_end"],
        "tool_call_id": call_id,
        "actions": actions,
    }
