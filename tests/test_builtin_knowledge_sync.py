"""Regression coverage for upgrading legacy built-in knowledge rows."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.db import Base
from admin.models.knowledge import KnowledgeBase
from admin.models.tenant import Tenant
from admin.services import builtin_knowledge
from admin.services.builtin_knowledge import BuiltinKnowledgeGroup


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
