"""Admin Tool: List knowledge bases, documents and chunks."""
import json
from pathlib import Path
from typing import Any
from nanobot.agent.tools.base import Tool


class AdminListKnowledgeTool(Tool):
    def __init__(self, workspace: Path):
        self._db_path = str(workspace / "data" / "db" / "admin.db")

    @property
    def name(self) -> str:
        return "admin_list_knowledge"

    @property
    def description(self) -> str:
        return (
            "List knowledge bases and their document, chunk, and status summaries. "
            "Pass a knowledge-base ID to inspect its documents."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "kb_id": {
                    "type": "string",
                    "description": "Optional knowledge-base ID whose documents should be listed",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        kb_id = kwargs.get("kb_id")
        try:
            from admin.db import get_sync_db
            from admin.models.knowledge import KnowledgeBase, Document

            with get_sync_db() as db:
                if kb_id:
                    docs = db.query(Document).filter(
                        Document.knowledge_base_id == kb_id
                    ).order_by(Document.created_at).all()
                    return json.dumps({
                        "kb_id": kb_id,
                        "documents": [
                            {
                                "id": d.id,
                                "filename": d.filename,
                                "file_type": d.file_type,
                                "file_size": d.file_size,
                                "status": d.status,
                                "chunk_count": d.chunk_count,
                                "created_at": d.created_at,
                            }
                            for d in docs
                        ],
                    }, ensure_ascii=False, indent=2, default=str)

                kbs = db.query(KnowledgeBase).order_by(KnowledgeBase.name).all()
                return json.dumps({
                    "knowledge_bases": [
                        {
                            "id": k.id,
                            "name": k.name,
                            "description": k.description,
                            "status": k.status,
                            "document_count": k.document_count,
                            "chunk_count": k.chunk_count,
                            "created_at": k.created_at,
                        }
                        for k in kbs
                    ],
                }, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)[:300]}, ensure_ascii=False)
