"""Baseline acceptance tests for knowledge upload boundaries."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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
from admin.models.knowledge import KnowledgeBase
from admin.models.tenant import Tenant
from admin.routers.knowledge import MAX_UPLOAD_BYTES, _authorise_kb, upload_document


@pytest_asyncio.fixture
async def knowledge_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

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
