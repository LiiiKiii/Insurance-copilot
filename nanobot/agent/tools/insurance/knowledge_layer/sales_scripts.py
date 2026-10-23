"""Knowledge Layer: search_sales_scripts — conversation templates for sales scenarios."""
import json
from pathlib import Path
from typing import Any

from admin.services.builtin_knowledge import BUILTIN_SALES_KB_NAME
from nanobot.agent.tools.base import Tool
from nanobot.agent.tools.insurance.knowledge_layer._vector_search import (
    search_builtin_vectors,
)
from nanobot.retrieval_citations import (
    build_keyword_citation,
    build_vector_citation,
    line_range_for_fragment,
    unique_terms,
)


SCENARIO_KEYWORDS = {
    "objection": ["think about it", "objection", "refuse", "expensive", "too costly"],
    "needs_analysis": ["needs", "risk review", "analysis", "exposure", "coverage gap"],
    "referral": ["referral", "introduction", "friend", "recommendation"],
    "upsell": ["cross-line", "existing client", "additional exposure", "upgrade"],
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
            "Supported scenarios include price objection handling, risk analysis, "
            "referrals, cross-line reviews, renewals, and closing."
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
                    "description": "Optional product type such as motor, property, commercial, liability, or specialty",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "Use keyword or semantic vector retrieval",
                    "default": "keyword",
                },
            },
            "required": ["scenario"],
        }

    async def execute(self, **kwargs: Any) -> str:
        scenario = kwargs["scenario"].lower()
        search_mode = str(kwargs.get("search_mode", "keyword")).strip().lower()
        if search_mode not in {"keyword", "vector"}:
            return json.dumps({"error": "search_mode must be 'keyword' or 'vector'"})
        scripts_path = self._workspace / "data" / "knowledge" / "sales_scripts.md"

        if not scripts_path.exists():
            return json.dumps({"error": "The sales-script knowledge document is unavailable"})

        content = scripts_path.read_text(encoding="utf-8")
        sections = content.split("\n## ")

        matched: list[str] = []
        vector_hits_by_section: dict[str, Any] = {}
        if search_mode == "vector":
            query = " ".join(
                part for part in [kwargs["scenario"], kwargs.get("product_type", "")]
                if part
            )
            try:
                hits = await search_builtin_vectors(
                    query,
                    knowledge_base_name=BUILTIN_SALES_KB_NAME,
                    candidate_limit=10,
                )
            except Exception as exc:
                return json.dumps({"error": f"Vector script search failed: {str(exc)[:200]}"})
            section_map = {
                section.strip().splitlines()[0].strip(): section.strip()
                for section in sections[1:]
                if section.strip()
            }
            for hit in hits:
                section = section_map.get(str(hit.metadata.get("section_title", "")).strip())
                if section and section not in matched:
                    matched.append(section)
                    vector_hits_by_section[section] = hit
                if len(matched) >= 2:
                    break
        else:
            for section in sections[1:]:
                section_lower = section.lower()
                for key, keywords in SCENARIO_KEYWORDS.items():
                    if key in scenario or any(kw in scenario for kw in keywords):
                        if any(kw in section_lower for kw in keywords):
                            matched.append(section.strip())
                            break

        if not matched and search_mode == "keyword":
            matched = [sections[1].strip()] if len(sections) > 1 else []

        terms = [*scenario.split()]
        for key, keywords in SCENARIO_KEYWORDS.items():
            if key in scenario or any(term in scenario for term in keywords):
                terms.extend([key, *keywords])
        terms = unique_terms(terms)
        citations = []
        for rank, section in enumerate(matched[:2], start=1):
            title = section.splitlines()[0].strip() if section else None
            if search_mode == "vector":
                hit = vector_hits_by_section.get(section)
                if hit is not None:
                    citations.append(build_vector_citation(
                        tool=self.name,
                        file_name=scripts_path.name,
                        content=hit.content,
                        distance=hit.distance,
                        rank=rank,
                        knowledge_base=hit.knowledge_base,
                        chunk_id=hit.chunk_id,
                        chunk_index=hit.chunk_index,
                        metadata={**hit.metadata, "token_count": hit.token_count},
                        section_title=title,
                        source_path="data/knowledge/sales_scripts.md",
                        embedding_model=hit.embedding_model,
                    ))
            else:
                citations.append(build_keyword_citation(
                    tool=self.name,
                    file_name=scripts_path.name,
                    content=section,
                    query_terms=terms,
                    knowledge_base=BUILTIN_SALES_KB_NAME,
                    section_title=title,
                    source_path="data/knowledge/sales_scripts.md",
                    line_range=line_range_for_fragment(content, section),
                ))

        return json.dumps({
            "scenario": kwargs["scenario"],
            "product_type": kwargs.get("product_type", ""),
            "matched_count": len(matched),
            "scripts": matched[:2],
            "citations": citations,
        }, ensure_ascii=False, indent=2)
