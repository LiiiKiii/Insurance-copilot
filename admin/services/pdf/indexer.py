"""Persist chunks, vectors and SQLite FTS rows in one transaction."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.services.embeddings import EmbeddingBatch, embed_texts
from admin.services.pdf.types import Chunk

logger = logging.getLogger(__name__)


class KnowledgeIndexer:
    async def write_chunks(
        self,
        db: AsyncSession,
        chunks: Sequence[Chunk],
        doc: Document,
        kb: KnowledgeBase,
        *,
        source: str = "ocr",
        metadata_overrides: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        if metadata_overrides is not None and len(metadata_overrides) != len(chunks):
            raise ValueError("metadata override count does not match chunk count")
        is_sqlite = db.get_bind().dialect.name == "sqlite"
        embedding_batch: EmbeddingBatch | None = None
        if not is_sqlite:
            embedding_batch = await embed_texts([chunk.content for chunk in chunks])
            if len(embedding_batch.vectors) != len(chunks):
                raise RuntimeError("embedding count does not match document chunk count")

        for position, chunk in enumerate(chunks):
            row = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=doc.id,
                knowledge_base_id=kb.id,
                chunk_index=chunk.index,
                content=chunk.content,
                token_count=chunk.token_count,
                chunk_metadata=self._encode_metadata(
                    chunk,
                    embedding_batch,
                    source=source,
                    extra=(metadata_overrides[position] if metadata_overrides else None),
                ),
                embedding=(
                    embedding_batch.vectors[position]
                    if embedding_batch is not None
                    else None
                ),
            )
            db.add(row)
            if is_sqlite:
                await db.flush()
                rowid = await db.scalar(
                    text("SELECT rowid FROM document_chunks WHERE id = :id"),
                    {"id": row.id},
                )
                await db.execute(
                    text(
                        "INSERT INTO knowledge_fts(rowid, doc_id, title, content) "
                        "VALUES (:rowid, :doc_id, :title, :content)"
                    ),
                    {
                        "rowid": rowid,
                        "doc_id": doc.id,
                        "title": doc.filename,
                        "content": chunk.content,
                    },
                )

    @staticmethod
    def _encode_metadata(
        chunk: Chunk,
        embedding_batch: EmbeddingBatch | None = None,
        *,
        source: str = "ocr",
        extra: Mapping[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "page_no": chunk.page_no,
            "page_range": list(chunk.page_range),
            "heading_path": [heading[:80] for heading in chunk.heading_path],
            "chunk_type": chunk.chunk_type,
            "source": source,
            "chunk_size": chunk.chunk_size,
            "chunk_overlap": chunk.chunk_overlap,
            "overlap_from_previous_tokens": chunk.overlap_from_previous_tokens,
        }
        if extra:
            payload.update(extra)
        if embedding_batch is not None:
            payload.update(
                {
                    "embedding_model": embedding_batch.model,
                    "embedding_dimensions": embedding_batch.dimensions,
                    "embedding_source_field": "content",
                    "embedding_content_sha256": hashlib.sha256(
                        chunk.content.encode("utf-8")
                    ).hexdigest(),
                }
            )
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > 1900:
            logger.warning(
                "chunk_metadata exceeds safety limit, falling back to {} for chunk index=%s",
                chunk.index,
            )
            return "{}"
        return encoded
