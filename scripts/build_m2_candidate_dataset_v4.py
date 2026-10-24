"""Prepare independent USD horizon-aligned v4 inputs; never read human labels."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import build_m2_candidate_dataset as v3
from scripts.build_life_demo_dataset import load_source

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data/config/m2_horizon_v4_rules.json"
ANNOTATORS = tuple(f"non_m4_annotator_{i}" for i in range(1, 4))
DATASET_ID = "m2-coursework-candidates-v4"


def gates(row):
    return all(row[k] for k in ("eligible", "permission_allowed", "compliance_allowed"))


def realization(row):
    """Use action and source evidence, never ranker scores, for a dated estimate."""
    action = (
        date.fromisoformat(row["action_deadline"])
        if row.get("action_deadline")
        else None
    )
    maximum = (row.get("estimated_approval_days") or {}).get("max")
    status = row.get("policy_status")
    if row["candidate_type"] == "policy":
        if status == "Awaiting Documents" and action and maximum is not None:
            return action + timedelta(days=maximum), "documents"
        if status == "Underwriter Query" and action and maximum is not None:
            return action + timedelta(days=maximum + 2), "query"
        if status == "Client Confirmation Pending" and action:
            return action + timedelta(days=2), "confirmation"
        if status == "Underwriting" and row.get("submit_date") and maximum is not None:
            return date.fromisoformat(row["submit_date"]) + timedelta(
                days=maximum
            ), "passive_underwriting"
        return None, "unsupported_policy_evidence"
    signal = row.get("action_signal", "").lower()
    if action:
        for term, days, rule in (
            ("callback", 10, "callback"),
            ("renewal", 5, "renewal"),
            ("quotation", 35, "quotation"),
        ):
            if term in signal:
                return action + timedelta(days=days), rule
    return None, "review" if "review" in signal else "unsupported_client_evidence"


def within_horizon(realized, start, end):
    return realized is not None and start <= realized <= end


def build_dataset():
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    original = v3.build_dataset()
    if (
        rules["horizon_calendar_days"] != 30
        or rules["as_of_date"] != original["as_of_date"]
    ):
        raise ValueError(
            "A changed horizon or source date requires a new business contract"
        )
    performance = load_source("performance")
    as_of = date.fromisoformat(rules["as_of_date"])
    start, end = as_of + timedelta(days=1), as_of + timedelta(days=30)
    timezone = rules["timezone"]
    cutoff = datetime.combine(
        as_of, datetime.max.time().replace(microsecond=0), ZoneInfo(timezone)
    ).isoformat()
    rules_ref = RULES.relative_to(ROOT).as_posix()
    scenarios = []
    for i, old in enumerate(original["scenarios"]):
        target_cases = rules["planned_bound_cases"][i]
        case_premium = rules["planned_average_written_premium_usd"][i]
        annual = old["objective"]
        objective = {
            "metric": "written_premium",
            "unit": "USD",
            "as_of_date": as_of.isoformat(),
            "annual_open_gap": annual["open_gap"],
            "annual_deadline": annual["deadline"],
            "planning_horizon_start": start.isoformat(),
            "planning_horizon_end": end.isoformat(),
            "business_timezone": timezone,
            "data_cutoff": cutoff,
            "horizon_target": target_cases * case_premium,
            "horizon_current": 0,
            "horizon_open_gap": target_cases * case_premium,
            "status": "available",
            "is_synthetic": True,
            "horizon_target_source": {
                "type": "synthetic_planning_rule",
                "rule_id": rules["rule_id"],
                "version": rules["version"],
                "reference": rules_ref,
                "scenario_index": i,
                "inputs": {
                    "planned_bound_cases": target_cases,
                    "planned_average_written_premium_usd": case_premium,
                },
                "rationale": rules["target_rationale"],
            },
            "horizon_current_source": {
                "type": "synthetic_credit_ledger",
                "reference": rules_ref + "#known_horizon_credit_ledger",
                "entries": [],
                "verified_in_window_credit_count": 0,
                "crediting_rule": rules["crediting_rule"],
                "known_at_cutoff": cutoff,
                "rationale": "The horizon is wholly after the cutoff; no confirmed in-window credit exists in this synthetic ledger. Annual YTD and forecasts are not current horizon production.",
            },
        }
        candidates = copy.deepcopy(old["candidates"])
        partitions = {
            k: []
            for k in (
                "in_horizon",
                "future_follow_up",
                "before_horizon",
                "realization_unavailable",
                "gate_excluded",
            )
        }
        for row in candidates:
            realized, assumption = realization(row)
            within = within_horizon(realized, start, end)
            if realized is None:
                group, reason = (
                    "realization_unavailable",
                    "No supported realization date; follow-up evidence does not establish credited premium.",
                )
            elif realized < start:
                group, reason = (
                    "before_horizon",
                    "Estimated credit date precedes the prospective window; do not count again.",
                )
            elif realized > end:
                group, reason = (
                    "future_follow_up",
                    "Expected credit is after the horizon; retain as a separate future opportunity.",
                )
            else:
                group, reason = "in_horizon", None
            probability_key = (
                "client_retention" if assumption == "renewal" else "conversion_rate"
            )
            probability = performance[old["agent_id"]]["metrics"][probability_key][
                "current"
            ]
            supported_amount = (
                isinstance(probability, (int, float))
                and not isinstance(probability, bool)
                and 0 <= probability <= 1
            )
            if not supported_amount:
                group, reason = (
                    "realization_unavailable",
                    "Missing or unsupported contribution probability.",
                )
            expected = (
                round(row["premium"] * probability, 2)
                if within and supported_amount
                else 0
            )
            row.update(
                metric="written_premium",
                expected_realization_date=realized.isoformat() if realized else None,
                expected_realization_source={
                    "type": "synthetic_timeline_assumption",
                    "rule_id": rules["realization_rule_id"],
                    "reference": rules_ref,
                    "assumption": assumption,
                    "source_record_id": row["source_record_id"],
                    "action_deadline": row.get("action_deadline"),
                    "source_submit_date": row.get("submit_date"),
                    "source_max_approval_days": (
                        row.get("estimated_approval_days") or {}
                    ).get("max"),
                    "is_synthetic": True,
                },
                within_planning_horizon=within,
                out_of_horizon_reason=reason,
                expected_contribution=expected,
                contribution_basis={
                    "type": "synthetic_rule_based_estimate",
                    "rule_id": rules["contribution_rule_id"],
                    "reference": rules_ref,
                    "source_record_id": row["source_record_id"],
                    "source_snapshot": "data/source/agencyperformance-50-v1.zip",
                    "premium_usd": row["premium"],
                    "probability": probability,
                    "probability_metric": probability_key,
                    "formula": "premium_usd * probability only for supported in-window realization; otherwise zero",
                    "metric": "written_premium",
                    "currency": "USD",
                    "is_synthetic": True,
                },
                realization_group=group,
                horizon_ranking_eligible=gates(row) and within and supported_amount,
            )
            partitions[group if gates(row) else "gate_excluded"].append(
                row["candidate_id"]
            )
        scenarios.append(
            {
                "scenario_id": old["scenario_id"],
                "agent_id": old["agent_id"],
                "agent_specialties": old["agent_specialties"],
                "objective": objective,
                "constraints": copy.deepcopy(old["constraints"]),
                "candidate_partitions": partitions,
                "candidates": candidates,
            }
        )
    result = {
        "dataset_id": DATASET_ID,
        "contract": "M1 Horizon-Aligned Gap v1, commit 2a50a94",
        "as_of_date": as_of.isoformat(),
        "business_timezone": timezone,
        "currency": "USD",
        "rules_reference": rules_ref,
        "rules_sha256": hashlib.sha256(RULES.read_bytes()).hexdigest(),
        "formal_normalization_denominator": "objective.horizon_open_gap",
        "annual_gap_usage": "Annual monitoring and annual feasibility only; never a short-horizon fallback.",
        "partition_policy": rules["partition_policy"],
        "non_duplication_policy": rules["non_duplication_policy"],
        "ranker_integration_status": "Requires M4 v4 implementation; never feed this objective to the v3 annual-gap ranker.",
        "zero_gap_policy": "No formal normalization until M4 defines and tests a no-open-gap policy; never use annual gap as fallback.",
        "evaluation_k": [1, 3, 5],
        "selection": copy.deepcopy(original["selection"]),
        "scenarios": scenarios,
    }
    result["selection"]["formal_horizon_candidate_count"] = sum(
        r["horizon_ranking_eligible"] for s in scenarios for r in s["candidates"]
    )
    validate(result)
    return result


def validate(data):
    if data.get("dataset_id") != DATASET_ID or len(data.get("scenarios", [])) != 10:
        raise ValueError("Expected independent v4 dataset with ten scenarios")
    seen_scenarios = set()
    for scenario in data["scenarios"]:
        if scenario["scenario_id"] in seen_scenarios:
            raise ValueError("Duplicate scenario")
        seen_scenarios.add(scenario["scenario_id"])
        obj = scenario["objective"]
        start, end = (
            date.fromisoformat(obj["planning_horizon_start"]),
            date.fromisoformat(obj["planning_horizon_end"]),
        )
        if start != date.fromisoformat(obj["as_of_date"]) + timedelta(
            days=1
        ) or end != start + timedelta(days=29):
            raise ValueError("Horizon must be the inclusive next thirty calendar days")
        ZoneInfo(obj["business_timezone"])
        if (
            obj["metric"] != "written_premium"
            or obj["unit"] != "USD"
            or "open_gap" in obj
        ):
            raise ValueError("Metric, currency or annual-fallback contract mismatch")
        if any(
            isinstance(obj[k], bool)
            or not isinstance(obj[k], (int, float))
            or not math.isfinite(obj[k])
            or obj[k] < 0
            for k in ("horizon_target", "horizon_current", "horizon_open_gap")
        ):
            raise ValueError("Invalid horizon amount")
        if obj["horizon_open_gap"] == 0:
            raise ValueError(
                "No-open-gap formal ranking requires a separate M4 policy; no annual fallback"
            )
        if obj["horizon_open_gap"] != max(
            obj["horizon_target"] - obj["horizon_current"], 0
        ):
            raise ValueError("Horizon gap mismatch")
        inputs = obj["horizon_target_source"]["inputs"]
        if (
            obj["horizon_target"]
            != inputs["planned_bound_cases"]
            * inputs["planned_average_written_premium_usd"]
        ):
            raise ValueError("Target does not match the independent capacity plan")
        if obj["horizon_current"] != 0 or obj["horizon_current_source"]["entries"]:
            raise ValueError("This future-window snapshot has no verified credits")
        rows = scenario["candidates"]
        if (
            len(rows) != 10
            or len({r["candidate_id"] for r in rows}) != 10
            or sum(gates(r) for r in rows) != 6
        ):
            raise ValueError("Raw candidates or original gates changed")
        for row in rows:
            if row["metric"] != obj["metric"] or row["currency"] != obj["unit"]:
                raise ValueError("Candidate currency or metric mismatch")
            if (
                row["agent_id"] != scenario["agent_id"]
                or row["owner_agent_id"] != scenario["agent_id"]
            ):
                raise ValueError("Candidate ownership mismatch")
            realized = (
                date.fromisoformat(row["expected_realization_date"])
                if row["expected_realization_date"]
                else None
            )
            inside = within_horizon(realized, start, end)
            if row["within_planning_horizon"] != inside:
                raise ValueError("Realization boundary mismatch")
            basis = row["contribution_basis"]
            if (
                basis["premium_usd"] != row["premium"]
                or basis["currency"] != "USD"
                or basis["metric"] != "written_premium"
            ):
                raise ValueError("Contribution basis metric or amount mismatch")
            if realization(row)[0] != realized:
                raise ValueError(
                    "Realization does not match its recorded synthetic rule"
                )
            supported_amount = (
                isinstance(basis["probability"], (int, float))
                and not isinstance(basis["probability"], bool)
                and 0 <= basis["probability"] <= 1
            )
            amount = (
                round(basis["premium_usd"] * basis["probability"], 2)
                if inside and supported_amount
                else 0
            )
            if row["expected_contribution"] != amount:
                raise ValueError(
                    "Contribution must match supported in-window written premium"
                )
            if not inside and not row["out_of_horizon_reason"]:
                raise ValueError("Excluded horizon money needs an explicit reason")
            supported = (
                isinstance(basis["probability"], (int, float))
                and not isinstance(basis["probability"], bool)
                and 0 <= basis["probability"] <= 1
            )
            if row["horizon_ranking_eligible"] != (gates(row) and inside and supported):
                raise ValueError("Formal ranking partition mismatch")


def build_blind(data):
    scenarios = []
    fields = (
        "candidate_id",
        "candidate_type",
        "premium",
        "currency",
        "product_type",
        "policy_status",
        "submit_date",
        "estimated_approval_days",
        "client_tags",
        "action_signal",
        "action_deadline",
        "expected_realization_date",
        "expected_realization_source",
        "within_planning_horizon",
        "out_of_horizon_reason",
        "realization_group",
    )
    for scenario in data["scenarios"]:
        scenarios.append(
            {
                "scenario_id": scenario["scenario_id"],
                "agent_id": scenario["agent_id"],
                "objective": copy.deepcopy(scenario["objective"]),
                "agent_specialties": scenario["agent_specialties"],
                "candidates": [
                    {k: copy.deepcopy(r[k]) for k in fields}
                    for r in scenario["candidates"]
                    if gates(r)
                ],
                "formal_ranking_candidate_ids": [
                    r["candidate_id"]
                    for r in scenario["candidates"]
                    if r["horizon_ranking_eligible"]
                ],
            }
        )
    return {
        "dataset_id": DATASET_ID,
        "data_fingerprint": fingerprint(data),
        "blind_version": "human-ranking-v4",
        "scenarios": scenarios,
        "task": "Independently rank only supported in-horizon candidates for reducing this exact 30-day gap. Other evidence is displayed separately, not silently scored as horizon premium.",
    }


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def annotation_template(data, annotators=ANNOTATORS):
    return {
        "dataset_id": DATASET_ID,
        "data_fingerprint": fingerprint(data),
        "annotation_version": "human-v4",
        "annotation_status": "pending",
        "grading_policy": "Fresh independent horizon-only rankings; v4 consensus and graded relevance require later adjudication. No v3 ranking or label is transferred.",
        "scenarios": [
            {
                "scenario_id": s["scenario_id"],
                "eligible_candidate_ids": [
                    r["candidate_id"] for r in s["candidates"] if gates(r)
                ],
                "ranking_candidate_ids": [
                    r["candidate_id"]
                    for r in s["candidates"]
                    if r["horizon_ranking_eligible"]
                ],
                "annotations": [
                    {"annotator_id": aid, "ranking": [], "notes": ""}
                    for aid in annotators
                ],
                "consensus_relevance": {},
            }
            for s in data["scenarios"]
        ],
    }


def write(output):
    output.mkdir(parents=True, exist_ok=True)
    data = build_dataset()
    slots = [("m2_candidate_annotations_v4.json", ANNOTATORS)] + [
        (f"m2_candidate_annotations_v4_{a}.json", (a,)) for a in ANNOTATORS
    ]
    for filename, _ in slots:
        path = output / filename
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("data_fingerprint") != fingerprint(data):
                raise ValueError(
                    "Existing v4 annotation belongs to different evidence; do not overwrite it"
                )
    for filename, payload in (
        ("m2_candidate_scenarios_v4.json", data),
        ("m2_candidate_blind_v4.json", build_blind(data)),
    ):
        (output / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    for filename, annotators in slots:
        path = output / filename
        if not path.exists():
            path.write_text(
                json.dumps(
                    annotation_template(data, annotators), ensure_ascii=False, indent=2
                )
                + "\n",
                encoding="utf-8",
            )
    return data["selection"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/evaluation")
    print(json.dumps(write(parser.parse_args().output), indent=2))
