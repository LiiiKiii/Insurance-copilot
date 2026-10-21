"""Knowledge Layer: search_competition_rules — competition and honor standards."""
import json
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool


# Keyword-to-file mapping. One keyword may map to multiple source documents.
# English summaries are listed before original circulars when both are available.
COMP_FILE_MAP: dict[str, list[str]] = {
    "written premium": ["mdrt_rules.md", "competition_elite_challenge.md", "competitions/AG25035.md"],
    "premium excellence": ["mdrt_rules.md", "competition_elite_challenge.md", "competitions/AG25035.md"],
    "portfolio quality": ["cot_rules.md"],
    "conversion quality": ["competition_starlight.md", "competitions/AG25011.md"],
    "quote-to-bind": ["competition_starlight.md", "competitions/AG25011.md"],
    "ai practice": ["competition_rookie_king.md", "competitions/AG25138.md"],
    "new business commission": ["competition_quarterly_sprint.md"],
    "commercial lines": ["competitions/AG24050.md"],
    "renewal": ["competitions/AG25030.md", "competitions/AG25129.md"],
    "pending case": ["competitions/AG25044.md"],
    "cross-line": ["competitions/AG25099.md"],
    "ag24050": ["competitions/AG24050.md"],
    "ag25011": ["competitions/AG25011.md"],
    "ag25030": ["competitions/AG25030.md"],
    "ag25035": ["competitions/AG25035.md"],
    "ag25044": ["competitions/AG25044.md"],
    "ag25099": ["competitions/AG25099.md"],
    "ag25129": ["competitions/AG25129.md"],
    "ag25138": ["competitions/AG25138.md"],
}


class SearchCompetitionRulesTool(Tool):
    """Search competition rules and honor standards from knowledge base.
    Part of Knowledge Layer — retrieves document snippets with source reference."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "search_competition_rules"

    @property
    def description(self) -> str:
        return (
            "Search competition rules, campaign circulars, and professional honour standards. "
            "Use this tool for written-premium, conversion-quality, AI-practice, "
            "new-business-commission, retention, and portfolio-quality programmes."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search terms such as 'written premium target', 'conversion quality rules', or 'AI practice sprint'",
                },
                "competition_name": {
                    "type": "string",
                    "description": "Optional competition name used to improve document matching",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"].lower()
        comp_name = (kwargs.get("competition_name") or "").lower()
        kb_dir = self._workspace / "data" / "knowledge"
        comp_dir = kb_dir / "competitions"

        # Find matching files from predefined map
        matched_files: list[Path] = []
        for key, filenames in COMP_FILE_MAP.items():
            if key.lower() in query or key.lower() in comp_name:
                for filename in filenames:
                    fpath = kb_dir / filename
                    if fpath.exists() and fpath not in matched_files:
                        matched_files.append(fpath)

        # Also search original circulars by keyword or filename.
        if comp_dir.exists():
            for fpath in sorted(comp_dir.glob("*.md")):
                content_preview = fpath.read_text(encoding="utf-8")[:500].lower()
                if any(kw in content_preview for kw in query.split()) or any(kw in fpath.name.lower() for kw in query.split()):
                    if fpath not in matched_files:
                        matched_files.append(fpath)

        # Fallback: search all competition files
        if not matched_files:
            for pattern in ["competition_*.md", "mdrt_rules.md", "cot_rules.md"]:
                matched_files.extend(kb_dir.glob(pattern))
            if comp_dir.exists():
                matched_files.extend(sorted(comp_dir.glob("*.md")))

        results = []
        for fpath in matched_files[:4]:
            content = fpath.read_text(encoding="utf-8")
            snippet = content[:2000].strip()
            results.append({
                "source": fpath.name,
                "snippet": snippet,
            })

        if not results:
            return json.dumps({"error": "No relevant competition rule documents were found"})

        return json.dumps({
            "query": kwargs["query"],
            "results": results,
            "total_files_searched": len(matched_files),
        }, ensure_ascii=False, indent=2)
