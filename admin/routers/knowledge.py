"""Knowledge base and document management router."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from admin.dependencies import DB, RoleAdmin, RoleManager, RoleAny
from admin.models.knowledge import Document, DocumentChunk, KnowledgeBase
from admin.services.pdf import get_document_processor

router = APIRouter()
logger = logging.getLogger(__name__)


async def _run_document_processor(doc_id: str) -> None:
    """Fire-and-forget wrapper so processing detaches from the request lifecycle.

    `process_document` 本身是 async（内部使用 async DB session），必须 await；
    但首次构造 DocumentProcessor 会同步加载 RapidOCR ONNX 模型，CPU 密集，
    所以把构造放线程池，避免阻塞事件循环导致 upload 响应卡住。
    """
    try:
        processor = await run_in_threadpool(get_document_processor)
        await processor.process_document(doc_id)
    except Exception:  # noqa: BLE001
        logger.exception("Background document processing failed: doc_id=%s", doc_id)


class KBRequest(BaseModel):
    name: str
    description: str = ""
    kb_type: str = "document"
    embedding_model_id: str | None = None
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k: int = 5


class DocumentRequest(BaseModel):
    filename: str
    file_type: str
    file_size: int = 0


def _kb_dict(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id, "tenant_id": kb.tenant_id, "name": kb.name,
        "description": kb.description, "kb_type": kb.kb_type,
        "embedding_model_id": kb.embedding_model_id,
        "chunk_size": kb.chunk_size, "chunk_overlap": kb.chunk_overlap, "top_k": kb.top_k,
        "status": kb.status, "document_count": kb.document_count, "chunk_count": kb.chunk_count,
        "created_at": kb.created_at.isoformat() if kb.created_at else None,
    }


@router.get("/")
async def list_kbs(
    current_user: RoleAny, db: DB,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    q = select(KnowledgeBase)
    if not current_user.is_superadmin:
        q = q.where(KnowledgeBase.tenant_id == current_user.tenant_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    return {"ok": True, "data": [_kb_dict(kb) for kb in result.scalars().all()],
            "meta": {"page": page, "page_size": page_size, "total": total}}


@router.post("/")
async def create_kb(body: KBRequest, current_user: RoleManager, db: DB):
    # Quota check
    from admin.models.tenant import Tenant
    tenant = (await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))).scalar_one_or_none()
    if tenant:
        kb_count = (await db.execute(
            select(func.count()).select_from(KnowledgeBase)
            .where(KnowledgeBase.tenant_id == current_user.tenant_id)
        )).scalar()
        if kb_count >= tenant.max_knowledge_bases:
            raise HTTPException(429, detail={"ok": False, "error": {"code": "QUOTA_EXCEEDED", "message": f"Knowledge base limit reached ({tenant.max_knowledge_bases})"}})

    kb = KnowledgeBase(tenant_id=current_user.tenant_id, **body.model_dump())
    db.add(kb)
    await db.commit()
    return {"ok": True, "data": _kb_dict(kb)}


@router.get("/{kb_id}")
async def get_kb(kb_id: str, current_user: RoleAny, db: DB):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(404, detail={"ok": False, "error": {"code": "NOT_FOUND", "message": "Knowledge base not found"}})
    if not current_user.is_superadmin and kb.tenant_id != current_user.tenant_id:
        raise HTTPException(403, detail={"ok": False, "error": {"code": "FORBIDDEN", "message": "Access denied"}})
    return {"ok": True, "data": _kb_dict(kb)}


@router.put("/{kb_id}")
async def update_kb(kb_id: str, body: KBRequest, current_user: RoleManager, db: DB):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(404, detail={"ok": False, "error": {"code": "NOT_FOUND", "message": "Knowledge base not found"}})
    if not current_user.is_superadmin and kb.tenant_id != current_user.tenant_id:
        raise HTTPException(403, detail={"ok": False, "error": {"code": "FORBIDDEN", "message": "Access denied"}})
    for k, v in body.model_dump().items():
        setattr(kb, k, v)
    await db.commit()
    return {"ok": True, "data": _kb_dict(kb)}


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str, current_user: RoleAdmin, db: DB):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(404, detail={"ok": False, "error": {"code": "NOT_FOUND", "message": "Knowledge base not found"}})
    if not current_user.is_superadmin and kb.tenant_id != current_user.tenant_id:
        raise HTTPException(403, detail={"ok": False, "error": {"code": "FORBIDDEN", "message": "Access denied"}})
    await db.delete(kb)
    await db.commit()
    return {"ok": True, "data": {"message": "Knowledge base deleted"}}


@router.get("/{kb_id}/documents")
async def list_documents(kb_id: str, current_user: RoleAny, db: DB,
                         page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    q = select(Document).where(Document.knowledge_base_id == kb_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    docs = result.scalars().all()
    return {
        "ok": True,
        "data": [{"id": d.id, "filename": d.filename, "file_type": d.file_type,
                  "file_size": d.file_size, "status": d.status,
                  "chunk_count": d.chunk_count, "error_message": d.error_message,
                  "created_at": d.created_at.isoformat() if d.created_at else None} for d in docs],
        "meta": {"page": page, "page_size": page_size, "total": total},
    }


@router.post("/{kb_id}/documents")
async def add_document(kb_id: str, body: DocumentRequest, current_user: RoleManager, db: DB):
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(404, detail={"ok": False, "error": {"code": "NOT_FOUND", "message": "Knowledge base not found"}})
    doc = Document(
        knowledge_base_id=kb_id,
        tenant_id=current_user.tenant_id,
        filename=body.filename,
        file_type=body.file_type,
        file_size=body.file_size,
        status="pending",
    )
    db.add(doc)
    kb.document_count = (kb.document_count or 0) + 1
    await db.commit()
    return {"ok": True, "data": {"id": doc.id, "filename": doc.filename, "status": doc.status}}


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str, current_user: RoleAdmin, db: DB):
    result = await db.execute(select(Document).where(Document.id == doc_id, Document.knowledge_base_id == kb_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, detail={"ok": False, "error": {"code": "NOT_FOUND", "message": "Document not found"}})
    # Update KB count
    result2 = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result2.scalar_one_or_none()
    if kb:
        kb.document_count = max((kb.document_count or 1) - 1, 0)
    # 先删除关联的 chunks，避免外键约束冲突
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))
    await db.delete(doc)
    await db.commit()
    return {"ok": True, "data": {"message": "Document deleted"}}


@router.get("/{kb_id}/documents/{doc_id}/chunks")
async def list_chunks(kb_id: str, doc_id: str, current_user: RoleAny, db: DB,
                      page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50)):
    q = select(DocumentChunk).where(DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_index)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    chunks = result.scalars().all()
    return {
        "ok": True,
        "data": [{"id": c.id, "chunk_index": c.chunk_index, "content": c.content,
                  "token_count": c.token_count, "metadata": c.chunk_metadata} for c in chunks],
        "meta": {"page": page, "page_size": page_size, "total": total},
    }


@router.post("/{kb_id}/documents/upload")
async def upload_document(
    kb_id: str,
    current_user: RoleManager,
    db: DB,
    file: UploadFile = File(...),
):
    """Upload a PDF, persist it, and schedule asynchronous OCR ingestion.

    Returns immediately with ``status='pending'``. The actual extraction
    and indexing happen in a BackgroundTask via DocumentProcessor.
    """
    # Verify KB exists & tenant access
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(
            404,
            detail={"ok": False, "error": {"code": "NOT_FOUND", "message": "Knowledge base not found"}},
        )
    if not current_user.is_superadmin and kb.tenant_id != current_user.tenant_id:
        raise HTTPException(
            403,
            detail={"ok": False, "error": {"code": "FORBIDDEN", "message": "Access denied"}},
        )

    # Save file to disk
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(_project_root, "data", "kb", kb_id)
    os.makedirs(upload_dir, exist_ok=True)
    filename = file.filename or f"upload_{uuid.uuid4().hex[:8]}"
    file_path = os.path.join(upload_dir, filename)
    content_bytes = await file.read()
    with open(file_path, "wb") as f:
        f.write(content_bytes)

    # Detect file type
    ext = os.path.splitext(filename)[1].lower()
    file_type = ext.lstrip(".") or "txt"

    # Insert document with status=pending. DO NOT increment kb.document_count
    # here; the processor does that on successful indexing.
    doc = Document(
        id=str(uuid.uuid4()),
        knowledge_base_id=kb_id,
        tenant_id=kb.tenant_id,
        filename=filename,
        file_type=file_type,
        file_size=len(content_bytes),
        status="pending",
    )
    db.add(doc)
    await db.commit()

    # Detach processing from the request so the HTTP response returns immediately.
    # FastAPI BackgroundTasks keep the connection open until the task finishes,
    # which makes heavy OCR block the upload modal; asyncio.create_task doesn't.
    asyncio.create_task(_run_document_processor(doc.id))

    return {
        "ok": True,
        "data": {
            "id": doc.id,
            "filename": filename,
            "file_type": file_type,
            "file_size": len(content_bytes),
            "status": "pending",
        },
    }
