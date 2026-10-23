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
    "average_case_size": {
        "query_aliases": [
            "件均", "保費偏低", "保费偏低", "保額", "保额", "avg_case",
            "case size", "average case size", "average premium",
        ],
        "document_terms": [
            "average premium per case", "average case size", "average premium",
            "premium per policy",
        ],
    },
    "conversion": {
        "query_aliases": [
            "轉化", "转化", "成交", "跟進", "跟进", "線索", "线索", "客源",
            "conversion", "lead", "lead conversion", "follow-up rate",
        ],
        "document_terms": [
            "low lead follow-up rate", "lead conversion rate", "72-hour rule",
            "three-contact method",
        ],
    },
    "mdrt": {
        "query_aliases": ["mdrt", "百萬圓桌", "百万圆桌", "里程碑"],
        "document_terms": ["mdrt", "career milestone"],
    },
    "sprint": {
        "query_aliases": [
            "衝刺", "冲刺", "最後", "最后", "截止", "30天",
            "sprint", "deadline", "last 30 days",
        ],
        "document_terms": [
            "sprint tactics", "sprint mode", "competition deadline", "last 30 days",
        ],
    },
    "existing_client": {
        "query_aliases": [
            "老客", "加保", "續保", "续保", "轉介紹", "转介绍", "介紹", "介绍",
            "existing client", "additional coverage", "referral", "upsell",
        ],
        "document_terms": [
            "timing for old customers to add insurance", "best entry timing",
            "annual coverage assessment",
        ],
    },
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
            "[Knowledge layer / 知識層] Search insurance-sales best practices by keyword or "
            "semantic vector. Supports average premium (件均保費), lead conversion (線索轉化), "
            "competition and MDRT sprints (競賽/MDRT衝刺), and existing-client upsell/referrals "
            "(老客加保/轉介紹). Returns English strategies and action guidance."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic / 主題, e.g. 'average premium is low' or '件均保費偏低', 'MDRT sprint' or 'MDRT衝刺'",
                },
                "context": {
                    "type": "string",
                    "description": "Optional context / 額外上下文, such as agent level or the specific problem",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "keyword for term matching / 關鍵詞匹配; vector for semantic search / 語義向量匹配",
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
            return json.dumps({"error": "Best-practice knowledge base not found / 最佳實踐知識庫不存在"}, ensure_ascii=False)

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
                return json.dumps(
                    {"error": f"最佳實踐向量查詢失敗: {str(exc)[:200]}"},
                    ensure_ascii=False,
                )
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
            matched_rules = [
                rule
                for rule in TOPIC_KEYWORDS.values()
                if any(alias in topic for alias in rule["query_aliases"])
            ]
            for rule in matched_rules:
                for section in sections[1:]:
                    section_lower = section.lower()
                    normalized = section.strip()
                    if (
                        normalized not in matched
                        and any(term in section_lower for term in rule["document_terms"])
                    ):
                        matched.append(normalized)

        if not matched and search_mode == "keyword":
            # Return first 2 sections as fallback
            matched = [s.strip() for s in sections[1:3]]

        terms = [*topic.split()]
        for key, rule in TOPIC_KEYWORDS.items():
            if any(alias in topic for alias in rule["query_aliases"]):
                terms.extend([key, *rule["query_aliases"], *rule["document_terms"]])
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
