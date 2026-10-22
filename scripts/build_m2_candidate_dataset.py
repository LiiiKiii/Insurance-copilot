"""Build the deterministic M2 coursework candidate dataset for M4.

The source dataset is agency-level. Customer and pending-policy rows in
``data/mock`` are synthetic project records derived from observed agent and
product distributions. This script preserves that lineage and adds only
deterministic, documented scoring fields.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "evaluation" / "m2_candidate_scenarios.json"
AS_OF = date(2026, 5, 31)
SCENARIO_COUNT = 10
POLICIES_PER_SCENARIO = 4
ACTIONABLE_CLIENTS_PER_SCENARIO = 2
FILTERED_CLIENTS_PER_SCENARIO = 4
NEED_PRODUCT = {
    "Motor": "Private Motor Insurance",
    "Property": "Home Contents Insurance",
    "Commercial": "SME Business Package",
    "Liability": "Public Liability Insurance",
    "Specialty": "Personal Liability Insurance",
}


def load(name: str) -> Any:
    return json.loads((ROOT / "data" / "mock" / name).read_text(encoding="utf-8"))


def bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def policy_urgency(policy: dict[str, Any]) -> tuple[float, str, int]:
    submitted = date.fromisoformat(policy["submit_date"])
    due = submitted + timedelta(days=int(policy["estimated_approval_days_max"]))
    remaining = (due - AS_OF).days
    score = 1.0 if remaining <= 0 else 0.85 if remaining <= 2 else 0.65 if remaining <= 5 else 0.4
    if policy["status"] == "Awaiting Documents":
        score += 0.1
    return bounded(score), due.isoformat(), remaining


def need_category(tags: set[str]) -> str | None:
    return next((name for name in NEED_PRODUCT if name in tags), None)


def business_fit(
    tags: set[str],
    product: str,
    category: str | None,
    specialties: set[str],
    specialty_categories: set[str],
) -> float:
    score = 0.4
    score += 0.3 if product in specialties else 0
    score += 0.2 if category and (category in tags or category in specialty_categories) else 0
    score += 0.1 if "High Value" in tags else 0
    return bounded(score)


def relevance(candidate: dict[str, Any]) -> int:
    if not all(candidate[key] for key in ("eligible", "permission_allowed", "compliance_allowed")):
        return 0
    if candidate["urgency"] >= 0.85 and candidate["actionability"] >= 0.85:
        return 3
    if candidate["urgency"] >= 0.65 or candidate["business_fit"] >= 0.85:
        return 2
    return 1 if candidate["expected_contribution"] > 0 else 0


def common_fields(agent_id: str, candidate_id: str, allowed: bool) -> dict[str, Any]:
    return {
        "scenario_id": f"SCN-{agent_id}",
        "agent_id": agent_id,
        "candidate_id": candidate_id,
        "currency": "USD",
        "permission_allowed": True,
        "permission_information": {
            "decision": True,
            "basis": "Candidate is stored under the same agent_id",
        },
        "compliance_allowed": allowed,
        "compliance_information": {
            "decision": allowed,
            "basis": "Agent training-compliance gate is not blocking sales",
        },
    }


def build_dataset() -> dict[str, Any]:
    agents = sorted(load("agents.json"), key=lambda row: row["agent_id"])
    clients_by_agent = load("clients.json")
    policies_by_agent = load("policies.json")
    performance_by_agent = load("performance.json")
    attribution_by_agent = load("attribution.json")
    scenarios: list[dict[str, Any]] = []

    for agent in agents[:SCENARIO_COUNT]:
        agent_id = agent["agent_id"]
        performance = performance_by_agent[agent_id]
        client_rows = clients_by_agent[agent_id]["clients"]
        clients = {row["client_id"]: row for row in client_rows}
        policies = sorted(
            policies_by_agent[agent_id]["policies"], key=lambda row: row["policy_id"]
        )[:POLICIES_PER_SCENARIO]
        product_categories = {
            row["product_name"]: row["category"]
            for row in attribution_by_agent[agent_id]["product_details"]
        }
        specialties = set(agent["specialties"])
        specialty_categories = {
            product_categories[name] for name in specialties if name in product_categories
        }
        conversion = float(performance["metrics"]["conversion_rate"]["current"])
        retention = float(performance["metrics"]["client_retention"]["current"])
        allowed = not bool(performance["training_compliance"]["no_train_no_sell"])
        candidates: list[dict[str, Any]] = []

        for policy in policies:
            client = clients[policy["customer_id"]]
            tags = set(client["tag_labels"])
            urgency, due, remaining = policy_urgency(policy)
            eligible = policy["status"] in {"Underwriting", "Awaiting Documents"} and policy["premium"] > 0
            actionability = 0.95 if policy["status"] == "Awaiting Documents" else 0.55
            actionability += 0.1 if remaining <= 0 else 0
            actionability += 0.05 if "Follow-up" in tags else 0
            candidate = {
                **common_fields(agent_id, policy["policy_id"], allowed),
                "candidate_type": "policy",
                "premium": float(policy["premium"]),
                "expected_contribution": round(float(policy["premium"]) * conversion, 2),
                "policy_status": policy["status"],
                "submit_date": policy["submit_date"],
                "estimated_approval_days": {
                    "min": int(policy["estimated_approval_days_min"]),
                    "max": int(policy["estimated_approval_days_max"]),
                },
                "expected_decision_date": due,
                "client_tags": client["tag_labels"],
                "product_type": policy["product"],
                "eligible": eligible,
                "eligibility_information": {
                    "decision": eligible,
                    "basis": "Pending status and positive premium",
                },
                "urgency": urgency,
                "actionability": bounded(actionability),
                "business_fit": business_fit(
                    tags,
                    policy["product"],
                    product_categories.get(policy["product"]),
                    specialties,
                    specialty_categories,
                ),
                "source_record_id": policy["policy_id"],
                "source_path": f"data/mock/policies.json#{agent_id}/{policy['policy_id']}",
                "source_client_id": client["client_id"],
                "data_origin": {
                    "candidate_record": policy["data_origin"],
                    "client_record": client["data_origin"],
                    "scores": "deterministic_derived",
                },
            }
            candidate["reference_relevance_grade"] = relevance(candidate)
            candidates.append(candidate)

        linked_clients = {row["customer_id"] for row in policies}
        available_clients = [
            row for row in client_rows if row["client_id"] not in linked_clients
        ]
        actionable_clients = [
            row
            for row in available_clients
            if {"Renewal Due", "Follow-up"} & set(row["tag_labels"])
        ]
        filtered_clients = [
            row
            for row in available_clients
            if not ({"Renewal Due", "Follow-up"} & set(row["tag_labels"]))
        ]
        actionable_clients.sort(
            key=lambda row: (
                -(3 * ("Renewal Due" in row["tag_labels"])
                  + 2 * ("Follow-up" in row["tag_labels"])
                  + ("High Value" in row["tag_labels"])),
                row["client_id"],
            )
        )
        filtered_clients.sort(key=lambda row: row["client_id"])
        client_candidates = (
            actionable_clients[:ACTIONABLE_CLIENTS_PER_SCENARIO]
            + filtered_clients[:FILTERED_CLIENTS_PER_SCENARIO]
        )
        for client in client_candidates:
            tags = set(client["tag_labels"])
            category = need_category(tags)
            product = NEED_PRODUCT.get(category or "", agent["specialties"][0])
            eligible = bool({"Renewal Due", "Follow-up"} & tags)
            urgency = 0.9 if "Renewal Due" in tags else 0.75 if "Follow-up" in tags else 0.6 if "High Value" in tags else 0.35
            actionability = 0.95 if {"Renewal Due", "Follow-up"}.issubset(tags) else 0.9 if "Follow-up" in tags else 0.85 if "Renewal Due" in tags else 0.55
            candidate = {
                **common_fields(agent_id, client["client_id"], allowed),
                "candidate_type": "client",
                "premium": float(client["premium"]),
                "expected_contribution": round(float(client["premium"]) * retention, 2),
                "policy_status": None,
                "submit_date": None,
                "estimated_approval_days": None,
                "expected_decision_date": None,
                "not_applicable_reason": "Client follow-up candidate; no pending policy attached",
                "client_tags": client["tag_labels"],
                "product_type": product,
                "eligible": eligible,
                "eligibility_information": {
                    "decision": eligible,
                    "basis": "Client has an explicit renewal-due or follow-up signal",
                },
                "urgency": urgency,
                "actionability": actionability,
                "business_fit": business_fit(
                    tags, product, category, specialties, specialty_categories
                ),
                "source_record_id": client["client_id"],
                "source_path": f"data/mock/clients.json#{agent_id}/{client['client_id']}",
                "source_client_id": client["client_id"],
                "data_origin": {
                    "candidate_record": client["data_origin"],
                    "scores": "deterministic_derived",
                },
            }
            candidate["reference_relevance_grade"] = relevance(candidate)
            candidates.append(candidate)

        current = float(performance["metrics"]["protection_premium"]["current"])
        target = float(performance["metrics"]["protection_premium"]["target"])
        scenarios.append({
            "scenario_id": f"SCN-{agent_id}",
            "agent_id": agent_id,
            "objective": {
                "metric": "written_premium",
                "current": current,
                "target": target,
                "open_gap": round(max(target - current, 0.0), 2),
                "unit": "USD",
                "deadline": "2026-12-31",
            },
            "constraints": {"top_k": 5},
            "candidates": candidates,
            "relevance": {
                row["candidate_id"]: row["reference_relevance_grade"]
                for row in candidates
            },
        })

    return {
        "dataset_id": "m2-coursework-candidates-v1",
        "description": "Deterministic coursework candidate set for M4 ranking integration.",
        "as_of_date": AS_OF.isoformat(),
        "currency": "USD",
        "evaluation_k": [1, 3, 5],
        "selection": {
            "method": "First ten agent IDs in ascending order; four policies, two actionable clients, and four filter-control clients per agent",
            "random_sampling": False,
            "scenario_count": len(scenarios),
            "candidates_per_scenario": 10,
            "candidate_count": sum(len(row["candidates"]) for row in scenarios),
            "filtered_candidate_count": sum(
                row["eligible"]
                and row["permission_allowed"]
                and row["compliance_allowed"]
                for scenario in scenarios
                for row in scenario["candidates"]
            ),
        },
        "source_files": [
            "data/mock/agents.json",
            "data/mock/clients.json",
            "data/mock/policies.json",
            "data/mock/performance.json",
            "data/mock/attribution.json",
        ],
        "field_lineage": {
            "direct_project_fields": [
                "agent_id", "candidate_id", "premium", "policy_status",
                "submit_date", "estimated_approval_days", "client_tags",
                "product_type", "source_record_id",
            ],
            "derived_fields": [
                "expected_contribution", "expected_decision_date", "eligible",
                "permission_allowed", "compliance_allowed", "urgency",
                "actionability", "business_fit", "reference_relevance_grade",
            ],
            "synthetic_record_notice": "Customer and policy records are coursework demonstration records generated from source-derived agent and product distributions; they are not individual Kaggle customer or policy records.",
        },
        "transformation_rules": {
            "policy_expected_contribution": "premium multiplied by the agent historical conversion rate",
            "client_expected_contribution": "client premium multiplied by the agent retention rate",
            "urgency": "Policy due-date bands or client renewal/follow-up tags, normalised to 0-1",
            "actionability": "Awaiting-documents/underwriting status or client follow-up tags, normalised to 0-1",
            "business_fit": "Base 0.4 plus product-specialty, need-category, and high-value matches, capped at 1",
            "eligibility": "Pending positive-premium policy, or client with an explicit renewal-due/follow-up signal",
            "permission": "Candidate record belongs to the scenario agent",
            "compliance": "Agent training-compliance gate permits sales",
            "reference_relevance": "Deterministic 0-3 coursework label from stated operational thresholds",
        },
        "limitations": [
            "Reference relevance grades validate the coursework pipeline only and are not production labels.",
            "Expected contribution is a transparent rule-based estimate, not a trained probability prediction.",
        ],
        "scenarios": scenarios,
    }


def main() -> None:
    dataset = build_dataset()
    OUTPUT.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {dataset['selection']['scenario_count']} scenarios and "
        f"{dataset['selection']['candidate_count']} candidates to {OUTPUT}"
    )


if __name__ == "__main__":
    main()
