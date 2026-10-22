"""Build and transport structured evidence independently from model prose."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

RETRIEVAL_TOOL_NAMES = {
    "search_knowledge_base",
    "search_competition_rules",
    "search_best_practice",
    "search_sales_scripts",
}
_MAX_EXCERPT_CHARS = 4_000


def parse_chunk_metadata(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def unique_terms(terms: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        value = str(term).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def line_range_for_fragment(document: str, fragment: str) -> list[int] | None:
    if not document or not fragment:
        return None
    start = document.find(fragment)
    if start < 0:
        return None
    end = start + len(fragment)
    return [document.count("\n", 0, start) + 1, document.count("\n", 0, end) + 1]


def _keyword_matches(
    content: str, terms: Iterable[str]
) -> tuple[list[str], list[dict[str, Any]]]:
    lowered = content.casefold()
    matched: list[str] = []
    locations: list[dict[str, Any]] = []
    for term in unique_terms(terms):
        needle, start, found = term.casefold(), 0, False
        while needle and len(locations) < 24:
            index = lowered.find(needle, start)
            if index < 0:
                break
            found = True
            locations.append({"term": term, "start": index, "end": index + len(term)})
            start = index + max(1, len(needle))
            if sum(item["term"] == term for item in locations) >= 3:
                break
        if found:
            matched.append(term)
    locations.sort(key=lambda item: (item["start"], item["end"], item["term"].casefold()))
    return matched, locations


def _common_citation(
    *,
    mode: str,
    tool: str,
    file_name: str,
    content: str,
    knowledge_base: str | None = None,
    chunk_id: str | None = None,
    chunk_index: int | None = None,
    metadata: dict[str, Any] | None = None,
    section_title: str | None = None,
    source_path: str | None = None,
    line_range: list[int] | None = None,
) -> dict[str, Any]:
    meta = metadata or {}
    resolved_section = section_title or meta.get("section_title")
    raw_id = "|".join(
        [mode, tool, file_name, str(chunk_index), str(resolved_section or "")]
    ).encode("utf-8")
    payload: dict[str, Any] = {
        "citation_id": hashlib.sha1(raw_id).hexdigest()[:16],
        "mode": mode,
        "tool": tool,
        "file_name": file_name,
        "content_excerpt": content[:_MAX_EXCERPT_CHARS],
    }
    optional = {
        "knowledge_base": knowledge_base,
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "section_title": resolved_section,
        "source_path": source_path or meta.get("source_path"),
        "page_range": meta.get("page_range"),
        "heading_path": meta.get("heading_path"),
        "line_range": line_range,
        "token_count": meta.get("token_count"),
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    return payload


def build_keyword_citation(
    *,
    tool: str,
    file_name: str,
    content: str,
    query_terms: Iterable[str],
    knowledge_base: str | None = None,
    chunk_id: str | None = None,
    chunk_index: int | None = None,
    metadata: dict[str, Any] | None = None,
    section_title: str | None = None,
    source_path: str | None = None,
    line_range: list[int] | None = None,
) -> dict[str, Any]:
    normalized = unique_terms(query_terms)
    matched, locations = _keyword_matches(content, normalized)
    citation = _common_citation(
        mode="keyword",
        tool=tool,
        file_name=file_name,
        content=content,
        knowledge_base=knowledge_base,
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        metadata=metadata,
        section_title=section_title,
        source_path=source_path,
        line_range=line_range,
    )
    citation["keyword"] = {
        "query_terms": normalized,
        "matched_terms": matched,
        "match_locations": locations,
    }
    return citation


def build_vector_citation(
    *,
    tool: str,
    file_name: str,
    content: str,
    distance: float,
    rank: int,
    knowledge_base: str | None = None,
    chunk_id: str | None = None,
    chunk_index: int | None = None,
    metadata: dict[str, Any] | None = None,
    section_title: str | None = None,
    source_path: str | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    numeric_distance = float(distance)
    citation = _common_citation(
        mode="vector",
        tool=tool,
        file_name=file_name,
        content=content,
        knowledge_base=knowledge_base,
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        metadata=metadata,
        section_title=section_title,
        source_path=source_path,
    )
    citation["vector"] = {
        "rank": rank,
        "distance": round(numeric_distance, 6),
        "similarity": round(max(-1.0, min(1.0, 1.0 - numeric_distance)), 6),
        **({"embedding_model": embedding_model} if embedding_model else {}),
    }
    return citation


def extract_retrieval_citations(tool_name: str, result: Any) -> list[dict[str, Any]]:
    if tool_name not in RETRIEVAL_TOOL_NAMES:
        return []
    payload = result
    if isinstance(result, str):
        try:
            payload = json.loads(result)
        except (TypeError, ValueError):
            return []
    if not isinstance(payload, dict) or not isinstance(payload.get("citations"), list):
        return []
    return [
        item for item in payload["citations"]
        if isinstance(item, dict)
        and item.get("mode") in {"keyword", "vector"}
        and isinstance(item.get("file_name"), str)
    ]


def strip_retrieval_citations(tool_name: str, result: Any) -> Any:
    if tool_name not in RETRIEVAL_TOOL_NAMES:
        return result
    if isinstance(result, dict):
        sanitized = dict(result)
        sanitized.pop("citations", None)
        return sanitized
    if isinstance(result, str):
        try:
            payload = json.loads(result)
        except (TypeError, ValueError):
            return result
        if not isinstance(payload, dict) or "citations" not in payload:
            return result
        payload.pop("citations", None)
        return json.dumps(payload, ensure_ascii=False)
    return result


def deduplicate_citations(citations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in citations:
        key = str(
            citation.get("citation_id")
            or json.dumps(citation, sort_keys=True, default=str)
        )
        if key not in seen:
            seen.add(key)
            result.append(citation)
    return result
