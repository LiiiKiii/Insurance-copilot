"""Shared pgvector retrieval for specialist knowledge tools."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from sqlalchemy import select

from admin.db import _is_sqlite, sync_engine
from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.services.embeddings import embed_texts
from nanobot.agent.tools.insurance.knowledge_layer.search_kb import (
    _load_vector_search_settings,
)


@dataclass(frozen=True)
class VectorChunkHit:
    content: str
    token_count: int
    filename: str
    knowledge_base: str
    chunk_index: int
    chunk_id: str
    metadata: dict
    distance: float
    embedding_model: str


async def search_builtin_vectors(
    query: str,
    *,
    knowledge_base_name: str,
    candidate_limit: int,
) -> list[VectorChunkHit]:
    if _is_sqlite:
        raise RuntimeError("Vector search requires PostgreSQL with pgvector")
    if not query.strip():
        return []
    batch = await embed_texts([query])
    if len(batch.vectors) != 1:
        raise RuntimeError("embedding count does not match the search query count")
    query_vector = batch.vectors[0]
    configured_top_k, threshold = _load_vector_search_settings()
    limit = max(1, candidate_limit, configured_top_k)

    def _search() -> list[VectorChunkHit]:
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
                KnowledgeBase.name == knowledge_base_name,
                KnowledgeBase.status == "active",
                Document.status == "indexed",
                DocumentChunk.embedding.is_not(None),
                cosine_distance <= threshold,
            )
            .order_by(cosine_distance, DocumentChunk.chunk_index)
            .limit(limit)
        )
        with sync_engine.connect() as connection:
            rows = connection.execute(statement).fetchall()
        hits: list[VectorChunkHit] = []
        for row in rows:
            try:
                metadata = json.loads(row[6] or "{}")
            except (TypeError, ValueError):
                metadata = {}
            hits.append(
                VectorChunkHit(
                    content=row[0],
                    token_count=row[1],
                    filename=row[2],
                    knowledge_base=row[3],
                    chunk_index=row[4],
                    chunk_id=row[5],
                    metadata=metadata,
                    distance=float(row[7]),
                    embedding_model=batch.model,
                )
            )
        return hits

    return await asyncio.to_thread(_search)
