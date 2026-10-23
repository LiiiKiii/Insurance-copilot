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
    "件均": ["件均", "case size", "保費偏低", "avg_case", "保額"],
    "轉化": ["轉化", "conversion", "成交", "跟進", "线索", "線索"],
    "mdrt": ["mdrt", "百萬圓桌", "里程碑"],
    "衝刺": ["衝刺", "最後", "截止", "冲刺", "30天"],
    "老客": ["老客", "加保", "續保", "轉介紹", "介绍", "转介绍"],
    "線索": ["線索", "跟進", "lead", "客源"],
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
            "【知識層】以關鍵詞或語義向量搜索保險銷售最佳實踐和成功策略。"
            "覆蓋：提升件均保費、提升線索轉化率、競賽衝刺戰術、MDRT衝刺策略、老客加保。"
            "返回相關策略和行動建議。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "主題，如 '件均保費偏低'、'MDRT衝刺'、'線索轉化率低'、'競賽最後30天'",
                },
                "context": {
                    "type": "string",
                    "description": "額外上下文（可選），如代理人職級、具體問題",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "keyword 使用關鍵詞匹配；vector 使用語義向量匹配",
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
            return json.dumps({"error": "最佳實踐知識庫不存在"}, ensure_ascii=False)

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
