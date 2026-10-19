"""Tests for DocumentProcessor with all five adapters mocked."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin.db import Base
from admin.models import (  # noqa: F401
    agent_data,
    assessment,
    audit,
    competition,
    config,
    flow_log,
    inbox,
    knowledge,
    model_config,
    performance_target,
    tenant,
    usage,
    user,
)
from admin.models.knowledge import Document, KnowledgeBase
from admin.services.pdf.indexer import KnowledgeIndexer
from admin.services.pdf.processor import DocumentProcessor
from admin.services.pdf.types import Chunk, PageImage, PageMarkdown


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
                "doc_id, title, content, tokenize='unicode61')"
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed(factory, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    async with factory() as db:
        kb = KnowledgeBase(
            id="kb-1",
            tenant_id="t-1",
            name="kb",
            document_count=0,
            chunk_count=0,
            status="active",
        )
        doc = Document(
            id="doc-1",
            knowledge_base_id="kb-1",
            tenant_id="t-1",
            filename="x.pdf",
            file_type="pdf",
            file_size=8,
            status="pending",
        )
        db.add(kb)
        db.add(doc)
        await db.commit()
    return pdf


def _make_processor(factory, *, pages=None, ocr_lines=None, chunks=None):
    raster = MagicMock()
    raster.rasterize.return_value = pages or [PageImage(1, b"\x89PNG", 10, 10)]
    ocr = MagicMock()
    ocr.extract_pages = AsyncMock(return_value=ocr_lines or [[]])
    recoverer = MagicMock()
    recoverer.recover_pages.return_value = [
        PageMarkdown(page_no=1, markdown="# 第一章\n\n正文。", source="ocr")
    ]
    chunker = MagicMock()
    chunker.chunk.return_value = (
        chunks
        if chunks is not None
        else [Chunk(0, "第一章 正文。", 1, (1, 1), ["第一章"], 5, "section")]
    )
    return DocumentProcessor(factory, raster, ocr, recoverer, chunker, KnowledgeIndexer())


@pytest.mark.asyncio
async def test_happy_path_transitions_to_indexed(session_factory, tmp_path, monkeypatch):
    pdf = await _seed(session_factory, tmp_path)
    proc = _make_processor(session_factory)
    monkeypatch.setattr(proc, "_resolve_path", lambda doc: pdf)
    await proc.process_document("doc-1")
    async with session_factory() as db:
        d = (await db.execute(select(Document).where(Document.id == "doc-1"))).scalar_one()
        assert d.status == "indexed"
        assert d.chunk_count == 1
        kb = (
            await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == "kb-1"))
        ).scalar_one()
        assert kb.document_count == 1
        assert kb.chunk_count == 1


@pytest.mark.asyncio
async def test_no_chunks_marks_failed(session_factory, tmp_path, monkeypatch):
    pdf = await _seed(session_factory, tmp_path)
    proc = _make_processor(session_factory, chunks=[])
    monkeypatch.setattr(proc, "_resolve_path", lambda doc: pdf)
    await proc.process_document("doc-1")
    async with session_factory() as db:
        d = (await db.execute(select(Document).where(Document.id == "doc-1"))).scalar_one()
        assert d.status == "failed"
        assert "no content" in (d.error_message or "")


@pytest.mark.asyncio
async def test_rasterizer_exception_marks_failed(session_factory, tmp_path, monkeypatch):
    pdf = await _seed(session_factory, tmp_path)
    proc = _make_processor(session_factory)
    proc._raster.rasterize.side_effect = RuntimeError("cannot open pdf: bad header")
    monkeypatch.setattr(proc, "_resolve_path", lambda doc: pdf)
    await proc.process_document("doc-1")
    async with session_factory() as db:
        d = (await db.execute(select(Document).where(Document.id == "doc-1"))).scalar_one()
        assert d.status == "failed"
        assert "cannot open pdf" in (d.error_message or "")
