"""Retrieve behavioural attribution data from the database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

from ._db import db_error, load_attribution_row


class GetAttributionAnalysisTool(Tool):
    """Return stored attribution dimensions without additional analysis."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "get_attribution_analysis"

    @property
    def description(self) -> str:
        return (
            "[Data Layer] Retrieve an agent's stored behavioural attribution "
            "dimensions, such as policy mix, lead follow-up, activity, training, "
            "peer comparison, and key metrics. Do not add recommendations."
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
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional dimensions. Leave empty to return all stored data. "
                        "Supported values include policy_type, lead_followup, activity, "
                        "training, peer_comparison, and key_metrics."
                    ),
                },
            },
            "required": ["agent_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        agent_id = kwargs["agent_id"]
        dimensions = set(kwargs.get("dimensions") or [])

        try:
            row = load_attribution_row(agent_id)
        except Exception as exc:
            return db_error(exc)

        if row is None:
            return json.dumps({"error": f"No attribution data found for agent {agent_id}"})

        try:
            data = json.loads(row.data_json)
        except (TypeError, json.JSONDecodeError):
            return json.dumps({"error": f"Invalid attribution data for agent {agent_id}"})

        if not isinstance(data, dict):
            return json.dumps({"error": f"Invalid attribution data for agent {agent_id}"})

        if dimensions:
            data = {
                key: value
                for key, value in data.items()
                if key in dimensions or key == "agent_id"
            }

        data["period"] = row.period
        return json.dumps(data, indent=2)
