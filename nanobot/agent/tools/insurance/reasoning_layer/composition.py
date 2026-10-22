"""Explicit composition of the insurance workbench tool registry."""

from pathlib import Path

from nanobot.agent.tools.insurance.data_layer.attribution import (
    GetAttributionAnalysisTool,
)
from nanobot.agent.tools.insurance.data_layer.competition import (
    GetCompetitionStatusTool,
)
from nanobot.agent.tools.insurance.data_layer.pending import GetPendingPoliciesTool
from nanobot.agent.tools.insurance.data_layer.performance import (
    GetPerformanceSnapshotTool,
)
from nanobot.agent.tools.insurance.knowledge_layer.best_practice import (
    SearchBestPracticeTool,
)
from nanobot.agent.tools.insurance.knowledge_layer.competition_rules import (
    SearchCompetitionRulesTool,
)
from nanobot.agent.tools.insurance.knowledge_layer.sales_scripts import (
    SearchSalesScriptsTool,
)
from nanobot.agent.tools.insurance.knowledge_layer.search_kb import (
    SearchKnowledgeBaseTool,
)
from nanobot.agent.tools.insurance.planning_layer.chase_plan import (
    GenerateChasePlanTool,
)
from nanobot.agent.tools.insurance.planning_layer.improvement_advice import (
    GenerateImprovementAdviceTool,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    PrioritizeFollowupsTool,
)
from nanobot.agent.tools.insurance.reasoning_layer.tools import (
    AssessGapFeasibilityTool,
    CalculateRunRateTool,
)
from nanobot.agent.tools.registry import ToolRegistry


def build_reasoning_registry(workspace: Path | None = None) -> ToolRegistry:
    """Build the complete, explicit tool registry for the insurance workbench."""
    workspace = workspace or Path.cwd()
    registry = ToolRegistry()
    registry.register(GetPerformanceSnapshotTool(workspace))
    registry.register(GetCompetitionStatusTool(workspace))
    registry.register(GetPendingPoliciesTool(workspace))
    registry.register(GetAttributionAnalysisTool(workspace))
    registry.register(CalculateRunRateTool())
    registry.register(AssessGapFeasibilityTool())
    registry.register(SearchCompetitionRulesTool(workspace))
    registry.register(SearchBestPracticeTool(workspace))
    registry.register(SearchSalesScriptsTool(workspace))
    registry.register(SearchKnowledgeBaseTool(workspace))
    registry.register(GenerateChasePlanTool(workspace))
    registry.register(GenerateImprovementAdviceTool(workspace))
    registry.register(PrioritizeFollowupsTool())
    return registry
