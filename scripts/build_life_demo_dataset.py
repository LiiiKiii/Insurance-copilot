"""Build a coherent synthetic life-insurance demo without reinterpreting source money."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/source/agencyperformance-50-v1.zip"
FILES = ("agents", "performance", "policies", "clients", "assessments", "attribution", "competitions")
AS_OF = date(2026, 10, 23)
PRODUCTS = ("Term Life", "Whole Life", "Critical Illness", "Medical Insurance")
ORIGIN = "synthetic_life_demo_not_kaggle_financial_data"


def load_source(name: str):
    manifest = json.loads(SOURCE.with_suffix(".json").read_text(encoding="utf-8"))
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Source snapshot checksum mismatch")
    with zipfile.ZipFile(SOURCE) as archive:
        return json.loads(archive.read(f"{name}.json"))


def metric(label, current, unit, target=None, peer_avg=None):
    result = {"label": label, "current": current, "target": target,
              "rate": current / target if target else None, "unit": unit,
              "description": "Synthetic life-insurance coursework value; not source financial performance."}
    if peer_avg is not None:
        result["peer_avg"] = peer_avg
    return result


def build():
    source_agents = load_source("agents")
    source_clients = load_source("clients")
    rules = json.loads((ROOT / "data/config/life_demo_rules.json").read_text(encoding="utf-8"))
    agents = deepcopy(source_agents)
    ids = {a["agent_id"] for a in agents}
    data = {name: {} for name in FILES if name != "agents"}
    data["agents"] = agents
    for i, agent in enumerate(agents):
        aid = agent["agent_id"]
        agent.update(specialties=list(PRODUCTS[i % 3:i % 3 + 2]), license_no=f"LIFE-DEMO-{i+1:03d}",
                     data_origin=ORIGIN, career_highlights=["Synthetic life-insurance demonstration profile"])
        if agent.get("supervisor_agent_id") and agent["supervisor_agent_id"] not in ids:
            raise ValueError(f"Unknown supervisor for {aid}")
        period = f"2026-01-01 to {AS_OF.isoformat()}"
        average = 24000 + (i * 1700) % 36000
        policy_count = 24 + (i * 7) % 90
        issued = average * policy_count
        fyc = round(issued * rules["synthetic_commission_rate"], 2)
        submissions = policy_count + 12 + i % 9
        retention = round(0.82 + (i % 13) * 0.01, 2)
        current_clients = 18
        clients = deepcopy(source_clients[aid]["clients"])
        for j, client in enumerate(clients):
            client.update(premium=average + j * 500, currency="HKD", data_origin=ORIGIN,
                          tag_categories=["Lifecycle", "Need", "Engagement"],
                          tag_labels=["Family" if j % 2 else "Young Professional", PRODUCTS[j % 4], "Follow-up" if j % 3 else "Renewal Due"])
        data["clients"][aid] = {"agent_id": aid, "currency": "HKD", "total_clients": current_clients,
                                "sample_count": len(clients), "sample_scope": "Complete synthetic demo register", "clients": clients}
        policies = []
        for j in range(4):
            policies.append({"policy_id": f"POL-{aid[3:]}-{j+1:03d}", "customer_id": clients[j]["client_id"],
                             "client_name": clients[j]["name"], "premium": average + j * 2000, "unit": "HKD",
                             "product": PRODUCTS[j], "product_en": PRODUCTS[j],
                             "status": "Awaiting Documents" if j == 0 else "Underwriting",
                             "submit_date": (AS_OF - timedelta(days=2 + j * 3)).isoformat(),
                             "estimated_approval_days_min": 3, "estimated_approval_days_max": 10,
                             "data_origin": ORIGIN})
        pending = sum(p["premium"] for p in policies)
        data["policies"][aid] = {"agent_id": aid, "currency": "HKD", "as_of_date": AS_OF.isoformat(),
                                 "total_pending_premium": pending, "total_count": 4, "pending_count": 4, "policies": policies}
        metrics = {
            "protection_premium": metric("Issued protection premium", issued, "HKD", 3200000),
            "pending_premium": metric("Pending protection premium", pending, "HKD"),
            "avg_case_size": metric("Average case premium", average, "HKD", 50000, 42000),
            "submission_count": metric("Submitted cases", submissions, "cases", 120),
            "policy_count": metric("Issued policies", policy_count, "policies"),
            "conversion_rate": metric("Submission-to-issue conversion", policy_count / submissions, "%", .75, .65),
            "new_clients": metric("New clients", 4 + i % 12, "clients", 20),
            "client_retention": metric("Client retention", retention, "%", .95),
            "fyc": metric("Eligible first-year commission (demo)", fyc, "HKD", rules["mdrt_fyc_demo_threshold"]),
            "ytd_fyc": metric("Year-to-date FYC", fyc, "HKD"),
            "quarter_fyc": metric("Quarterly FYC", round(fyc * .25, 2), "HKD"),
            "daily_fyc": metric("Daily average FYC", round(fyc / AS_OF.timetuple().tm_yday, 2), "HKD"),
            "total_clients": metric("Clients in demo register", current_clients, "clients"),
            "churn_clients": metric("Churned clients", i % 3, "clients"),
            "churn_rate": metric("Client churn", 1 - retention, "%"),
            "renewal_due_clients": metric("Renewal-due clients", 6, "clients"),
            "ai_training_usage": metric("AI training sessions", 15 + i % 16, "sessions", 24),
            "ai_practice_rate": metric("AI training completion", (15 + i % 16) / 24, "%"),
            "online_university": metric("Mandatory training", "Completed", ""),
            "no_train_no_sell": metric("Training compliance hold", False, ""),
        }
        data["performance"][aid] = {"agent_id": aid, "period": period, "as_of_date": AS_OF.isoformat(),
            "metrics": metrics, "history": {"last_month_protection_premium": round(issued / 10),
            "last_quarter_protection_premium": round(issued / 4), "last_year_protection_premium": round(issued * .9)},
            "team_breakdown": {"personal_premium": issued, "subordinate_premium": 0},
            "training_compliance": {"no_train_no_sell": False, "online_university": "Completed"},
            "data_origin": {"identity_keys": "Preserved from the original 50-agent project snapshot",
                            "financial_performance": ORIGIN, "qualification": "Illustrative demo, not verified professional eligibility"}}
        data["assessments"][aid] = {"agent_id": aid, "currency": "HKD", "assessments": [
            {"subject": metrics[k]["label"], "unit": metrics[k]["unit"], "current_value": metrics[k]["current"],
             "target_value": metrics[k]["target"], "status": "Met" if metrics[k]["current"] >= metrics[k]["target"] else "Needs Attention",
             "remark": "Synthetic coursework assessment; not a professional qualification decision."}
            for k in ["protection_premium", "fyc", "avg_case_size"]]}
        comps = []
        definitions = [
            ("LIFE_DEMO_STARLIGHT_2026", "Starlight Protection Premium", "competition", "protection_premium", 3200000, "HKD"),
            ("LIFE_DEMO_CASES_2026", "Case Submission Sprint", "competition", "submission_count", 120, "cases"),
            ("LIFE_DEMO_ELITE_2026", "Annual Protection Premium Challenge", "competition", "protection_premium", 5000000, "HKD"),
            ("LIFE_DEMO_MDRT_2026", "MDRT FYC Demonstration (not certification)", "honor", "fyc", rules["mdrt_fyc_demo_threshold"], "HKD"),
            ("LIFE_DEMO_COT_2026", "COT FYC Demonstration (not certification)", "honor", "fyc", rules["cot_fyc_demo_threshold"], "HKD"),
        ]
        for cid, name, kind, key, target, unit in definitions:
            current = metrics[key]["current"]
            comps.append({"id": cid, "name": name, "name_en": name, "type": kind, "target_metric": key,
                          "target_value": target, "current_value": current, "gap": max(target-current, 0),
                          "unit": unit, "deadline": rules["deadline"], "status": "achieved" if current >= target else "active",
                          "data_origin": ORIGIN, "description": "Illustrative life-insurance coursework target; pending business is not achieved production."})
        data["competitions"][aid] = {"agent_id": aid, "pending_policies": deepcopy(data["policies"][aid]), "competitions": comps}
        data["attribution"][aid] = {"agent_id": aid, "period": period, "currency": "HKD", "data_origin": ORIGIN,
            "key_metrics": {"label": "Synthetic behaviour metrics", "dimensions": [
                {"name": "Average Case Size", "name_en": "Average Case Size", "current": average, "peer_avg": 42000, "unit": "HKD"},
                {"name": "Conversion Rate", "name_en": "Conversion Rate", "current": policy_count/submissions, "peer_avg": .65, "unit": "%"}]},
            "policy_type": {"label": "Synthetic product mix", "data": {p: .25 for p in PRODUCTS}, "peer_avg": {p: .25 for p in PRODUCTS}},
            "product_details": [{"product_name": p, "category": p, "premium": issued / 4, "commission_rate": rules["synthetic_commission_rate"], "currency": "HKD"} for p in PRODUCTS]}
        data["attribution"][aid].update(
            lead_followup={"label": "Synthetic follow-up", "data": {"followup_rate": .60 + (i % 6) * .04}, "peer_avg": {"followup_rate": .80}},
            activity={"label": "Synthetic client activity", "data": {"monthly_meetings": 8 + i % 12}, "peer_avg": {"monthly_meetings": 16}},
            training={"label": "Synthetic training", "data": {"sessions": metrics["ai_training_usage"]["current"]}, "peer_avg": {"sessions": 24}},
            peer_comparison={"label": "Synthetic cohort context", "team_size": len(agents), "insight": "All business observations are synthetic coursework fixtures."},
        )
    for agent in agents:
        aid = agent["agent_id"]
        data["performance"][aid]["team_breakdown"]["subordinate_premium"] = sum(
            data["performance"][a["agent_id"]]["metrics"]["protection_premium"]["current"]
            for a in agents if a.get("supervisor_agent_id") == aid)
    validate(data)
    return data


def validate(data):
    ids = {a["agent_id"] for a in data["agents"]}
    if len(ids) != 50 or len(data["agents"]) != 50:
        raise ValueError("Expected 50 unique agents")
    for name in FILES[1:]:
        if set(data[name]) != ids:
            raise ValueError(f"Agent-key mismatch in {name}")
    policy_ids = set()
    for aid in ids:
        for name in FILES[1:]:
            if data[name][aid].get("agent_id") != aid:
                raise ValueError(f"Embedded agent-key mismatch in {name}")
        for key, value in data["performance"][aid]["metrics"].items():
            current, target = value.get("current"), value.get("target")
            if isinstance(current, (int, float)) and not math.isfinite(current):
                raise ValueError(f"Nonfinite metric for {aid}.{key}")
            if target is not None and (not math.isfinite(target) or target < 0):
                raise ValueError(f"Invalid target for {aid}.{key}")
            if value.get("unit") == "USD":
                raise ValueError(f"Mixed business currency for {aid}.{key}")
            if target and isinstance(current, (int, float)) and not math.isclose(value["rate"], current / target):
                raise ValueError(f"Metric rate mismatch for {aid}.{key}")
        clients = {c["client_id"] for c in data["clients"][aid]["clients"]}
        if len(clients) != len(data["clients"][aid]["clients"]):
            raise ValueError(f"Duplicate client for {aid}")
        for policy in data["policies"][aid]["policies"]:
            if policy["policy_id"] in policy_ids:
                raise ValueError("Duplicate policy identifier")
            policy_ids.add(policy["policy_id"])
            if policy["unit"] != "HKD":
                raise ValueError("Policy currency mismatch")
        policies = data["policies"][aid]
        if any(p["customer_id"] not in clients for p in policies["policies"]):
            raise ValueError(f"Policy-client mismatch for {aid}")
        total = sum(p["premium"] for p in policies["policies"])
        if total != policies["total_pending_premium"] or total != data["performance"][aid]["metrics"]["pending_premium"]["current"]:
            raise ValueError(f"Pending reconciliation failed for {aid}")
        for comp in data["competitions"][aid]["competitions"]:
            m = data["performance"][aid]["metrics"][comp["target_metric"]]
            if (m["unit"] != comp["unit"] or m["current"] != comp["current_value"]
                    or comp["gap"] != max(comp["target_value"] - comp["current_value"], 0)):
                raise ValueError(f"Competition metric mismatch for {aid}")


def write(output):
    data = build()
    output.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        (output / f"{name}.json").write_text(json.dumps(data[name], ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    manifest = {"dataset_id": "life-demo-50-v1", "as_of_date": AS_OF.isoformat(), "currency": "HKD",
        "origin": ORIGIN, "source_usage": "Only stable fictional identities and client identifiers are reused. No USD source amount is converted or relabelled.",
        "legacy_accounts": "AGT001/AGT002/AGT003/AGT_TL01 belong to the retired four-agent seed; existing database accounts are not deleted or aliased.",
        "record_counts": {"agents": 50, "clients": 900, "policies": 200, "assessments": 150, "competitions": 5, "competition_entries": 250},
        "sha256": {f"{name}.json": hashlib.sha256((output/f"{name}.json").read_bytes()).hexdigest() for name in FILES}}
    (output/"dataset_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"data/mock")
    args = parser.parse_args()
    print(json.dumps(write(args.output), indent=2))
