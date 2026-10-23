"""Insurance intent Skills; these guide registered Tools but never execute them."""

from .base import InsuranceSkill
from .registry import SkillRegistry
from .query_single_target_gap import QuerySingleTargetGapSkill
from .diagnose_performance_gap import DiagnosePerformanceGapSkill
from .check_feasibility import CheckFeasibilitySkill
from .decompose_goal_and_advise import DecomposeGoalSkill
from .analyze_underperformance import AnalyzeUnderperformanceSkill

__all__ = [
    "InsuranceSkill", "SkillRegistry", "QuerySingleTargetGapSkill",
    "DiagnosePerformanceGapSkill", "CheckFeasibilitySkill", "DecomposeGoalSkill",
    "AnalyzeUnderperformanceSkill",
]
