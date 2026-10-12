"""Explicit composition of the deterministic insurance reasoning tools."""

from nanobot.agent.tools.insurance.reasoning_layer.tools import (
    AssessGapFeasibilityTool,
    CalculateRunRateTool,
)
from nanobot.agent.tools.registry import ToolRegistry


def build_reasoning_registry() -> ToolRegistry:
    """Build the deliberately small, explicit registry for A3-M1 reasoning."""
    registry = ToolRegistry()
    registry.register(CalculateRunRateTool())
    registry.register(AssessGapFeasibilityTool())
    return registry
