"""Search admin-managed knowledge with keyword or pgvector retrieval."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from admin.db import _is_sqlite, sync_engine
from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.services.embeddings import embed_texts
from nanobot.agent.tools.base import Tool
from nanobot.retrieval_citations import (
    build_keyword_citation,
    build_vector_citation,
    parse_chunk_metadata,
)

logger = logging.getLogger(__name__)
_DEFAULT_VECTOR_TOP_K = 5
_DEFAULT_VECTOR_DISTANCE_THRESHOLD = 0.55


def _search_fts(
    conn,
    keywords: list[str],
    kb_name: str | None,
    limit: int,
    metadata_sql: str = "dc.chunk_metadata",
):
    try:
        where = "knowledge_fts MATCH :match_expr"
        params: dict[str, Any] = {
            "match_expr": " OR ".join(keywords),
            "limit_val": limit,
        }
        if kb_name:
            where += " AND kb.name LIKE :kb_name"
            params["kb_name"] = f"%{kb_name}%"
        return conn.execute(
            text(
                f"""
                SELECT dc.content, dc.token_count, d.filename, kb.name, dc.chunk_index,
                       dc.id, {metadata_sql} AS chunk_metadata, NULL AS distance
                FROM knowledge_fts fts
                JOIN document_chunks dc ON dc.rowid = fts.rowid
                JOIN documents d ON d.id = dc.document_id
                JOIN knowledge_bases kb ON kb.id = dc.knowledge_base_id
                WHERE {where}
                LIMIT :limit_val
                """
            ),
            params,
        ).fetchall()
    except Exception:
        return None


def _load_vector_search_settings() -> tuple[int, float]:
    try:
        top_k = int(os.environ.get("RAG_VECTOR_TOP_K", _DEFAULT_VECTOR_TOP_K))
    except ValueError as exc:
        raise ValueError("RAG_VECTOR_TOP_K must be an integer") from exc
    try:
        threshold = float(
            os.environ.get(
                "RAG_VECTOR_DISTANCE_THRESHOLD",
                _DEFAULT_VECTOR_DISTANCE_THRESHOLD,
            )
        )
    except ValueError as exc:
        raise ValueError("RAG_VECTOR_DISTANCE_THRESHOLD must be a number") from exc
    if top_k <= 0:
        raise ValueError("RAG_VECTOR_TOP_K must be greater than zero")
    if not 0 <= threshold <= 2:
        raise ValueError("RAG_VECTOR_DISTANCE_THRESHOLD must be between 0 and 2")
    return top_k, threshold


def _search_vector(
    conn,
    query_vector: list[float],
    kb_name: str | None,
    top_k: int,
    distance_threshold: float,
):
    cosine_distance = DocumentChunk.embedding.cosine_distance(query_vector)
    statement = (
        select(
            DocumentChunk.content,
            DocumentChunk.token_count,
            Document.filename,
            KnowledgeBase.name,
            DocumentChunk.chunk_index,
            DocumentChunk.id,
            DocumentChunk.chunk_metadata,
            cosine_distance.label("distance"),
        )
        .select_from(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
        .where(
            DocumentChunk.embedding.is_not(None),
            cosine_distance <= distance_threshold,
        )
    )
    if kb_name:
        statement = statement.where(KnowledgeBase.name.like(f"%{kb_name}%"))
    return conn.execute(
        statement.order_by(cosine_distance, DocumentChunk.chunk_index).limit(top_k)
    ).fetchall()


class SearchKnowledgeBaseTool(Tool):
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "search_knowledge_base"

    @property
    def description(self) -> str:
        return (
            "Search knowledge bases using keyword matching or semantic vector "
            "matching. Use for policies, product details, training materials, "
            "and administrator-uploaded domain knowledge."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query in natural language"},
                "kb_name": {
                    "type": "string",
                    "description": "Optional knowledge-base name filter",
                },
                "search_mode": {
                    "type": "string",
                    "enum": ["keyword", "vector"],
                    "description": "Retrieval method",
                    "default": "keyword",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum keyword results; vector mode uses RAG_VECTOR_TOP_K",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        kb_name = kwargs.get("kb_name")
        search_mode = str(kwargs.get("search_mode", "keyword")).strip().lower()
        if not query:
            return json.dumps({"error": "Query is required"}, ensure_ascii=False)
        if search_mode not in {"keyword", "vector"}:
            return json.dumps(
                {"error": "search_mode must be 'keyword' or 'vector'"},
                ensure_ascii=False,
            )
        if search_mode == "vector" and _is_sqlite:
            return json.dumps(
                {"error": "Vector search requires PostgreSQL with pgvector"},
                ensure_ascii=False,
            )

        try:
            keyword_top_k = int(kwargs.get("top_k", 5))
        except (TypeError, ValueError):
            return json.dumps({"error": "top_k must be an integer"}, ensure_ascii=False)
        keyword_terms = [term.strip() for term in query.split() if len(term.strip()) >= 2]
        vector_top_k = 0
        distance_threshold = 0.0
        query_vector: list[float] | None = None
        embedding_model: str | None = None

        def _search() -> str:
            with sync_engine.connect() as connection:
                metadata_sql = "dc.chunk_metadata"
                if _is_sqlite:
                    columns = {
                        row[1]
                        for row in connection.exec_driver_sql(
                            "PRAGMA table_info(document_chunks)"
                        ).fetchall()
                    }
                    if "chunk_metadata" not in columns:
                        # Preserve compatibility with pre-M3/local test schemas.
                        metadata_sql = "NULL"
                if search_mode == "vector":
                    assert query_vector is not None
                    rows = _search_vector(
                        connection,
                        query_vector,
                        kb_name,
                        vector_top_k,
                        distance_threshold,
                    )
                else:
                    rows = (
                        _search_fts(
                            connection,
                            keyword_terms,
                            kb_name,
                            keyword_top_k,
                            metadata_sql,
                        )
                        if keyword_terms and _is_sqlite
                        else None
                    )
                    if not rows:
                        where_clauses: list[str] = []
                        params: dict[str, Any] = {"limit_val": keyword_top_k}
                        if kb_name:
                            where_clauses.append("kb.name LIKE :kb_name")
                            params["kb_name"] = f"%{kb_name}%"
                        if keyword_terms:
                            matches: list[str] = []
                            for index, term in enumerate(keyword_terms):
                                key = f"kw_{index}"
                                matches.append(f"dc.content LIKE :{key}")
                                params[key] = f"%{term}%"
                            where_clauses.append(f"({' OR '.join(matches)})")
                        where_sql = " AND ".join(where_clauses) or "1=1"
                        rows = connection.execute(
                            text(
                                f"""
                                SELECT dc.content, dc.token_count, d.filename, kb.name,
                                       dc.chunk_index, dc.id, {metadata_sql} AS chunk_metadata,
                                       NULL AS distance
                                FROM document_chunks dc
                                JOIN documents d ON d.id = dc.document_id
                                JOIN knowledge_bases kb ON kb.id = dc.knowledge_base_id
                                WHERE {where_sql}
                                ORDER BY dc.chunk_index
                                LIMIT :limit_val
                                """
                            ),
                            params,
                        ).fetchall()
                kb_rows = connection.execute(
                    text(
                        "SELECT name, document_count FROM knowledge_bases "
                        "WHERE status = 'active'"
                    )
                ).fetchall()

            if not rows:
                names = [row[0] for row in kb_rows]
                return json.dumps(
                    {
                        "found": False,
                        "query": query,
                        "message": (
                            "No matching content found. Available knowledge bases: "
                            + (", ".join(names) if names else "none")
                        ),
                        "available_kbs": names,
                        "results": [],
                    },
                    ensure_ascii=False,
                )

            results, citations = [], []
            for rank, row in enumerate(rows, start=1):
                content, token_count, filename, kb_value, chunk_index = row[:5]
                chunk_id = row[5]
                metadata = parse_chunk_metadata(row[6])
                distance = row[7]
                results.append(
                    {
                        "content": content[:1500],
                        "source": f"{kb_value} / {filename} (chunk {chunk_index})",
                        "token_count": token_count,
                    }
                )
                citation_metadata = {**metadata, "token_count": token_count}
                if search_mode == "vector":
                    citations.append(
                        build_vector_citation(
                            tool=self.name,
                            file_name=filename,
                            content=content,
                            distance=float(distance or 0.0),
                            rank=rank,
                            knowledge_base=kb_value,
                            chunk_id=chunk_id,
                            chunk_index=chunk_index,
                            metadata=citation_metadata,
                            embedding_model=embedding_model,
                        )
                    )
                else:
                    citations.append(
                        build_keyword_citation(
                            tool=self.name,
                            file_name=filename,
                            content=content,
                            query_terms=keyword_terms,
                            knowledge_base=kb_value,
                            chunk_id=chunk_id,
                            chunk_index=chunk_index,
                            metadata=citation_metadata,
                        )
                    )
            return json.dumps(
                {
                    "found": True,
                    "query": query,
                    "result_count": len(results),
                    "results": results,
                    "citations": citations,
                },
                ensure_ascii=False,
            )

        try:
            if search_mode == "vector":
                vector_top_k, distance_threshold = _load_vector_search_settings()
                batch = await embed_texts([query])
                if len(batch.vectors) != 1:
                    raise RuntimeError("embedding count does not match the search query count")
                query_vector, embedding_model = batch.vectors[0], batch.model
            return await asyncio.to_thread(_search)
        except Exception as exc:
            logger.error("Knowledge base search failed: %s", exc, exc_info=True)
            return json.dumps(
                {"found": False, "error": "Knowledge base query failed", "results": []},
                ensure_ascii=False,
            )
