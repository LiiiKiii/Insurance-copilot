"""Retrieve raw competition and honour status from the database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

from ._db import db_error, load_competitions_from_db


class GetCompetitionStatusTool(Tool):
    """Return active competition entries without feasibility reasoning."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "get_competition_status"

    @property
    def description(self) -> str:
        return (
            "[Data Layer] Retrieve an agent's active competitions and honours. "
            "Return target, current value, gap, deadline, remaining days, and "
            "status for every matching entry. Do not assess feasibility."
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
                "competition_id": {
                    "type": "string",
                    "description": "Optional competition ID; omit to return all entries",
                },
                "include_honors": {
                    "type": "boolean",
                    "description": "Whether honour entries are included; defaults to true",
                },
            },
            "required": ["agent_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        agent_id = kwargs["agent_id"]
        competition_id = kwargs.get("competition_id")
        include_honors = kwargs.get("include_honors", True)

        try:
            competitions = load_competitions_from_db(self._workspace, agent_id)
        except Exception as exc:
            return db_error(exc)

        if not include_honors:
            competitions = [item for item in competitions if item["type"] != "honor"]
        if competition_id:
            competitions = [item for item in competitions if item["id"] == competition_id]

        competitions.sort(
            key=lambda item: (
                item["days_remaining"] is None,
                item["days_remaining"] if item["days_remaining"] is not None else 0,
            )
        )

        return json.dumps(
            {
                "agent_id": agent_id,
                "total": len(competitions),
                "competitions": competitions,
            },
            indent=2,
        )
