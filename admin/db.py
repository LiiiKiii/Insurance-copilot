"""Database connection and session management for the administrative backend.

The A1 data layer provides asynchronous sessions for future API routes and
synchronous sessions for business tools. SQLite is used by default, while a
custom ``ADMIN_DATABASE_URL`` can select another SQLAlchemy-supported backend.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "admin.db"

load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.environ.get(
    "ADMIN_DATABASE_URL",
    f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}",
)

_SYNC_URL_MAP = {"+asyncpg": "+psycopg", "+aiosqlite": ""}
SYNC_DATABASE_URL = DATABASE_URL
for _async_driver, _sync_driver in _SYNC_URL_MAP.items():
    SYNC_DATABASE_URL = SYNC_DATABASE_URL.replace(_async_driver, _sync_driver)

_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
_pool_config = {} if _is_sqlite else {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10,
    "pool_recycle": 600,
    "pool_timeout": 30,
}

engine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("ADMIN_DB_ECHO", "0") == "1",
    connect_args=_connect_args,
    **_pool_config,
)
AsyncSessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=os.environ.get("ADMIN_DB_ECHO", "0") == "1",
    connect_args=_connect_args,
    **_pool_config,
)
SyncSessionFactory = sessionmaker(sync_engine, expire_on_commit=False)


@contextlib.contextmanager
def get_sync_db():
    """Provide a transactional synchronous database session."""
    session: Session = SyncSessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class Base(DeclarativeBase):
    """Declarative base shared by all administrative models."""


async def get_db():
    """Provide a transactional asynchronous database session."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create the A1 business-data tables that are currently available."""
    if _is_sqlite:
        database_path = make_url(DATABASE_URL).database
        if database_path and database_path != ":memory:":
            Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    from admin.models import agent_data, competition, performance_target  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose database connection pools during application shutdown."""
    await engine.dispose()
    sync_engine.dispose()
