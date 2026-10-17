"""Admin Tool: Import files into knowledge base."""
import json
import uuid
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool


class AdminKBImportTool(Tool):
    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._db_path = str(workspace / "data" / "db" / "admin.db")

    @property
    def name(self) -> str:
        return "admin_kb_import"

    @property
    def description(self) -> str:
        return (
            "Import a project-local .md, .txt, or .csv file into a knowledge base. "
            "The file is split into chunks and indexed for keyword retrieval."
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
                "chunk_size": {
                    "type": "integer",
                    "description": "Maximum characters per chunk, from 100 to 4000",
                    "default": 500,
                    "minimum": 100,
                    "maximum": 4000,
                },
            },
            "required": ["kb_id", "file_path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        kb_id = kwargs["kb_id"]
        rel_path = kwargs["file_path"].lstrip("/")
        chunk_size = max(100, min(int(kwargs.get("chunk_size", 500)), 4000))

        target = self._workspace / rel_path
        try:
            target.resolve().relative_to(self._workspace.resolve())
        except ValueError:
            return json.dumps({"error": "The path is outside the project workspace"})

        if not target.exists() or not target.is_file():
            return json.dumps({"error": f"File not found: {rel_path}"})

        if target.suffix.lower() not in {".md", ".txt", ".csv"}:
            return json.dumps({"error": "Supported file types are .md, .txt, and .csv"})

        content = target.read_text(encoding="utf-8", errors="replace")
        file_size = target.stat().st_size
        filename = target.name

        # Split on paragraph boundaries, then combine short paragraphs.
        raw_chunks = [p.strip() for p in content.split("\n\n") if p.strip()]
        chunks = []
        current = ""
        for p in raw_chunks:
            if len(current) + len(p) < chunk_size:
                current = current + "\n\n" + p if current else p
            else:
                if current:
                    chunks.append(current)
                current = p
        if current:
            chunks.append(current)

        if not chunks:
            return json.dumps({"error": "The source file does not contain importable text"})

        try:
            from admin.db import get_sync_db
            from sqlalchemy import text

            from admin.models.knowledge import KnowledgeBase, Document, DocumentChunk
            from admin.utils import now_beijing

            with get_sync_db() as db:
                # Confirm that the destination exists.
                kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
                if not kb:
                    return json.dumps({"error": f"Knowledge base {kb_id} does not exist"})

                # Reject duplicate filenames within one knowledge base.
                existing = db.query(Document).filter(
                    Document.knowledge_base_id == kb_id,
                    Document.filename == filename,
                ).first()
                if existing:
                    return json.dumps({"error": f"File {filename} already exists in this knowledge base"})

                doc_id = str(uuid.uuid4())
                now = now_beijing()

                # Insert the document record.
                doc = Document(
                    id=doc_id,
                    knowledge_base_id=kb_id,
                    tenant_id=kb.tenant_id,
                    filename=filename,
                    file_type=target.suffix.lstrip("."),
                    file_size=file_size,
                    status="indexed",
                    chunk_count=len(chunks),
                    created_at=now,
                )
                db.add(doc)

                # Insert chunks and mirror them into SQLite FTS5.
                is_sqlite = db.get_bind().dialect.name == "sqlite"
                for idx, chunk_text in enumerate(chunks):
                    chunk = DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=doc_id,
                        knowledge_base_id=kb_id,
                        chunk_index=idx,
                        content=chunk_text,
                        token_count=len(chunk_text.split()),
                        chunk_metadata="{}",
                    )
                    db.add(chunk)

                    if is_sqlite:
                        db.flush()
                        rowid = db.scalar(
                            text("SELECT rowid FROM document_chunks WHERE id = :id"),
                            {"id": chunk.id},
                        )
                        db.execute(
                            text(
                                "INSERT INTO knowledge_fts(rowid, doc_id, title, content) "
                                "VALUES (:rowid, :doc_id, :title, :content)"
                            ),
                            {
                                "rowid": rowid,
                                "doc_id": doc_id,
                                "title": filename,
                                "content": chunk_text,
                            },
                        )

                # Maintain denormalised counters used by the admin view.
                kb.document_count += 1
                kb.chunk_count += len(chunks)

                kb_name = kb.name

            return json.dumps({
                "success": True,
                "filename": filename,
                "kb_name": kb_name,
                "chunks_created": len(chunks),
                "file_size": file_size,
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)[:300]}, ensure_ascii=False)

