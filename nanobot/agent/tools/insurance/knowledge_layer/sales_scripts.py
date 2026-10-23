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
    "objection": {
        "query_aliases": [
            "考慮", "考虑", "異議", "异议", "拒絕", "拒绝", "太貴", "太贵",
            "objection", "too expensive", "think about it", "handling objections",
        ],
        "document_terms": [
            "objection handling", "think about it", "too expensive", "clarify concerns",
        ],
    },
    "needs_analysis": {
        "query_aliases": [
            "需求", "挖掘", "分析", "保障缺口", "fabe", "needs analysis",
            "needs discovery", "coverage gap",
        ],
        "document_terms": [
            "demand mining", "fabe framework", "core questions for demand mining",
        ],
    },
    "referral": {
        "query_aliases": [
            "轉介紹", "转介绍", "介紹", "介绍", "朋友", "referral", "refer a friend",
        ],
        "document_terms": ["referral", "old customers", "friends"],
    },
    "upsell": {
        "query_aliases": [
            "加保", "老客", "升級", "升级", "upsell", "existing client",
            "additional coverage",
        ],
        "document_terms": ["old customers", "additional coverage", "protection needs"],
    },
    "closing": {
        "query_aliases": [
            "促成", "成交", "簽單", "签单", "closing", "close the sale", "sign policy",
        ],
        "document_terms": [
            "facilitating conversational skills", "direct facilitation method",
            "small steps closing method",
        ],
    },
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
            "[Knowledge layer / 知識層] Search bilingual sales scenarios and return English "
            "conversation scripts. Supports objection handling (異議處理), FABE needs analysis "
            "(需求挖掘), referrals (轉介紹), existing-client upsell (老客加保), and closing "
            "(促成成交)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": "Scenario / 場景, e.g. 'objection handling' or '異議處理', 'needs analysis' or '需求挖掘', 'referral', 'upsell', or 'closing'",
                },
                "product_type": {
                    "type": "string",
                    "description": "Optional product type / 可選產品類型, e.g. 'protection/保障型', 'savings/儲蓄型', or 'critical illness/危疾'",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "keyword for term matching / 關鍵詞匹配; vector for semantic search / 語義向量匹配",
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
            return json.dumps({"error": "Sales-script knowledge base not found / 話術知識庫不存在"}, ensure_ascii=False)

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
                return json.dumps(
                    {"error": f"話術向量查詢失敗: {str(exc)[:200]}"},
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
                if len(matched) >= 2:
                    break
        else:
            matched_rules = [
                rule
                for rule in SCENARIO_KEYWORDS.values()
                if any(alias in scenario for alias in rule["query_aliases"])
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
            matched = [sections[1].strip()] if len(sections) > 1 else []

        terms = [*scenario.split()]
        for key, rule in SCENARIO_KEYWORDS.items():
            if any(alias in scenario for alias in rule["query_aliases"]):
                terms.extend([key, *rule["query_aliases"], *rule["document_terms"]])
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
