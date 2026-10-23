"""Regression coverage for upgrading legacy built-in knowledge rows."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.db import Base
from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.models.tenant import Tenant
from admin.services import builtin_knowledge
from admin.services.builtin_knowledge import BuiltinKnowledgeGroup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HAN_RE = re.compile(r"[\u3400-\u9fff]")


@pytest.mark.asyncio
async def test_sync_reuses_stable_id_when_legacy_name_differs(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'builtin-sync.db').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        tenant_id = "tenant-default"
        stable_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"insurance-copilot:{tenant_id}:builtin:sales_scripts",
            )
        )
        async with sessions() as db:
            db.add(Tenant(id=tenant_id, slug="default", name="Default"))
            db.add(
                KnowledgeBase(
                    id=stable_id,
                    tenant_id=tenant_id,
                    name="系统内置知识库 - 销售话术",
                    description="Legacy localized name",
                )
            )
            await db.commit()

        monkeypatch.setattr(
            builtin_knowledge,
            "get_builtin_knowledge_groups",
            lambda _workspace: (
                BuiltinKnowledgeGroup(
                    key="sales_scripts",
                    name=builtin_knowledge.BUILTIN_SALES_KB_NAME,
                    description="Built-in sales scenario scripts.",
                    knowledge_type="sales_script",
                    relative_paths=(),
                ),
            ),
        )
        monkeypatch.setattr(
            builtin_knowledge,
            "load_embedding_config",
            lambda: SimpleNamespace(model="test/model", dimensions=3),
        )
        monkeypatch.setattr(
            builtin_knowledge.StructuredMarkdownChunker,
            "from_env",
            lambda: SimpleNamespace(target_tokens=512),
        )

        summary = await builtin_knowledge.sync_builtin_knowledge(
            tmp_path,
            session_factory=sessions,
        )

        async with sessions() as db:
            rows = list((await db.scalars(KnowledgeBase.__table__.select())).all())
            knowledge_base = await db.get(KnowledgeBase, stable_id)

        assert summary["knowledge_bases"] == 1
        assert len(rows) == 1
        assert knowledge_base is not None
        assert knowledge_base.name == builtin_knowledge.BUILTIN_SALES_KB_NAME
        assert knowledge_base.status == "active"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_english_builtin_sync_is_idempotent_and_replaces_chunks(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'english-sync.db').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text(
                    "CREATE VIRTUAL TABLE knowledge_fts USING "
                    "fts5(doc_id, title, content, tokenize='unicode61')"
                )
            )
        async with sessions() as db:
            tenant_id = "tenant-default"
            sales_kb_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"insurance-copilot:{tenant_id}:builtin:sales_scripts",
                )
            )
            db.add(Tenant(id=tenant_id, slug="default", name="Default"))
            db.add(
                KnowledgeBase(
                    id=sales_kb_id,
                    tenant_id=tenant_id,
                    name=builtin_knowledge.BUILTIN_SALES_KB_NAME,
                    status="active",
                )
            )
            db.add(
                Document(
                    id="legacy-sales-document",
                    knowledge_base_id=sales_kb_id,
                    tenant_id=tenant_id,
                    filename="sales_scripts.md",
                    file_type="md",
                    status="indexed",
                    chunk_count=1,
                )
            )
            db.add(
                DocumentChunk(
                    id="legacy-chinese-chunk",
                    document_id="legacy-sales-document",
                    knowledge_base_id=sales_kb_id,
                    chunk_index=0,
                    content="舊中文銷售話術",
                    token_count=8,
                    chunk_metadata=json.dumps(
                        {
                            "source": "builtin_markdown",
                            "source_sha256": "obsolete",
                            "chunk_size": 512,
                            "chunk_overlap": 0,
                            "section_title": "舊中文章節",
                            "heading_path": ["舊中文章節"],
                        },
                        ensure_ascii=False,
                    ),
                )
            )
            await db.flush()
            await db.execute(
                text(
                    "INSERT INTO knowledge_fts(doc_id, title, content) "
                    "VALUES ('legacy-sales-document', 'sales_scripts.md', '舊中文銷售話術')"
                )
            )
            await db.commit()

        monkeypatch.setattr(
            builtin_knowledge,
            "load_embedding_config",
            lambda: SimpleNamespace(model="test/multilingual", dimensions=3),
        )

        first = await builtin_knowledge.sync_builtin_knowledge(
            PROJECT_ROOT,
            session_factory=sessions,
        )
        async with sessions() as db:
            first_documents = int(await db.scalar(select(func.count()).select_from(Document)) or 0)
            first_chunks = int(await db.scalar(select(func.count()).select_from(DocumentChunk)) or 0)

        second = await builtin_knowledge.sync_builtin_knowledge(
            PROJECT_ROOT,
            session_factory=sessions,
        )
        async with sessions() as db:
            documents = list((await db.scalars(select(Document))).all())
            chunks = list((await db.scalars(select(DocumentChunk))).all())

        assert first["files_synced"] == 16
        assert first["files_unchanged"] == 0
        assert second["files_synced"] == 0
        assert second["files_unchanged"] == 16
        assert len(documents) == first_documents == 16
        assert len(chunks) == first_chunks > 0
        assert all(row.id != "legacy-chinese-chunk" for row in chunks)
        assert len({(row.knowledge_base_id, row.filename) for row in documents}) == 16
        assert all(row.status == "indexed" for row in documents)
        for chunk in chunks:
            metadata = json.loads(chunk.chunk_metadata)
            assert not HAN_RE.search(chunk.content)
            assert not HAN_RE.search(metadata["section_title"])
            assert not HAN_RE.search(" ".join(metadata["heading_path"]))
            assert metadata["source_sha256"]
    finally:
        await engine.dispose()
