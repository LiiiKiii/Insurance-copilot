"""Build the deterministic M2 coursework candidate dataset for M4.

The source dataset is agency-level. Customer and pending-policy rows in
``data/mock`` are synthetic project records derived from observed agent and
product distributions. This script preserves that lineage and adds only
deterministic, documented scoring fields.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "evaluation" / "m2_candidate_scenarios.json"
BLIND_OUTPUT = ROOT / "data" / "evaluation" / "m2_candidate_blind.json"
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

    for scenario_index, agent in enumerate(agents[:SCENARIO_COUNT]):
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
        actionable_clients.sort(key=lambda row: row["client_id"])
        filtered_clients.sort(key=lambda row: row["client_id"])
        actionable_pairs = list(combinations(actionable_clients, 2))
        if len(actionable_pairs) < SCENARIO_COUNT:
            raise ValueError(
                f"{agent_id} needs at least five independent actionable clients"
            )
        selected_actionable_clients = list(
            actionable_pairs[scenario_index % len(actionable_pairs)]
        )
        client_candidates = (
            selected_actionable_clients
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
            candidates.append(candidate)

        current = float(performance["metrics"]["protection_premium"]["current"])
        target = float(performance["metrics"]["protection_premium"]["target"])
        scenarios.append({
            "scenario_id": f"SCN-{agent_id}",
            "agent_id": agent_id,
            "agent_specialties": agent["specialties"],
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
        })

    return {
        "dataset_id": "m2-coursework-candidates-v2",
        "description": "Deterministic coursework candidate set for M4 ranking integration.",
        "as_of_date": AS_OF.isoformat(),
        "currency": "USD",
        "evaluation_k": [1, 3, 5],
        "selection": {
            "method": "First ten agent IDs in ascending order; four policies, a different deterministic pair from five actionable clients per scenario, and four filter-control clients per agent",
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
                "agent_id", "agent_specialties", "candidate_id", "premium", "policy_status",
                "submit_date", "estimated_approval_days", "client_tags",
                "product_type", "source_record_id",
            ],
            "derived_fields": [
                "expected_contribution", "expected_decision_date", "eligible",
                "permission_allowed", "compliance_allowed", "urgency",
                "actionability", "business_fit",
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
        },
        "limitations": [
            "Expected contribution is a transparent rule-based estimate, not a trained probability prediction.",
            "Final M4 relevance labels are collected independently from blinded human rankings and are not generated here.",
        ],
        "scenarios": scenarios,
    }


def build_blind_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    """Return only evidence fields needed for independent human ranking."""
    scenarios: list[dict[str, Any]] = []
    for scenario in dataset["scenarios"]:
        candidates = []
        for row in scenario["candidates"]:
            if not all(
                row[field]
                for field in ("eligible", "permission_allowed", "compliance_allowed")
            ):
                continue
            candidates.append({
                "candidate_id": row["candidate_id"],
                "candidate_type": row["candidate_type"],
                "premium": row["premium"],
                "currency": row["currency"],
                "policy_status": row["policy_status"],
                "submit_date": row["submit_date"],
                "estimated_approval_days": row["estimated_approval_days"],
                "client_tags": row["client_tags"],
                "product_type": row["product_type"],
                "eligible": row["eligible"],
                "permission_allowed": row["permission_allowed"],
                "compliance_allowed": row["compliance_allowed"],
                "source_record_id": row["source_record_id"],
            })
        scenarios.append({
            "scenario_id": scenario["scenario_id"],
            "agent_id": scenario["agent_id"],
            "agent_specialties": scenario["agent_specialties"],
            "open_gap": scenario["objective"]["open_gap"],
            "currency": scenario["objective"]["unit"],
            "deadline": scenario["objective"]["deadline"],
            "candidates": candidates,
        })
    return {
        "dataset_id": dataset["dataset_id"],
        "blind_version": "human-ranking-v2",
        "description": "Blinded evidence-only view for independent human ranking.",
        "scenarios": scenarios,
    }


def main() -> None:
    dataset = build_dataset()
    blind_dataset = build_blind_dataset(dataset)
    OUTPUT.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    BLIND_OUTPUT.write_text(
        json.dumps(blind_dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {dataset['selection']['scenario_count']} scenarios and "
        f"{dataset['selection']['candidate_count']} candidates to {OUTPUT}; "
        f"wrote blinded evidence to {BLIND_OUTPUT}"
    )


if __name__ == "__main__":
    main()
