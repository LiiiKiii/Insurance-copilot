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
BLIND_OUTPUT = ROOT / "data" / "evaluation" / "m2_candidate_blind.json"
AS_OF = date(2026, 5, 31)
SCENARIO_COUNT = 10
TENANT_ID = "coursework-demo"
POLICIES_PER_SCENARIO = 4
CLIENTS_PER_SCENARIO = 6
NEED_PRODUCT = {
    "Motor": "Private Motor Insurance",
    "Property": "Home Contents Insurance",
    "Commercial": "SME Business Package",
    "Liability": "Public Liability Insurance",
    "Specialty": "Personal Liability Insurance",
}

# These profiles vary only the coursework evaluation context. The original
# project policy status remains available as ``source_policy_status``.
POLICY_STATES = {
    "documents": {
        "status": "Awaiting Documents",
        "signal": "Customer documents are incomplete; the agent can request them now.",
        "action": "Contact the customer and obtain the missing documents.",
        "days": 1, "urgency": 0.95, "actionability": 0.98, "eligible": True,
    },
    "query": {
        "status": "Underwriter Query",
        "signal": "The underwriter has an unanswered question for the agent.",
        "action": "Answer the underwriter query and provide supporting evidence.",
        "days": 2, "urgency": 0.88, "actionability": 0.92, "eligible": True,
    },
    "confirmation": {
        "status": "Client Confirmation Pending",
        "signal": "Quoted terms are ready and the client must confirm acceptance.",
        "action": "Call the client to confirm the quoted terms.",
        "days": 4, "urgency": 0.76, "actionability": 0.86, "eligible": True,
    },
    "underwriting": {
        "status": "Underwriting",
        "signal": "The case is being reviewed and has no outstanding request.",
        "action": "Monitor the case and prepare for the next review point.",
        "days": 8, "urgency": 0.42, "actionability": 0.38, "eligible": True,
    },
    "approved": {
        "status": "Approved",
        "signal": "The policy is approved and no follow-up is currently required.",
        "action": "No current action.",
        "days": None, "urgency": 0.10, "actionability": 0.10, "eligible": False,
    },
    "withdrawn": {
        "status": "Withdrawn",
        "signal": "The case has been withdrawn and is closed.",
        "action": "No current action.",
        "days": None, "urgency": 0.0, "actionability": 0.0, "eligible": False,
    },
}

POLICY_PROFILE_MATRIX = (
    ("documents", "query", "approved", "withdrawn"),
    ("documents", "confirmation", "underwriting", "approved"),
    ("query", "confirmation", "underwriting", "documents"),
    ("confirmation", "underwriting", "approved", "withdrawn"),
    ("documents", "query", "underwriting", "withdrawn"),
    ("query", "confirmation", "underwriting", "documents"),
    ("documents", "underwriting", "approved", "withdrawn"),
    ("query", "confirmation", "underwriting", "approved"),
    ("documents", "query", "confirmation", "underwriting"),
    ("documents", "confirmation", "underwriting", "withdrawn"),
)

CLIENT_ACTIONS = {
    "renewal": {
        "signal": "Renewal decision is due within three days.",
        "action": "Review cover and confirm renewal with the client.",
        "days": 3, "urgency": 0.90, "actionability": 0.86,
        "eligible": True, "permission": True, "compliance": True,
    },
    "callback": {
        "signal": "The client requested a callback today.",
        "action": "Return the client's call and record the outcome.",
        "days": 0, "urgency": 0.98, "actionability": 0.98,
        "eligible": True, "permission": True, "compliance": True,
    },
    "quote": {
        "signal": "The client requested a quotation within five days.",
        "action": "Confirm needs and prepare the requested quotation.",
        "days": 5, "urgency": 0.78, "actionability": 0.90,
        "eligible": True, "permission": True, "compliance": True,
    },
    "review": {
        "signal": "A coverage review is scheduled within fourteen days.",
        "action": "Prepare the coverage review and contact the client.",
        "days": 14, "urgency": 0.55, "actionability": 0.74,
        "eligible": True, "permission": True, "compliance": True,
    },
    "none": {
        "signal": "There is no current customer request or due event.",
        "action": "No current action.",
        "days": None, "urgency": 0.20, "actionability": 0.20,
        "eligible": False, "permission": True, "compliance": True,
    },
    "permission": {
        "signal": "A follow-up exists, but contact permission is not recorded.",
        "action": "Resolve ownership or permission before contacting the client.",
        "days": 2, "urgency": 0.82, "actionability": 0.80,
        "eligible": True, "permission": False, "compliance": True,
    },
    "compliance": {
        "signal": "A follow-up exists, but the product compliance gate is blocking contact.",
        "action": "Resolve the compliance hold before contacting the client.",
        "days": 2, "urgency": 0.84, "actionability": 0.82,
        "eligible": True, "permission": True, "compliance": False,
    },
}

CLIENT_PROFILE_MATRIX = (
    ("callback", "renewal", "quote", "review", "none", "permission"),
    ("renewal", "callback", "review", "none", "permission", "compliance"),
    ("callback", "quote", "none", "none", "permission", "compliance"),
    ("quote", "callback", "review", "renewal", "none", "compliance"),
    ("callback", "quote", "renewal", "none", "permission", "none"),
    ("renewal", "review", "none", "permission", "compliance", "none"),
    ("review", "quote", "callback", "renewal", "permission", "none"),
    ("quote", "renewal", "review", "none", "compliance", "none"),
    ("callback", "review", "none", "permission", "none", "compliance"),
    ("renewal", "callback", "quote", "none", "permission", "compliance"),
)


def load(name: str) -> Any:
    return json.loads((ROOT / "data" / "mock" / name).read_text(encoding="utf-8"))


def bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def action_deadline(days: int | None) -> str | None:
    return (AS_OF + timedelta(days=days)).isoformat() if days is not None else None


def stable_tags(client: dict[str, Any]) -> list[str]:
    """Remove transient template signals; scenario evidence is stored separately."""
    transient = {"Renewal Due", "Follow-up", "Active"}
    return [tag for tag in client["tag_labels"] if tag not in transient]


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


def common_fields(
    agent_id: str,
    candidate_id: str,
    permission_allowed: bool,
    compliance_allowed: bool,
) -> dict[str, Any]:
    return {
        "scenario_id": f"SCN-{agent_id}",
        "agent_id": agent_id,
        "candidate_id": candidate_id,
        "currency": "USD",
        "tenant_id": TENANT_ID,
        "owner_agent_id": agent_id,
        "permission_allowed": permission_allowed,
        "permission_information": {
            "decision": permission_allowed,
            "basis": (
                "Candidate belongs to the same tenant and agent"
                if permission_allowed
                else "Contact permission is deliberately absent in this evaluation case"
            ),
        },
        "compliance_allowed": compliance_allowed,
        "compliance_information": {
            "decision": compliance_allowed,
            "basis": (
                "No compliance restriction blocks this follow-up"
                if compliance_allowed
                else "A deliberate product-compliance hold blocks this evaluation case"
            ),
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
        agent_compliant = not bool(performance["training_compliance"]["no_train_no_sell"])
        if not agent_compliant:
            raise ValueError(f"Selected scenario agent {agent_id} is compliance-blocked")
        candidates: list[dict[str, Any]] = []

        for policy_index, policy in enumerate(policies):
            client = clients[policy["customer_id"]]
            tags = set(stable_tags(client))
            profile_name = POLICY_PROFILE_MATRIX[scenario_index][policy_index]
            profile = POLICY_STATES[profile_name]
            eligible = bool(profile["eligible"] and policy["premium"] > 0)
            candidate = {
                **common_fields(agent_id, policy["policy_id"], True, True),
                "candidate_type": "policy",
                "premium": float(policy["premium"]),
                "expected_contribution": round(float(policy["premium"]) * conversion, 2),
                "policy_status": profile["status"],
                "source_policy_status": policy["status"],
                "submit_date": policy["submit_date"],
                "estimated_approval_days": {
                    "min": int(policy["estimated_approval_days_min"]),
                    "max": int(policy["estimated_approval_days_max"]),
                },
                "expected_decision_date": action_deadline(profile["days"]),
                "action_deadline": action_deadline(profile["days"]),
                "action_signal": profile["signal"],
                "recommended_action": profile["action"],
                "client_tags": stable_tags(client),
                "source_client_tags": client["tag_labels"],
                "product_type": policy["product"],
                "eligible": eligible,
                "eligibility_information": {
                    "decision": eligible,
                    "basis": (
                        "Scenario has a current action and the premium is positive"
                        if eligible else "Scenario is closed or has no current action"
                    ),
                },
                "urgency": profile["urgency"],
                "actionability": profile["actionability"],
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
                    "scenario_evidence": "synthetic_coursework_scenario_profile",
                    "scores": "deterministic_derived",
                },
            }
            candidates.append(candidate)

        linked_clients = {row["customer_id"] for row in policies}
        available_clients = [
            row for row in client_rows if row["client_id"] not in linked_clients
        ]
        available_clients.sort(key=lambda row: row["client_id"])
        start = (scenario_index * 3) % len(available_clients)
        client_candidates = [
            available_clients[(start + offset * 2) % len(available_clients)]
            for offset in range(CLIENTS_PER_SCENARIO)
        ]
        if len({row["client_id"] for row in client_candidates}) != CLIENTS_PER_SCENARIO:
            raise ValueError(f"{agent_id} cannot provide six distinct client candidates")

        for client_index, client in enumerate(client_candidates):
            tags = set(stable_tags(client))
            category = need_category(tags)
            product = NEED_PRODUCT.get(category or "", agent["specialties"][0])
            profile_name = CLIENT_PROFILE_MATRIX[scenario_index][client_index]
            profile = CLIENT_ACTIONS[profile_name]
            candidate = {
                **common_fields(
                    agent_id,
                    client["client_id"],
                    profile["permission"],
                    profile["compliance"],
                ),
                "candidate_type": "client",
                "premium": float(client["premium"]),
                "expected_contribution": round(float(client["premium"]) * retention, 2),
                "policy_status": None,
                "submit_date": None,
                "estimated_approval_days": None,
                "expected_decision_date": None,
                "not_applicable_reason": "Client follow-up candidate; no pending policy attached",
                "action_deadline": action_deadline(profile["days"]),
                "action_signal": profile["signal"],
                "recommended_action": profile["action"],
                "client_tags": stable_tags(client),
                "source_client_tags": client["tag_labels"],
                "product_type": product,
                "eligible": profile["eligible"],
                "eligibility_information": {
                    "decision": profile["eligible"],
                    "basis": (
                        "Scenario has a current customer action"
                        if profile["eligible"] else "No current customer action"
                    ),
                },
                "urgency": profile["urgency"],
                "actionability": profile["actionability"],
                "business_fit": business_fit(
                    tags, product, category, specialties, specialty_categories
                ),
                "source_record_id": client["client_id"],
                "source_path": f"data/mock/clients.json#{agent_id}/{client['client_id']}",
                "source_client_id": client["client_id"],
                "data_origin": {
                    "candidate_record": client["data_origin"],
                    "scenario_evidence": "synthetic_coursework_scenario_profile",
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
        "dataset_id": "m2-coursework-candidates-v3",
        "description": "Stratified coursework candidate scenarios for M4 ranking integration.",
        "as_of_date": AS_OF.isoformat(),
        "currency": "USD",
        "evaluation_k": [1, 3, 5],
        "selection": {
            "method": "First ten agent IDs in ascending order; four source-linked policies and six source-linked clients per scenario, with stratified synthetic action contexts and explicit filter controls",
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
                "agent_id", "agent_specialties", "candidate_id", "premium",
                "submit_date", "estimated_approval_days", "source_policy_status",
                "source_client_tags", "product_type", "source_record_id",
            ],
            "derived_fields": [
                "tenant_id", "owner_agent_id", "client_tags", "policy_status",
                "action_signal", "action_deadline",
                "expected_contribution", "expected_decision_date", "eligible",
                "permission_allowed", "compliance_allowed", "urgency",
                "actionability", "business_fit",
            ],
            "synthetic_record_notice": "Customer and policy records are coursework demonstration records. Candidate identity, premium and ownership are source-linked; action context and displayed policy status are stratified synthetic evaluation evidence, not individual Kaggle records or production facts.",
        },
        "transformation_rules": {
            "policy_expected_contribution": "premium multiplied by the agent historical conversion rate",
            "client_expected_contribution": "client premium multiplied by the agent retention rate",
            "urgency": "Scenario action-deadline bands, normalised to 0-1",
            "actionability": "Scenario-specific next-action clarity, normalised to 0-1",
            "business_fit": "Base 0.4 plus product-specialty, need-category, and high-value matches, capped at 1",
            "eligibility": "The scenario has a current action and positive premium where applicable",
            "permission": "Same tenant/agent ownership plus scenario contact permission",
            "compliance": "Agent and scenario product-compliance gates permit contact",
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
                "action_signal": row["action_signal"],
                "action_deadline": row["action_deadline"],
                "tenant_id": row["tenant_id"],
                "owner_agent_id": row["owner_agent_id"],
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
        "blind_version": "human-ranking-v3",
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
