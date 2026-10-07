"""Knowledge Layer: search_best_practice — proven sales strategies and success cases."""
import json
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool


TOPIC_KEYWORDS = {
    "case_size": ["case size", "average premium", "low premium", "coverage amount"],
    "conversion": ["conversion", "closing rate", "follow-up", "lead"],
    "mdrt": ["mdrt", "million dollar round table", "milestone"],
    "sprint": ["sprint", "deadline", "last 30 days", "final month"],
    "existing_client": ["existing client", "additional coverage", "renewal", "referral"],
    "lead": ["lead", "follow-up", "prospect", "pipeline"],
}


class SearchBestPracticeTool(Tool):
    """Search for proven best practices and success strategies from knowledge base.
    Part of Knowledge Layer — returns relevant strategies with examples."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "search_best_practice"

    @property
    def description(self) -> str:
        return (
            "Search proven insurance sales practices and success strategies. "
            "Covers average premium improvement, lead conversion, competition sprints, "
            "MDRT progress, and additional coverage for existing clients."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic such as 'low average premium', 'MDRT sprint', 'low lead conversion', or 'last 30 days of a competition'",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context such as the agent's role or a specific business issue",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, **kwargs: Any) -> str:
        topic = kwargs["topic"].lower()
        bp_path = self._workspace / "data" / "knowledge" / "best_practices.md"

        if not bp_path.exists():
            return json.dumps({"error": "The best-practice knowledge document is unavailable"})

        content = bp_path.read_text(encoding="utf-8")
        sections = content.split("\n## ")

        matched = []
        for section in sections[1:]:  # Skip title
            section_lower = section.lower()
            for key, keywords in TOPIC_KEYWORDS.items():
                if key in topic or any(kw in topic for kw in keywords):
                    if any(kw in section_lower for kw in keywords):
                        matched.append(section.strip())
                        break

        if not matched:
            # Return first 2 sections as fallback
            matched = [s.strip() for s in sections[1:3]]

        return json.dumps({
            "topic": kwargs["topic"],
            "matched_count": len(matched),
            "practices": matched[:3],
        }, ensure_ascii=False, indent=2)
