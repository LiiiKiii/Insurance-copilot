"""Orchestrate the OCR PDF ingestion pipeline.

Owns the only DB session in the pipeline. The five adapters
(rasterizer, ocr, recoverer, chunker, indexer) are pure: this class is the
only place that knows about transactions and status transitions.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select

from admin.models.knowledge import Document, KnowledgeBase
from admin.services.pdf.chunker import MarkdownChunker
from admin.services.pdf.indexer import KnowledgeIndexer
from admin.services.pdf.layout_recoverer import LayoutRecoverer
from admin.services.pdf.ocr_extractor import OcrExtractor
from admin.services.pdf.rasterizer import PdfRasterizer

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        session_factory,
        rasterizer: PdfRasterizer,
        ocr: OcrExtractor,
        recoverer: LayoutRecoverer,
        chunker: MarkdownChunker,
        indexer: KnowledgeIndexer,
    ) -> None:
        self._sf = session_factory
        self._raster = rasterizer
        self._ocr = ocr
        self._recover = recoverer
        self._chunker = chunker
        self._indexer = indexer

    async def process_document(self, doc_id: str) -> None:
        async with self._sf() as db:
            doc = (
                await db.execute(select(Document).where(Document.id == doc_id))
            ).scalar_one_or_none()
            if doc is None:
                logger.warning("process_document called with unknown id %s", doc_id)
                return
            kb = (
                await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == doc.knowledge_base_id)
                )
            ).scalar_one_or_none()
            if kb is None:
                doc.status = "failed"
                doc.error_message = "knowledge base missing"
                await db.commit()
                return

            try:
                doc.status = "processing"
                await db.commit()
                logger.info("[doc=%s name=%s] stage=start", doc_id, doc.filename)

                file_path = self._resolve_path(doc)

                logger.info("[doc=%s] stage=rasterize begin path=%s", doc_id, file_path)
                pages = self._raster.rasterize(file_path)
                logger.info("[doc=%s] stage=rasterize done pages=%d", doc_id, len(pages))

                logger.info("[doc=%s] stage=ocr begin pages=%d", doc_id, len(pages))
                page_lines = await self._ocr.extract_pages(pages)
                total_lines = sum(len(lines) for lines in page_lines)
                logger.info("[doc=%s] stage=ocr done lines=%d", doc_id, total_lines)

                logger.info("[doc=%s] stage=recover begin", doc_id)
                pages_md = self._recover.recover_pages(
                    page_lines, [p.page_no for p in pages]
                )
                logger.info("[doc=%s] stage=recover done md_pages=%d", doc_id, len(pages_md))

                logger.info("[doc=%s] stage=chunk begin", doc_id)
                chunks = self._chunker.chunk(pages_md)
                logger.info("[doc=%s] stage=chunk done chunks=%d", doc_id, len(chunks))

                if not chunks:
                    doc.status = "failed"
                    doc.error_message = "no content extracted from PDF"
                    await db.commit()
                    logger.warning("[doc=%s] stage=failed reason=no_chunks", doc_id)
                    return

                logger.info("[doc=%s] stage=index begin chunks=%d", doc_id, len(chunks))
                await self._indexer.write_chunks(db, chunks, doc, kb)
                doc.status = "indexed"
                doc.chunk_count = len(chunks)
                kb.document_count = (kb.document_count or 0) + 1
                kb.chunk_count = (kb.chunk_count or 0) + len(chunks)
                await db.commit()
                logger.info("[doc=%s] stage=indexed chunks=%d", doc_id, len(chunks))
            except Exception as e:  # noqa: BLE001
                logger.exception("[doc=%s] stage=failed", doc_id)
                await db.rollback()
                doc2 = (
                    await db.execute(select(Document).where(Document.id == doc_id))
                ).scalar_one_or_none()
                if doc2 is not None:
                    doc2.status = "failed"
                    doc2.error_message = str(e)[:1000]
                    await db.commit()

    @staticmethod
    def _resolve_path(doc: Document) -> Path:
        # The upload route computes its base as
        # ``dirname(dirname(admin/routers/knowledge.py)) == admin/``
        # and saves to ``admin/data/kb/{kb_id}/{filename}``. From
        # admin/services/pdf/processor.py, ``parents[2]`` is that same
        # ``admin/`` directory, so we mirror the route's convention.
        admin_dir = Path(__file__).resolve().parents[2]
        return admin_dir / "data" / "kb" / doc.knowledge_base_id / doc.filename
