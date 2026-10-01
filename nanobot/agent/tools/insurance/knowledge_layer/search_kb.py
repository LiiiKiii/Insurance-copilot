"""Knowledge Layer: SearchKnowledgeBase — retrieves chunks from admin-managed KBs.

Uses sync SQLAlchemy engine for keyword search.
Reads from admin DB document_chunks table.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

from admin.db import sync_engine, _is_sqlite
from nanobot.agent.tools.base import Tool

logger = logging.getLogger(__name__)


def _search_fts(conn, keywords: list[str], kb_name: str | None, limit: int):
    """Try FTS5 MATCH first, fall back to None if unavailable (SQLite only)."""
    try:
        match_expr = " OR ".join(keywords)
        where = "knowledge_fts MATCH :match_expr"
        params: dict = {"match_expr": match_expr, "limit_val": limit}
        if kb_name:
            where += " AND kb.name LIKE :kb_name"
            params["kb_name"] = f"%{kb_name}%"
        sql = text(f"""
            SELECT dc.content, dc.token_count, d.filename, kb.name, dc.chunk_index
            FROM knowledge_fts fts
            JOIN document_chunks dc ON dc.rowid = fts.rowid
            JOIN documents d ON d.id = dc.document_id
            JOIN knowledge_bases kb ON kb.id = dc.knowledge_base_id
            WHERE {where}
            LIMIT :limit_val
        """)
        return conn.execute(sql, params).fetchall()
    except Exception:
        return None


class SearchKnowledgeBaseTool(Tool):
    """Search admin-managed knowledge bases for relevant content.
    Part of Knowledge Layer -- connects admin KB to agent reasoning."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "search_knowledge_base"

    @property
    def description(self) -> str:
        return (
            "Search knowledge bases for relevant information. "
            "Use when answering questions about company policies, product details, "
            "training materials, or any domain-specific knowledge that may have been "
            "uploaded by administrators."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in natural language",
                },
                "kb_name": {
                    "type": "string",
                    "description": "Optional: specific knowledge base name to search in",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query", "")
        kb_name = kwargs.get("kb_name")
        top_k = int(kwargs.get("top_k", 5))

        if not query:
            return json.dumps({"error": "Query is required"}, ensure_ascii=False)

        def _search() -> str:
            with sync_engine.connect() as conn:
                # 分詞用於匹配
                keywords = [kw.strip() for kw in query.split() if len(kw.strip()) >= 2]

                # 嘗試 FTS5（僅 SQLite 支持，PG 下跳過）
                rows = None
                if keywords and _is_sqlite:
                    rows = _search_fts(conn, keywords, kb_name, top_k)

                # 回退到 LIKE 查詢（PG 和 SQLite 均兼容）
                if not rows:
                    where_clauses: list[str] = []
                    params: dict = {"limit_val": top_k}

                    if kb_name:
                        where_clauses.append("kb.name LIKE :kb_name")
                        params["kb_name"] = f"%{kb_name}%"

                    if keywords:
                        kw_parts = []
                        for i, kw in enumerate(keywords):
                            key = f"kw_{i}"
                            kw_parts.append(f"dc.content LIKE :{key}")
                            params[key] = f"%{kw}%"
                        where_clauses.append(f"({' OR '.join(kw_parts)})")

                    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

                    sql = text(f"""
                        SELECT dc.content, dc.token_count, d.filename, kb.name, dc.chunk_index
                        FROM document_chunks dc
                        JOIN documents d ON d.id = dc.document_id
                        JOIN knowledge_bases kb ON kb.id = dc.knowledge_base_id
                        WHERE {where_sql}
                        ORDER BY dc.chunk_index
                        LIMIT :limit_val
                    """)
                    rows = conn.execute(sql, params).fetchall()

                # 獲取 KB 列表供上下文參考
                kb_list = conn.execute(
                    text("SELECT name, document_count FROM knowledge_bases WHERE status = 'active'")
                ).fetchall()

            if not rows:
                kb_names = [r[0] for r in kb_list]
                return json.dumps({
                    "found": False,
                    "query": query,
                    "message": f"No matching content found. Available knowledge bases: {', '.join(kb_names) if kb_names else 'none'}",
                    "available_kbs": kb_names,
                    "results": [],
                }, ensure_ascii=False)

            results = []
            for content, token_count, filename, kb_name_val, chunk_idx in rows:
                results.append({
                    "content": content[:1500],
                    "source": f"{kb_name_val} / {filename} (chunk {chunk_idx})",
                    "token_count": token_count,
                })

            return json.dumps({
                "found": True,
                "query": query,
                "result_count": len(results),
                "results": results,
            }, ensure_ascii=False)

        try:
            return await asyncio.to_thread(_search)
        except Exception as e:
            logger.error("Knowledge base search failed: %s", e, exc_info=True)
            return json.dumps({
                "found": False,
                "error": "知識庫查詢失敗",
                "results": [],
            }, ensure_ascii=False)
