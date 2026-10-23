"""Knowledge Layer: search_competition_rules — competition and honor standards."""
import json
from pathlib import Path
from typing import Any

from admin.services.builtin_knowledge import BUILTIN_COMPETITION_KB_NAME
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


# Keyword → file mapping. A keyword can map to multiple files (list).
# Search order: data/knowledge/{file} first, then data/knowledge/competitions/{file}.
COMP_FILE_MAP: dict[str, list[str]] = {
    # 榮譽獎項
    "ida": ["competitions/AG25035.md"],
    "mdrt": ["competitions/AG25035.md", "mdrt_rules.md"],
    "million dollar round table": ["competitions/AG25035.md", "mdrt_rules.md"],
    "百萬圓桌": ["competitions/AG25035.md", "mdrt_rules.md"],
    "cot": ["cot_rules.md"],
    "court of the table": ["cot_rules.md"],
    "超級會員": ["cot_rules.md"],
    # 精英海外
    "精英海外": ["competitions/AG24050.md", "competition_elite_challenge.md"],
    "精英挑戰": ["competitions/AG24050.md", "competition_elite_challenge.md"],
    "elite overseas": ["competitions/AG24050.md", "competition_elite_challenge.md"],
    "elite challenge": ["competitions/AG24050.md", "competition_elite_challenge.md"],
    # 三月快閃
    "三月快閃": ["competitions/AG25030.md", "competition_starlight.md"],
    "快閃三重賞": ["competitions/AG25030.md", "competition_starlight.md"],
    "星光大道": ["competition_starlight.md"],
    "march flash": ["competitions/AG25030.md", "competition_starlight.md"],
    "triple flash reward": ["competitions/AG25030.md", "competition_starlight.md"],
    "starlight avenue": ["competition_starlight.md"],
    # 業務推動
    "q1推動": ["competitions/AG25011.md", "competition_quarterly_sprint.md"],
    "業務推動": ["competitions/AG25011.md", "competition_quarterly_sprint.md"],
    "業務衝刺": ["competitions/AG25011.md", "competition_quarterly_sprint.md"],
    "季度衝刺": ["competition_quarterly_sprint.md"],
    "q1 campaign": ["competitions/AG25011.md", "competition_quarterly_sprint.md"],
    "business campaign": ["competitions/AG25011.md", "competition_quarterly_sprint.md"],
    "business sprint": ["competitions/AG25011.md", "competition_quarterly_sprint.md"],
    "quarterly sprint": ["competition_quarterly_sprint.md"],
    # 4月有禮
    "4月有禮": ["competitions/AG25044.md"],
    "接粽而來": ["competitions/AG25044.md"],
    "april gift": ["competitions/AG25044.md"],
    "dragon boat festival": ["competitions/AG25044.md"],
    # 月戰越勇
    "月戰越勇": ["competitions/AG25099.md"],
    "monthly flash reward": ["competitions/AG25099.md"],
    # 遊樂團
    "遊樂團": ["competitions/AG25129.md"],
    "賞您出行": ["competitions/AG25129.md"],
    "travel reward": ["competitions/AG25129.md"],
    # 十月推動
    "糕賞精英": ["competitions/AG25138.md"],
    "鈔有驚喜": ["competitions/AG25138.md"],
    "october campaign": ["competitions/AG25138.md"],
    "elite reward": ["competitions/AG25138.md"],
    # 新人王
    "新人王": ["competition_rookie_king.md"],
    "rookie king": ["competition_rookie_king.md"],
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
            "[Knowledge layer / 知識層] Search competition rules and honor standards by keyword "
            "or semantic vector. Supports Chinese and English names for MDRT, COT, IDA, "
            "elite overseas challenges (精英海外), quarterly sprints (季度衝刺), Rookie King "
            "(新人王), and other campaign circulars. Returns English source content."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query / 搜索關鍵詞, e.g. 'MDRT qualification' or 'MDRT資格條件', 'quarterly sprint rules' or '季度衝刺達標條件'",
                },
                "competition_name": {
                    "type": "string",
                    "description": "Optional competition name / 可選競賽名稱, in English or Chinese",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "keyword for term matching / 關鍵詞匹配; vector for semantic search / 語義向量匹配",
                    "default": "keyword",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"].lower()
        comp_name = (kwargs.get("competition_name") or "").lower()
        search_mode = str(kwargs.get("search_mode", "keyword")).strip().lower()
        if search_mode not in {"keyword", "vector"}:
            return json.dumps({"error": "search_mode must be 'keyword' or 'vector'"})
        kb_dir = self._workspace / "data" / "knowledge"
        comp_dir = kb_dir / "competitions"

        matched_files: list[Path] = []
        vector_hits_by_file: dict[Path, Any] = {}
        matched_map_terms: list[str] = []
        if search_mode == "vector":
            vector_query = " ".join(
                part for part in [kwargs["query"], kwargs.get("competition_name", "")]
                if part
            )
            try:
                hits = await search_builtin_vectors(
                    vector_query,
                    knowledge_base_name=BUILTIN_COMPETITION_KB_NAME,
                    candidate_limit=16,
                )
            except Exception as exc:
                return json.dumps(
                    {"error": f"競賽規則向量查詢失敗: {str(exc)[:200]}"},
                    ensure_ascii=False,
                )
            for hit in hits:
                source_path = str(hit.metadata.get("source_path", ""))
                fpath = self._workspace / source_path if source_path else None
                if fpath is None or not fpath.is_file():
                    root_candidate = kb_dir / hit.filename
                    nested_candidate = comp_dir / hit.filename
                    fpath = root_candidate if root_candidate.is_file() else nested_candidate
                if fpath.is_file() and fpath not in matched_files:
                    matched_files.append(fpath)
                    vector_hits_by_file[fpath] = hit
                if len(matched_files) >= 4:
                    break
        else:
            for key, filenames in COMP_FILE_MAP.items():
                if key.lower() in query or key.lower() in comp_name:
                    matched_map_terms.append(key)
                    for filename in filenames:
                        fpath = kb_dir / filename
                        if fpath.exists() and fpath not in matched_files:
                            matched_files.append(fpath)

            # Also search original circulars by keyword or filename.
            if comp_dir.exists():
                for fpath in sorted(comp_dir.glob("*.md")):
                    content_preview = fpath.read_text(encoding="utf-8")[:500].lower()
                    if (
                        any(term in content_preview for term in query.split())
                        or any(term in fpath.name.lower() for term in query.split())
                    ) and fpath not in matched_files:
                        matched_files.append(fpath)

        if not matched_files and search_mode == "keyword":
            for pattern in ["competition_*.md", "mdrt_rules.md", "cot_rules.md"]:
                matched_files.extend(kb_dir.glob(pattern))
            if comp_dir.exists():
                matched_files.extend(sorted(comp_dir.glob("*.md")))

        results, citations = [], []
        terms = unique_terms([*query.split(), *comp_name.split(), *matched_map_terms])
        for rank, fpath in enumerate(matched_files[:4], start=1):
            content = fpath.read_text(encoding="utf-8")
            snippet = content[:2000].strip()
            results.append({
                "source": fpath.name,
                "snippet": snippet,
            })
            source_path = fpath.relative_to(self._workspace).as_posix()
            if search_mode == "vector":
                hit = vector_hits_by_file.get(fpath)
                if hit is not None:
                    citations.append(build_vector_citation(
                        tool=self.name,
                        file_name=fpath.name,
                        content=hit.content,
                        distance=hit.distance,
                        rank=rank,
                        knowledge_base=hit.knowledge_base,
                        chunk_id=hit.chunk_id,
                        chunk_index=hit.chunk_index,
                        metadata={**hit.metadata, "token_count": hit.token_count},
                        source_path=source_path,
                        embedding_model=hit.embedding_model,
                    ))
            else:
                citations.append(build_keyword_citation(
                    tool=self.name,
                    file_name=fpath.name,
                    content=snippet,
                    query_terms=terms,
                    knowledge_base=BUILTIN_COMPETITION_KB_NAME,
                    source_path=source_path,
                    line_range=line_range_for_fragment(content, snippet),
                ))

        if not results:
            return json.dumps({"error": "找不到相關競賽規則文件"}, ensure_ascii=False)

        return json.dumps({
            "query": kwargs["query"],
            "results": results,
            "total_files_searched": len(matched_files),
            "citations": citations,
        }, ensure_ascii=False, indent=2)
