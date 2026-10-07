"""PDF ingestion service package."""
from __future__ import annotations

from admin.services.pdf.chunker import MarkdownChunker
from admin.services.pdf.indexer import KnowledgeIndexer
from admin.services.pdf.layout_recoverer import LayoutRecoverer
from admin.services.pdf.ocr_extractor import OcrExtractor
from admin.services.pdf.processor import DocumentProcessor
from admin.services.pdf.rasterizer import PdfRasterizer

__all__ = [
    "DocumentProcessor",
    "KnowledgeIndexer",
    "LayoutRecoverer",
    "MarkdownChunker",
    "OcrExtractor",
    "PdfRasterizer",
    "get_document_processor",
]

_processor: DocumentProcessor | None = None


def get_document_processor() -> DocumentProcessor:
    """Process-wide singleton.

    Built lazily on first call so the RapidOCR ONNX model only loads when
    actually needed (not during unit tests that monkey-patch the singleton).
    """
    global _processor
    if _processor is None:
        from admin.db import AsyncSessionFactory

        _processor = DocumentProcessor(
            session_factory=AsyncSessionFactory,
            rasterizer=PdfRasterizer(),
            ocr=OcrExtractor(),
            recoverer=LayoutRecoverer(),
            chunker=MarkdownChunker(),
            indexer=KnowledgeIndexer(),
        )
    return _processor
