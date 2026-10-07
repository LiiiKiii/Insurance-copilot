"""Knowledge Layer: search_sales_scripts — conversation templates for sales scenarios."""
import json
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool


SCENARIO_KEYWORDS = {
    "objection": ["think about it", "objection", "refuse", "expensive", "too costly"],
    "needs_analysis": ["needs", "fabe", "analysis", "protection gap", "coverage gap"],
    "referral": ["referral", "introduction", "friend", "recommendation"],
    "upsell": ["additional coverage", "existing client", "upsell", "upgrade"],
    "closing": ["close", "closing", "commit", "sign", "purchase"],
}


class SearchSalesScriptsTool(Tool):
    """Search for proven sales scripts for specific conversation scenarios.
    Part of Knowledge Layer — returns word-for-word scripts with usage guidance."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "search_sales_scripts"

    @property
    def description(self) -> str:
        return (
            "Search sales scripts for a specific customer conversation. "
            "Supported scenarios include objection handling, FABE needs analysis, "
            "referrals, additional coverage for existing clients, and closing."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": "Scenario such as 'objection_handling', 'needs_analysis', 'referral', 'upsell', or 'closing'",
                },
                "product_type": {
                    "type": "string",
                    "description": "Optional product type such as protection, savings, or critical illness",
                },
            },
            "required": ["scenario"],
        }

    async def execute(self, **kwargs: Any) -> str:
        scenario = kwargs["scenario"].lower()
        scripts_path = self._workspace / "data" / "knowledge" / "sales_scripts.md"

        if not scripts_path.exists():
            return json.dumps({"error": "The sales-script knowledge document is unavailable"})

        content = scripts_path.read_text(encoding="utf-8")
        sections = content.split("\n## ")

        matched = []
        for section in sections[1:]:
            section_lower = section.lower()
            for key, keywords in SCENARIO_KEYWORDS.items():
                if key in scenario or any(kw in scenario for kw in keywords):
                    if any(kw in section_lower for kw in keywords):
                        matched.append(section.strip())
                        break

        if not matched:
            matched = [sections[1].strip()] if len(sections) > 1 else []

        return json.dumps({
            "scenario": kwargs["scenario"],
            "product_type": kwargs.get("product_type", ""),
            "matched_count": len(matched),
            "scripts": matched[:2],
        }, ensure_ascii=False, indent=2)
