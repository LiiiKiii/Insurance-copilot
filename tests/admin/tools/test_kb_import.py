"""Tests for the admin text-file knowledge-base import path.

The text import reuses the PDF pipeline's token-aware Markdown chunker and the
shared KnowledgeIndexer: on PostgreSQL chunks receive embeddings, while SQLite
mirrors chunks into FTS5 without vectors.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.db import Base
from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.models.tenant import Tenant

from nanobot.agent.tools.admin.kb_import import AdminKBImportTool


@pytest_asyncio.fixture
async def kb_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE knowledge_fts USING fts5("
                "doc_id, title, content, tokenize='unicode61')"
            )
        )

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as db:
        db.add(Tenant(id="tenant-1", slug="tenant-1", name="Tenant 1"))
        db.add(
            KnowledgeBase(
                id="kb-1",
                tenant_id="tenant-1",
                name="Imported files",
                document_count=0,
                chunk_count=0,
                status="active",
            )
        )
        await db.commit()

    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_import_uses_shared_token_chunker_overlap_and_indexer(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    kb_session_factory,
):
    monkeypatch.setenv("RAG_CHUNK_SIZE", "30")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP", "7")
    source = tmp_path / "rules.md"
    source.write_text(
        "# Rules\n\n" + "\n\n".join(f"Rule {i}: detailed insurance guidance text." for i in range(30)),
        encoding="utf-8",
    )

    tool = AdminKBImportTool(tmp_path, session_factory=kb_session_factory)
    result = json.loads(
        await tool.execute(kb_id="kb-1", file_path="rules.md")
    )

    assert result["success"] is True
    assert result["chunks_created"] > 2
    assert result["embeddings_created"] == 0  # SQLite mirrors the PDF fallback.
    assert result["chunk_size"] == 30
    assert result["chunk_overlap"] == 7

    async with kb_session_factory() as db:
        document = (
            await db.execute(select(Document).where(Document.filename == "rules.md"))
        ).scalar_one()
        rows = (
            await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index)
            )
        ).scalars().all()

    assert document.status == "indexed"
    assert len(rows) == result["chunks_created"]
    for previous, current in zip(rows, rows[1:]):
        metadata = json.loads(current.chunk_metadata)
        assert metadata["source"] == "md"
        assert metadata["chunk_size"] == 30
        assert 0 < metadata["overlap_from_previous_tokens"] <= 7
        assert any(
            previous.content.endswith(current.content[:size])
            for size in range(1, min(len(previous.content), len(current.content)) + 1)
        )


@pytest.mark.asyncio
async def test_import_rejects_unsupported_suffix(tmp_path, kb_session_factory):
    source = tmp_path / "notes.pdf"
    source.write_text("not a text import", encoding="utf-8")
    tool = AdminKBImportTool(tmp_path, session_factory=kb_session_factory)
    result = json.loads(await tool.execute(kb_id="kb-1", file_path="notes.pdf"))
    assert "error" in result
    assert "md, .txt, and .csv" in result["error"]


@pytest.mark.asyncio
async def test_import_rejects_duplicate_filename(tmp_path, kb_session_factory):
    source = tmp_path / "notes.txt"
    source.write_text("Shared text body for the knowledge base.", encoding="utf-8")
    tool = AdminKBImportTool(tmp_path, session_factory=kb_session_factory)

    first = json.loads(await tool.execute(kb_id="kb-1", file_path="notes.txt"))
    assert first["success"] is True
    second = json.loads(await tool.execute(kb_id="kb-1", file_path="notes.txt"))
    assert "error" in second
    assert "already exists" in second["error"]
