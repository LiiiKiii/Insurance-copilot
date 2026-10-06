"""Retrieve raw agent performance metrics from the database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

from ._db import db_error, load_performance_row


class GetPerformanceSnapshotTool(Tool):
    """Return current, target, and completion values without reasoning."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "get_performance_snapshot"

    @property
    def description(self) -> str:
        return (
            "[Data Layer] Retrieve an agent's raw performance snapshot. "
            "Return every requested metric with its current value, target, "
            "completion rate, unit, and description. Do not infer causes or "
            "make recommendations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID, for example AGT001",
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional metric keys. Leave empty to return all metrics. "
                        "Supported keys include protection_premium, pending_premium, "
                        "submission_count, policy_count, quarter_fyc, ytd_fyc, "
                        "daily_fyc, avg_fyc_per_policy, conversion_rate, new_clients, "
                        "total_clients, churn_rate, client_retention, "
                        "ai_training_usage, ai_practice_rate, and online_university."
                    ),
                },
            },
            "required": ["agent_id"],
        }

    @staticmethod
    def _metric_map() -> dict[str, dict[str, Any]]:
        """Map public metric keys to ORM attributes and display metadata."""
        return {
            "protection_premium": {
                "label": "MDRT annual credit",
                "unit": "Credit",
                "current_col": "protection_premium_current",
                "target_col": "protection_premium_target",
                "rate_col": "protection_premium_rate",
                "description": (
                    "Annual MDRT credit. This is a points-based measure and must "
                    "not be treated as HKD premium."
                ),
            },
            "pending_premium": {
                "label": "Pending premium",
                "unit": "HKD",
                "current_col": "pending_premium_current",
                "target_col": None,
                "rate_col": None,
                "description": "Total submitted premium still awaiting underwriting approval.",
            },
            "submission_count": {
                "label": "Submissions",
                "unit": "cases",
                "current_col": "submission_count_current",
                "target_col": "submission_count_target",
                "rate_col": "submission_count_rate",
                "description": "Submitted cases, including issued and pending policies.",
            },
            "policy_count": {
                "label": "Issued policies",
                "unit": "policies",
                "current_col": "policy_count",
                "target_col": None,
                "rate_col": None,
                "description": "Policies successfully issued after underwriting.",
            },
            "quarter_fyc": {
                "label": "Quarterly FYC",
                "unit": "HKD",
                "current_col": "quarter_fyc",
                "target_col": None,
                "rate_col": None,
                "description": "First-year commission accumulated this quarter.",
            },
            "ytd_fyc": {
                "label": "Year-to-date FYC",
                "unit": "HKD",
                "current_col": "ytd_fyc",
                "target_col": None,
                "rate_col": None,
                "description": "First-year commission accumulated year to date.",
            },
            "daily_fyc": {
                "label": "Daily average FYC",
                "unit": "HKD/day",
                "current_col": "daily_fyc",
                "target_col": None,
                "rate_col": None,
                "description": "Recent average daily first-year commission output.",
            },
            "conversion_rate": {
                "label": "Conversion rate",
                "unit": "%",
                "current_col": "conversion_rate_current",
                "target_col": "conversion_rate_target",
                "rate_col": "conversion_rate_rate",
                "peer_avg_col": "conversion_rate_peer_avg",
                "description": "Share of client discussions that become issued policies.",
            },
            "new_clients": {
                "label": "New clients",
                "unit": "clients",
                "current_col": "new_clients_current",
                "target_col": "new_clients_target",
                "rate_col": "new_clients_rate",
                "description": "New clients acquired during the reporting year.",
            },
            "client_retention": {
                "label": "Client retention",
                "unit": "%",
                "current_col": "client_retention_current",
                "target_col": "client_retention_target",
                "rate_col": "client_retention_rate",
                "description": "Share of existing clients retained.",
            },
            "total_clients": {
                "label": "Total clients",
                "unit": "clients",
                "current_col": "total_clients",
                "target_col": None,
                "rate_col": None,
                "description": "Total clients assigned to the agent.",
            },
            "churn_rate": {
                "label": "Client churn rate",
                "unit": "%",
                "current_col": "churn_rate",
                "target_col": None,
                "rate_col": None,
                "description": "Client churn expressed as a decimal ratio.",
            },
            "ai_training_usage": {
                "label": "AI coaching sessions",
                "unit": "sessions",
                "current_col": "ai_training_usage_current",
                "target_col": "ai_training_usage_target",
                "rate_col": "ai_training_usage_rate",
                "description": "Completed AI-assisted sales coaching sessions.",
            },
            "ai_practice_rate": {
                "label": "AI coaching completion",
                "unit": "%",
                "current_col": "ai_practice_rate",
                "target_col": None,
                "rate_col": None,
                "description": "AI coaching course completion as a decimal ratio.",
            },
            "online_university": {
                "label": "Online university status",
                "unit": "",
                "current_col": "online_university",
                "target_col": None,
                "rate_col": None,
                "description": "Mandatory training completion status.",
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        agent_id = kwargs["agent_id"]
        requested = set(kwargs.get("metrics") or [])

        try:
            row = load_performance_row(agent_id)
        except Exception as exc:
            return db_error(exc)

        if row is None:
            return json.dumps({"error": f"No performance data found for agent {agent_id}"})

        result: dict[str, Any] = {}
        for key, metadata in self._metric_map().items():
            if requested and key not in requested:
                continue

            current_column = metadata.get("current_col")
            target_column = metadata.get("target_col")
            rate_column = metadata.get("rate_col")
            entry: dict[str, Any] = {
                "label": metadata["label"],
                "unit": metadata["unit"],
                "current": getattr(row, current_column, None) if current_column else None,
                "target": getattr(row, target_column, None) if target_column else None,
                "rate": getattr(row, rate_column, None) if rate_column else None,
                "description": metadata["description"],
            }
            peer_column = metadata.get("peer_avg_col")
            if peer_column:
                entry["peer_avg"] = getattr(row, peer_column, None)
            result[key] = entry

        if not requested or "avg_fyc_per_policy" in requested:
            ytd_fyc = row.ytd_fyc or row.fyc_current
            policy_count = row.policy_count
            if ytd_fyc is not None and policy_count:
                result["avg_fyc_per_policy"] = {
                    "label": "Average FYC per policy",
                    "unit": "HKD",
                    "current": round(ytd_fyc / policy_count, 2),
                    "target": None,
                    "rate": None,
                    "description": (
                        "Year-to-date FYC divided by issued policy count. This is "
                        "average commission, not average premium."
                    ),
                }

        return json.dumps(
            {
                "agent_id": agent_id,
                "period": f"{row.period_start} to {row.period_end}",
                "metrics": result,
            },
            indent=2,
        )
