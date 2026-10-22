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
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "Use keyword or semantic vector retrieval",
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
                return json.dumps({"error": f"Vector competition search failed: {str(exc)[:200]}"})
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
            return json.dumps({"error": "No relevant competition rule documents were found"})

        return json.dumps({
            "query": kwargs["query"],
            "results": results,
            "total_files_searched": len(matched_files),
            "citations": citations,
        }, ensure_ascii=False, indent=2)
