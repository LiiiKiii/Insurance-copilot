"""HTTP boundary for the existing template-based planning tools.

The endpoints in this module expose the A1/A2 planning baseline without
changing its business logic.  Candidate scoring and Top-K optimisation remain
outside the A3 scope and are documented as a future interface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from admin.utils import get_workspace


router = APIRouter(prefix="/api/planning", tags=["planning"])


class ChasePlanRequest(BaseModel):
    """Input accepted by the existing chase-plan tool."""

    agent_id: str = Field(min_length=1)
    competition_id: str | None = None


class ImprovementAdviceRequest(BaseModel):
    """Input accepted by the existing improvement-advice tool."""

    agent_id: str = Field(min_length=1)
    top_n: int = Field(default=5, ge=1, le=50)


class PlanningTool(Protocol):
    """Small execution boundary shared by the two planning endpoints."""

    async def execute(self, **kwargs: Any) -> str: ...


def _build_chase_plan_tool(workspace: Path) -> PlanningTool:
    # Keep tool imports lazy so application construction does not query data or
    # initialise the agent runtime.
    from nanobot.agent.tools.insurance.planning_layer.chase_plan import (
        GenerateChasePlanTool,
    )

    return GenerateChasePlanTool(workspace)


def _build_improvement_advice_tool(workspace: Path) -> PlanningTool:
    from nanobot.agent.tools.insurance.planning_layer.improvement_advice import (
        GenerateImprovementAdviceTool,
    )

    return GenerateImprovementAdviceTool(workspace)


def _decode_tool_result(result: str) -> dict[str, Any]:
    """Convert a tool's JSON contract into an API response object."""
    try:
        payload = json.loads(result)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Planning tool returned an invalid response",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail="Planning tool returned an invalid response",
        )
    return payload


@router.post("/chase-plan")
async def generate_chase_plan(request: ChasePlanRequest) -> dict[str, Any]:
    """Generate the existing deterministic competition catch-up plan."""
    tool = _build_chase_plan_tool(get_workspace())
    result = await tool.execute(
        agent_id=request.agent_id,
        competition_id=request.competition_id,
    )
    return _decode_tool_result(result)


@router.post("/improvement-advice")
async def generate_improvement_advice(
    request: ImprovementAdviceRequest,
) -> dict[str, Any]:
    """Generate the existing template-based diagnostic advice."""
    tool = _build_improvement_advice_tool(get_workspace())
    result = await tool.execute(
        agent_id=request.agent_id,
        top_n=request.top_n,
    )
    return _decode_tool_result(result)
