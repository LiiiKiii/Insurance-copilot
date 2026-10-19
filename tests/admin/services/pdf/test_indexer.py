"""Tests for KnowledgeIndexer including FTS5 rowid alignment."""
import json

import pytest
from sqlalchemy import select, text

from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.services.pdf.indexer import KnowledgeIndexer
from admin.services.pdf.types import Chunk


@pytest.fixture
def kb_and_doc() -> tuple[KnowledgeBase, Document]:
    kb = KnowledgeBase(
        id="kb-1",
        tenant_id="t-1",
        name="test kb",
        document_count=0,
        chunk_count=0,
        status="active",
    )
    doc = Document(
        id="doc-1",
        knowledge_base_id="kb-1",
        tenant_id="t-1",
        filename="policy.pdf",
        file_type="pdf",
        file_size=1000,
        status="processing",
    )
    return kb, doc


def make_chunk(idx: int, content: str) -> Chunk:
    return Chunk(
        index=idx,
        content=content,
        page_no=1,
        page_range=(1, 1),
        heading_path=["第一章 总则"],
        token_count=10,
        chunk_type="section",
    )


@pytest.mark.asyncio
async def test_write_chunks_inserts_document_chunks(memory_db_session, kb_and_doc):
    kb, doc = kb_and_doc
    memory_db_session.add(kb)
    memory_db_session.add(doc)
    await memory_db_session.flush()

    indexer = KnowledgeIndexer()
    chunks = [make_chunk(0, "第一段内容"), make_chunk(1, "第二段内容")]
    await indexer.write_chunks(memory_db_session, chunks, doc, kb)
    await memory_db_session.flush()

    rows = (
        await memory_db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        )
    ).scalars().all()
    assert len(rows) == 2
    assert {r.content for r in rows} == {"第一段内容", "第二段内容"}


@pytest.mark.asyncio
async def test_write_chunks_inserts_fts5_with_aligned_rowid(memory_db_session, kb_and_doc):
    kb, doc = kb_and_doc
    memory_db_session.add(kb)
    memory_db_session.add(doc)
    await memory_db_session.flush()

    indexer = KnowledgeIndexer()
    chunks = [make_chunk(0, "重大疾病保险责任")]
    await indexer.write_chunks(memory_db_session, chunks, doc, kb)
    await memory_db_session.flush()

    result = (
        await memory_db_session.execute(
            text(
                "SELECT dc.content FROM knowledge_fts fts "
                "JOIN document_chunks dc ON dc.rowid = fts.rowid "
                "WHERE knowledge_fts MATCH :q"
            ),
            {"q": "重大疾病*"},
        )
    ).fetchall()
    assert len(result) == 1
    assert result[0][0] == "重大疾病保险责任"


@pytest.mark.asyncio
async def test_metadata_contains_page_and_heading(memory_db_session, kb_and_doc):
    kb, doc = kb_and_doc
    memory_db_session.add(kb)
    memory_db_session.add(doc)
    await memory_db_session.flush()

    indexer = KnowledgeIndexer()
    await indexer.write_chunks(memory_db_session, [make_chunk(0, "x")], doc, kb)
    await memory_db_session.flush()

    row = (
        await memory_db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        )
    ).scalars().one()
    meta = json.loads(row.chunk_metadata)
    assert meta["page_no"] == 1
    assert meta["page_range"] == [1, 1]
    assert meta["heading_path"] == ["第一章 总则"]
    assert meta["source"] == "ocr"
