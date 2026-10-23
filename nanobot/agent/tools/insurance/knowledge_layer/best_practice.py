"""Knowledge Layer: search_best_practice — proven sales strategies and success cases."""
import json
from pathlib import Path
from typing import Any

from admin.services.builtin_knowledge import BUILTIN_BEST_PRACTICE_KB_NAME
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


TOPIC_KEYWORDS = {
    "case_size": ["case size", "average premium", "low premium", "coverage amount"],
    "conversion": ["conversion", "closing rate", "follow-up", "lead"],
    "written_premium": ["written premium", "premium target", "milestone"],
    "sprint": ["sprint", "deadline", "last 30 days", "final month"],
    "existing_client": ["existing client", "cross-line", "renewal", "referral"],
    "retention": ["retention", "renewal", "churn"],
    "product_mix": ["product mix", "motor", "property", "commercial", "specialty"],
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
            "written-premium progress, retention, and cross-line reviews for existing clients."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic such as 'low average premium', 'written premium sprint', 'low lead conversion', or 'renewal retention'",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context such as the agent's role or a specific business issue",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "Use keyword or semantic vector retrieval",
                    "default": "keyword",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, **kwargs: Any) -> str:
        topic = kwargs["topic"].lower()
        search_mode = str(kwargs.get("search_mode", "keyword")).strip().lower()
        if search_mode not in {"keyword", "vector"}:
            return json.dumps({"error": "search_mode must be 'keyword' or 'vector'"})
        bp_path = self._workspace / "data" / "knowledge" / "best_practices.md"

        if not bp_path.exists():
            return json.dumps({"error": "The best-practice knowledge document is unavailable"})

        content = bp_path.read_text(encoding="utf-8")
        sections = content.split("\n## ")

        matched: list[str] = []
        vector_hits_by_section: dict[str, Any] = {}
        if search_mode == "vector":
            query = " ".join(
                part for part in [kwargs["topic"], kwargs.get("context", "")] if part
            )
            try:
                hits = await search_builtin_vectors(
                    query,
                    knowledge_base_name=BUILTIN_BEST_PRACTICE_KB_NAME,
                    candidate_limit=12,
                )
            except Exception as exc:
                return json.dumps({"error": f"Vector best-practice search failed: {str(exc)[:200]}"})
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
                if len(matched) >= 3:
                    break
        else:
            for section in sections[1:]:
                section_lower = section.lower()
                for key, keywords in TOPIC_KEYWORDS.items():
                    if key in topic or any(kw in topic for kw in keywords):
                        if any(kw in section_lower for kw in keywords):
                            matched.append(section.strip())
                            break

        if not matched and search_mode == "keyword":
            # Return first 2 sections as fallback
            matched = [s.strip() for s in sections[1:3]]

        terms = [*topic.split()]
        for key, keywords in TOPIC_KEYWORDS.items():
            if key in topic or any(term in topic for term in keywords):
                terms.extend([key, *keywords])
        terms = unique_terms(terms)
        citations = []
        for rank, section in enumerate(matched[:3], start=1):
            title = section.splitlines()[0].strip() if section else None
            if search_mode == "vector":
                hit = vector_hits_by_section.get(section)
                if hit is not None:
                    citations.append(build_vector_citation(
                        tool=self.name,
                        file_name=bp_path.name,
                        content=hit.content,
                        distance=hit.distance,
                        rank=rank,
                        knowledge_base=hit.knowledge_base,
                        chunk_id=hit.chunk_id,
                        chunk_index=hit.chunk_index,
                        metadata={**hit.metadata, "token_count": hit.token_count},
                        section_title=title,
                        source_path="data/knowledge/best_practices.md",
                        embedding_model=hit.embedding_model,
                    ))
            else:
                citations.append(build_keyword_citation(
                    tool=self.name,
                    file_name=bp_path.name,
                    content=section,
                    query_terms=terms,
                    knowledge_base=BUILTIN_BEST_PRACTICE_KB_NAME,
                    section_title=title,
                    source_path="data/knowledge/best_practices.md",
                    line_range=line_range_for_fragment(content, section),
                ))

        return json.dumps({
            "topic": kwargs["topic"],
            "matched_count": len(matched),
            "practices": matched[:3],
            "citations": citations,
        }, ensure_ascii=False, indent=2)
