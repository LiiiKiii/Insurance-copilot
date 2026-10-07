"""Persist Chunks into ``document_chunks`` plus the FTS5 virtual table.

The FTS5 row's rowid MUST equal the corresponding ``document_chunks`` row's
rowid because
``nanobot/agent/tools/insurance/knowledge_layer/search_kb.py`` joins them
via ``dc.rowid = fts.rowid``. This means we flush after inserting each
chunk to obtain its assigned rowid before inserting the FTS row.

PostgreSQL deployments don't have the FTS5 virtual table; we detect the
dialect and skip the FTS insert there. Existing PG search behaviour (LIKE)
is unchanged by this MVP.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.services.pdf.types import Chunk

logger = logging.getLogger(__name__)


class KnowledgeIndexer:
    async def write_chunks(
        self,
        db: AsyncSession,
        chunks: Sequence[Chunk],
        doc: Document,
        kb: KnowledgeBase,
    ) -> None:
        is_sqlite = db.get_bind().dialect.name == "sqlite"

        for c in chunks:
            chunk_row = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=doc.id,
                knowledge_base_id=kb.id,
                chunk_index=c.index,
                content=c.content,
                token_count=c.token_count,
                chunk_metadata=self._encode_metadata(c),
            )
            db.add(chunk_row)

            if is_sqlite:
                # Flush so SQLite assigns a rowid we can read back.
                await db.flush()
                rowid = await db.scalar(
                    text("SELECT rowid FROM document_chunks WHERE id = :id"),
                    {"id": chunk_row.id},
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
                        "content": c.content,
                    },
                )

    @staticmethod
    def _encode_metadata(c: Chunk) -> str:
        truncated_path = [h[:80] for h in c.heading_path]
        payload = {
            "page_no": c.page_no,
            "page_range": list(c.page_range),
            "heading_path": truncated_path,
            "chunk_type": c.chunk_type,
            "source": "ocr",
        }
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > 1900:
            logger.warning(
                "chunk_metadata exceeds safety limit, falling back to {} for chunk index=%s",
                c.index,
            )
            return "{}"
        return encoded
