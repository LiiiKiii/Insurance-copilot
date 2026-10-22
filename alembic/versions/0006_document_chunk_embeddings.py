"""Add pgvector embeddings to document chunks.

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE SCHEMA IF NOT EXISTS extensions")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN IF NOT EXISTS embedding extensions.vector(1536)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw "
        "(embedding extensions.vector_cosine_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS document_chunks_embedding_hnsw")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")
