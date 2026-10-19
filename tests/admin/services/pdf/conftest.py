"""Shared fixtures: in-memory SQLite engine with FTS5 virtual table."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from admin.db import Base

# Importing models registers them with Base.metadata
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


@pytest_asyncio.fixture
async def memory_db_session() -> AsyncSession:
    """In-memory async SQLite with FTS5 table created (mirrors init_db())."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5("
                "doc_id, title, content, tokenize='unicode61')"
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()
