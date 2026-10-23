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
    "objection": ["考慮", "objection", "異議", "拒絕", "太貴"],
    "needs_analysis": ["需求", "fabe", "挖掘", "分析", "保障缺口"],
    "referral": ["轉介紹", "referral", "介紹", "朋友"],
    "upsell": ["加保", "老客", "upsell", "升級"],
    "closing": ["促成", "closing", "成交", "簽單"],
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
            "【知識層】以關鍵詞或語義向量搜索特定銷售場景的話術模板。"
            "場景包括：異議處理（客戶說考慮一下）、需求挖掘（FABE法）、"
            "轉介紹、老客加保、促成成交。返回可直接使用的話術和使用說明。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": "場景描述，如 'objection_handling'、'needs_analysis'、'referral'、'upsell'、'closing'，或中文描述",
                },
                "product_type": {
                    "type": "string",
                    "description": "產品類型（可選），如 '保障型'、'儲蓄型'、'危疾'",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "keyword 使用關鍵詞匹配；vector 使用語義向量匹配",
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
            return json.dumps({"error": "話術知識庫不存在"}, ensure_ascii=False)

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
