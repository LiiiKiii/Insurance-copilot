"""Idempotently synchronize built-in Markdown files into managed knowledge bases."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select, text

from admin.db import AsyncSessionFactory
from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.models.tenant import Tenant
from admin.services.embeddings import load_embedding_config
from admin.services.pdf.indexer import KnowledgeIndexer
from admin.services.structured_markdown import StructuredMarkdownChunker
from admin.utils import now_beijing

BUILTIN_SALES_KB_NAME = "Built-in Sales Scripts"
BUILTIN_BEST_PRACTICE_KB_NAME = "Built-in Best Practices"
BUILTIN_COMPETITION_KB_NAME = "Built-in Competition Rules"


@dataclass(frozen=True)
class BuiltinKnowledgeGroup:
    key: str
    name: str
    description: str
    knowledge_type: str
    relative_paths: tuple[str, ...]


def get_builtin_knowledge_groups(workspace: Path) -> tuple[BuiltinKnowledgeGroup, ...]:
    knowledge_dir = workspace / "data" / "knowledge"
    competition_paths = {
        path.relative_to(workspace).as_posix()
        for pattern in ("competition_*.md", "mdrt_rules.md", "cot_rules.md")
        for path in knowledge_dir.glob(pattern)
    }
    competition_dir = knowledge_dir / "competitions"
    if competition_dir.exists():
        competition_paths.update(
            path.relative_to(workspace).as_posix()
            for path in competition_dir.glob("*.md")
        )
    return (
        BuiltinKnowledgeGroup(
            "sales_scripts",
            BUILTIN_SALES_KB_NAME,
            "Built-in insurance sales scenario scripts; synced from data/knowledge/sales_scripts.md.",
            "sales_script",
            ("data/knowledge/sales_scripts.md",),
        ),
        BuiltinKnowledgeGroup(
            "best_practices",
            BUILTIN_BEST_PRACTICE_KB_NAME,
            "Built-in insurance sales best practices; synced from data/knowledge/best_practices.md.",
            "best_practice",
            ("data/knowledge/best_practices.md",),
        ),
        BuiltinKnowledgeGroup(
            "competition_rules",
            BUILTIN_COMPETITION_KB_NAME,
            "Built-in competition, MDRT, COT and historical competition announcements.",
            "competition_rule",
            tuple(sorted(competition_paths)),
        ),
    )


async def sync_builtin_knowledge(
    workspace: Path,
    *,
    session_factory=None,
) -> dict[str, int]:
    factory = session_factory or AsyncSessionFactory
    chunker = StructuredMarkdownChunker.from_env()
    embedding_config = load_embedding_config()
    summary = {
        "knowledge_bases": 0,
        "files_synced": 0,
        "files_unchanged": 0,
        "chunks_written": 0,
    }
    async with factory() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == "default"))
        ).scalar_one_or_none()
        if tenant is None:
            raise RuntimeError("default tenant is required before syncing built-in knowledge")
        dialect = db.get_bind().dialect.name
        require_embeddings = dialect != "sqlite"

        for group in get_builtin_knowledge_groups(workspace):
            builtin_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"insurance-copilot:{tenant.id}:builtin:{group.key}",
                )
            )
            # The stable ID is authoritative. Earlier releases used localized
            # display names for these same IDs, so a name-only lookup tries to
            # insert an already-existing primary key after an upgrade.
            kb = await db.get(KnowledgeBase, builtin_id)
            if kb is None:
                kb = (
                    await db.execute(
                        select(KnowledgeBase).where(
                            KnowledgeBase.tenant_id == tenant.id,
                            KnowledgeBase.name == group.name,
                        )
                    )
                ).scalars().first()
            if kb is None:
                kb = KnowledgeBase(
                    id=builtin_id,
                    tenant_id=tenant.id,
                    name=group.name,
                    description=group.description,
                    kb_type="document",
                    embedding_model_id=embedding_config.model,
                    chunk_size=chunker.target_tokens,
                    chunk_overlap=0,
                    top_k=5,
                    status="building",
                )
                db.add(kb)
                await db.flush()
            else:
                if kb.tenant_id != tenant.id:
                    raise RuntimeError(
                        f"built-in knowledge ID {builtin_id} belongs to another tenant"
                    )
                kb.name = group.name
                kb.description = group.description
                kb.embedding_model_id = embedding_config.model
                kb.chunk_size = chunker.target_tokens
                kb.chunk_overlap = 0
                kb.status = "building"
            summary["knowledge_bases"] += 1

            for relative_path in group.relative_paths:
                source_path = workspace / relative_path
                if not source_path.is_file():
                    raise FileNotFoundError(f"built-in knowledge file missing: {relative_path}")
                content = source_path.read_text(encoding="utf-8", errors="replace")
                source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                structured = chunker.chunk(content)
                if not structured:
                    raise RuntimeError(f"no chunks produced for {relative_path}")
                document = (
                    await db.execute(
                        select(Document).where(
                            Document.knowledge_base_id == kb.id,
                            Document.filename == source_path.name,
                        )
                    )
                ).scalars().first()
                existing = []
                if document is not None:
                    existing = list(
                        (
                            await db.execute(
                                select(DocumentChunk)
                                .where(DocumentChunk.document_id == document.id)
                                .order_by(DocumentChunk.chunk_index)
                            )
                        ).scalars().all()
                    )
                if _is_current(
                    document,
                    existing,
                    source_hash,
                    len(structured),
                    chunker.target_tokens,
                    embedding_config.model,
                    embedding_config.dimensions,
                    require_embeddings,
                ):
                    summary["files_unchanged"] += 1
                    continue

                if document is None:
                    document = Document(
                        id=str(uuid.uuid4()),
                        knowledge_base_id=kb.id,
                        tenant_id=tenant.id,
                        filename=source_path.name,
                        file_type="md",
                        file_size=source_path.stat().st_size,
                        status="processing",
                        chunk_count=len(structured),
                        created_at=now_beijing(),
                    )
                    db.add(document)
                    await db.flush()
                else:
                    if dialect == "sqlite":
                        await db.execute(
                            text("DELETE FROM knowledge_fts WHERE doc_id = :doc_id"),
                            {"doc_id": document.id},
                        )
                    await db.execute(
                        delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
                    )
                    document.file_size = source_path.stat().st_size
                    document.status = "processing"
                    document.error_message = None
                    document.chunk_count = len(structured)

                await KnowledgeIndexer().write_chunks(
                    db,
                    [item.chunk for item in structured],
                    document,
                    kb,
                    source="builtin_markdown",
                    metadata_overrides=[
                        {
                            "source_path": relative_path,
                            "source_sha256": source_hash,
                            "knowledge_type": group.knowledge_type,
                            "section_title": item.section_title[:300],
                            "chunk_strategy": item.chunk_strategy,
                            "is_builtin": True,
                        }
                        for item in structured
                    ],
                )
                document.status = "indexed"
                summary["files_synced"] += 1
                summary["chunks_written"] += len(structured)

            await db.flush()
            kb.document_count = int(
                await db.scalar(
                    select(func.count()).select_from(Document).where(
                        Document.knowledge_base_id == kb.id
                    )
                ) or 0
            )
            kb.chunk_count = int(
                await db.scalar(
                    select(func.count()).select_from(DocumentChunk).where(
                        DocumentChunk.knowledge_base_id == kb.id
                    )
                ) or 0
            )
            kb.status = "active"
        await db.commit()
    return summary


def _is_current(
    document: Document | None,
    chunks: list[DocumentChunk],
    source_hash: str,
    expected_count: int,
    chunk_size: int,
    embedding_model: str,
    embedding_dimensions: int,
    require_embeddings: bool,
) -> bool:
    if document is None or document.status != "indexed" or not chunks:
        return False
    if document.chunk_count != len(chunks) or len(chunks) != expected_count:
        return False
    if require_embeddings and any(chunk.embedding is None for chunk in chunks):
        return False
    for chunk in chunks:
        try:
            metadata = json.loads(chunk.chunk_metadata or "{}")
        except (TypeError, ValueError):
            return False
        if (
            metadata.get("source") != "builtin_markdown"
            or metadata.get("source_sha256") != source_hash
            or metadata.get("chunk_size") != chunk_size
            or metadata.get("chunk_overlap") != 0
        ):
            return False
        if require_embeddings and (
            metadata.get("embedding_model") != embedding_model
            or metadata.get("embedding_dimensions") != embedding_dimensions
        ):
            return False
    return True
