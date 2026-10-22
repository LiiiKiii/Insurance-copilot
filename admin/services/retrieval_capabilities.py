"""Runtime capability checks for selectable knowledge retrieval."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from sqlalchemy import text

from admin.db import _is_sqlite, engine
from admin.services.embeddings import EmbeddingError, load_embedding_config


@dataclass(frozen=True)
class RetrievalMethodCapability:
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class RetrievalCapabilities:
    keyword: RetrievalMethodCapability
    vector: RetrievalMethodCapability

    def to_dict(self) -> dict[str, dict[str, bool | str | None]]:
        return {"keyword": asdict(self.keyword), "vector": asdict(self.vector)}


async def get_retrieval_capabilities() -> RetrievalCapabilities:
    keyword = RetrievalMethodCapability(available=True)
    if _is_sqlite:
        return RetrievalCapabilities(
            keyword,
            RetrievalMethodCapability(False, "Vector retrieval requires PostgreSQL with pgvector."),
        )
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return RetrievalCapabilities(
            keyword,
            RetrievalMethodCapability(False, "OPENROUTER_API_KEY is not configured."),
        )
    try:
        config = load_embedding_config()
    except (EmbeddingError, ValueError):
        return RetrievalCapabilities(
            keyword, RetrievalMethodCapability(False, "Embedding configuration is invalid.")
        )
    statement = text(
        """
        SELECT
            EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS has_vector_extension,
            (
                SELECT format_type(attribute.atttypid, attribute.atttypmod)
                FROM pg_attribute AS attribute
                WHERE attribute.attrelid = to_regclass('document_chunks')
                  AND attribute.attname = 'embedding'
                  AND attribute.attnum > 0
                  AND NOT attribute.attisdropped
            ) AS embedding_type
        """
    )
    try:
        async with engine.connect() as connection:
            row = (await connection.execute(statement)).mappings().one()
    except Exception:
        return RetrievalCapabilities(
            keyword,
            RetrievalMethodCapability(False, "Unable to verify PostgreSQL/pgvector configuration."),
        )
    expected = f"vector({config.dimensions})"
    if not row["has_vector_extension"]:
        reason = "The pgvector extension is not enabled."
    elif row["embedding_type"] is None:
        reason = "The document_chunks.embedding column is missing."
    elif row["embedding_type"] != expected:
        reason = f"The embedding column is {row['embedding_type']}; expected {expected}."
    else:
        reason = None
    return RetrievalCapabilities(keyword, RetrievalMethodCapability(reason is None, reason))
