"""Admin Tool: Import local text files into a managed knowledge base.

The text path reuses the PDF upload pipeline's token-aware Markdown chunker and
the shared :class:`KnowledgeIndexer`, so PostgreSQL imports receive the same
embedding model, validation, metadata and vector persistence behaviour as
uploaded PDFs. SQLite keeps the FTS5 mirror fallback without embeddings.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from admin.db import AsyncSessionFactory
from admin.models.knowledge import Document, KnowledgeBase
from admin.services.pdf.chunker import MarkdownChunker
from admin.services.pdf.indexer import KnowledgeIndexer
from admin.services.pdf.types import PageMarkdown
from admin.utils import now_beijing
from nanobot.agent.tools.base import Tool

_SUFFIXES = {".md", ".txt", ".csv"}


class AdminKBImportTool(Tool):
    def __init__(self, workspace: Path, session_factory=None):
        self._workspace = workspace
        self._session_factory = session_factory or AsyncSessionFactory

    @property
    def name(self) -> str:
        return "admin_kb_import"

    @property
    def description(self) -> str:
        return (
            "Import a project-local .md, .txt, or .csv file into a knowledge base. "
            "Uses the same token-aware chunking, overlap and embedding pipeline as "
            "PDF upload; chunks are stored in documents/document_chunks and receive "
            "semantic vectors on PostgreSQL."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "kb_id": {
                    "type": "string",
                    "description": "Destination knowledge-base ID; use admin_list_knowledge to discover IDs",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path relative to the project root, for example data/knowledge/best_practices.md",
                },
            },
            "required": ["kb_id", "file_path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        kb_id = kwargs["kb_id"]
        rel_path = kwargs["file_path"].lstrip("/")

        target = self._workspace / rel_path
        try:
            target.resolve().relative_to(self._workspace.resolve())
        except ValueError:
            return json.dumps({"error": "The path is outside the project workspace"})

        if not target.exists() or not target.is_file():
            return json.dumps({"error": f"File not found: {rel_path}"})

        suffix = target.suffix.lower()
        if suffix not in _SUFFIXES:
            return json.dumps({"error": "Supported file types are .md, .txt, and .csv"})

        content = target.read_text(encoding="utf-8", errors="replace")
        file_size = target.stat().st_size
        filename = target.name
        file_type = suffix.lstrip(".").lower() or "txt"

        # Text imports use the same tokenizer-aware chunker and environment
        # settings as the PDF upload pipeline. A text file is represented as a
        # single logical page; Markdown headings are still preserved.
        chunker = MarkdownChunker.from_env()
        chunks = chunker.chunk(
            [PageMarkdown(page_no=1, markdown=content, source=file_type)]
        )
        if not chunks:
            return json.dumps({"error": "The source file does not contain importable text"})

        try:
            async with self._session_factory() as db:
                # Confirm that the destination exists.
                kb = (
                    await db.execute(
                        select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
                    )
                ).scalar_one_or_none()
                if kb is None:
                    return json.dumps({"error": f"Knowledge base {kb_id} does not exist"})

                # Reject duplicate filenames within one knowledge base.
                existing = (
                    await db.execute(
                        select(Document).where(
                            Document.knowledge_base_id == kb_id,
                            Document.filename == filename,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return json.dumps(
                        {"error": f"File {filename} already exists in this knowledge base"}
                    )

                doc_id = str(uuid.uuid4())
                doc = Document(
                    id=doc_id,
                    knowledge_base_id=kb_id,
                    tenant_id=kb.tenant_id,
                    filename=filename,
                    file_type=file_type,
                    file_size=file_size,
                    status="processing",
                    chunk_count=len(chunks),
                    created_at=now_beijing(),
                )
                db.add(doc)
                await db.flush()

                # Reuse the PDF pipeline's indexer so PostgreSQL imports get the
                # same embedding model, validation, metadata, and vector
                # persistence behaviour; SQLite mirrors chunks into FTS5.
                await KnowledgeIndexer().write_chunks(
                    db,
                    chunks,
                    doc,
                    kb,
                    source=file_type,
                )

                doc.status = "indexed"
                doc.chunk_count = len(chunks)
                kb.document_count = (kb.document_count or 0) + 1
                kb.chunk_count = (kb.chunk_count or 0) + len(chunks)

                kb_name = kb.name
                is_sqlite = db.get_bind().dialect.name == "sqlite"
                await db.commit()

            return json.dumps(
                {
                    "success": True,
                    "filename": filename,
                    "kb_name": kb_name,
                    "chunks_created": len(chunks),
                    "embeddings_created": 0 if is_sqlite else len(chunks),
                    "chunk_size": chunks[0].chunk_size,
                    "chunk_overlap": chunks[0].chunk_overlap,
                    "file_size": file_size,
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)[:300]}, ensure_ascii=False)
