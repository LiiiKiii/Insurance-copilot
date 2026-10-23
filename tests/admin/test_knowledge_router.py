"""Baseline acceptance tests for knowledge upload boundaries."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.routers import knowledge as knowledge_router
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
from admin.models.tenant import Tenant
from admin.routers.knowledge import (
    MAX_UPLOAD_BYTES,
    _authorise_kb,
    delete_document,
    delete_kb,
    upload_document,
)


@pytest_asyncio.fixture
async def knowledge_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                "CREATE VIRTUAL TABLE knowledge_fts USING fts5("
                "doc_id, title, content, tokenize='unicode61'"
                ")"
            )
        )

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        session.add_all(
            [
                Tenant(id="tenant-a", slug="tenant-a", name="Tenant A"),
                Tenant(id="tenant-b", slug="tenant-b", name="Tenant B"),
                KnowledgeBase(
                    id="kb-a",
                    tenant_id="tenant-a",
                    name="Tenant A Knowledge",
                    status="active",
                ),
                KnowledgeBase(
                    id="kb-b",
                    tenant_id="tenant-b",
                    name="Tenant B Knowledge",
                    status="active",
                ),
            ]
        )
        await session.commit()
        yield session

    await engine.dispose()


def _user(tenant_id: str):
    return SimpleNamespace(tenant_id=tenant_id, is_superadmin=False)


@pytest.mark.asyncio
async def test_knowledge_base_access_is_tenant_scoped(knowledge_session):
    with pytest.raises(HTTPException) as exc_info:
        await _authorise_kb("kb-b", _user("tenant-a"), knowledge_session)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf_documents(knowledge_session):
    upload = UploadFile(filename="notes.txt", file=BytesIO(b"plain text"))

    with pytest.raises(HTTPException) as exc_info:
        await upload_document("kb-a", _user("tenant-a"), knowledge_session, upload)

    assert exc_info.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_documents_over_the_size_limit(knowledge_session):
    class OversizedUpload:
        filename = "oversized.pdf"

        async def read(self, size: int) -> bytes:
            assert size == MAX_UPLOAD_BYTES + 1
            return b"x" * size

    with pytest.raises(HTTPException) as exc_info:
        await upload_document(
            "kb-a", _user("tenant-a"), knowledge_session, OversizedUpload()
        )

    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_still_rejects_filename_present_in_database(
    knowledge_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(knowledge_router, "_KB_STORAGE_ROOT", tmp_path)
    knowledge_session.add(
        Document(
            id="doc-a",
            knowledge_base_id="kb-a",
            tenant_id="tenant-a",
            filename="policy.pdf",
            file_type="pdf",
            file_size=7,
            status="indexed",
        )
    )
    await knowledge_session.commit()

    upload = UploadFile(filename="policy.pdf", file=BytesIO(b"new pdf"))
    with pytest.raises(HTTPException) as exc_info:
        await upload_document(
            "kb-a", _user("tenant-a"), knowledge_session, upload
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_deleted_document_can_be_uploaded_again(
    knowledge_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(knowledge_router, "_KB_STORAGE_ROOT", tmp_path)

    kb = await knowledge_session.get(KnowledgeBase, "kb-a")
    kb.document_count = 1
    document = Document(
        id="doc-a",
        knowledge_base_id="kb-a",
        tenant_id="tenant-a",
        filename="policy.pdf",
        file_type="pdf",
        file_size=7,
        status="indexed",
    )
    knowledge_session.add(document)
    await knowledge_session.commit()

    stored_file = tmp_path / "kb-a" / "policy.pdf"
    stored_file.parent.mkdir(parents=True)
    stored_file.write_bytes(b"old pdf")

    result = await delete_document(
        "kb-a", "doc-a", _user("tenant-a"), knowledge_session
    )

    assert result["ok"] is True
    assert not stored_file.exists()
    assert await knowledge_session.get(Document, "doc-a") is None

    async def ignore_processing(_doc_id: str) -> None:
        return None

    monkeypatch.setattr(
        knowledge_router, "_run_document_processor", ignore_processing
    )
    upload = UploadFile(filename="policy.pdf", file=BytesIO(b"new pdf"))
    uploaded = await upload_document(
        "kb-a", _user("tenant-a"), knowledge_session, upload
    )

    assert uploaded["ok"] is True
    assert uploaded["data"]["filename"] == "policy.pdf"
    assert stored_file.read_bytes() == b"new pdf"


@pytest.mark.asyncio
async def test_upload_replaces_file_orphaned_by_old_deletion(
    knowledge_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(knowledge_router, "_KB_STORAGE_ROOT", tmp_path)

    stored_file = tmp_path / "kb-a" / "policy.pdf"
    stored_file.parent.mkdir(parents=True)
    stored_file.write_bytes(b"orphaned pdf")

    async def ignore_processing(_doc_id: str) -> None:
        return None

    monkeypatch.setattr(
        knowledge_router, "_run_document_processor", ignore_processing
    )
    upload = UploadFile(filename="policy.pdf", file=BytesIO(b"replacement pdf"))

    uploaded = await upload_document(
        "kb-a", _user("tenant-a"), knowledge_session, upload
    )

    assert uploaded["ok"] is True
    assert stored_file.read_bytes() == b"replacement pdf"


@pytest.mark.asyncio
async def test_delete_kb_removes_all_stored_files(
    knowledge_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(knowledge_router, "_KB_STORAGE_ROOT", tmp_path)

    document = Document(
        id="doc-a",
        knowledge_base_id="kb-a",
        tenant_id="tenant-a",
        filename="policy.pdf",
        file_type="pdf",
        file_size=7,
        status="indexed",
    )
    knowledge_session.add(document)
    await knowledge_session.commit()

    kb_dir = tmp_path / "kb-a"
    kb_dir.mkdir(parents=True)
    (kb_dir / "policy.pdf").write_bytes(b"old pdf")
    (kb_dir / "orphaned.pdf").write_bytes(b"orphaned pdf")

    result = await delete_kb("kb-a", _user("tenant-a"), knowledge_session)

    assert result["ok"] is True
    assert not kb_dir.exists()
    assert await knowledge_session.get(Document, "doc-a") is None
    assert await knowledge_session.get(KnowledgeBase, "kb-a") is None
