"""Retrieval capability endpoint used by the chat interface."""
from fastapi import APIRouter

from admin.services.retrieval_capabilities import get_retrieval_capabilities

router = APIRouter()


@router.get("/api/retrieval/capabilities")
async def retrieval_capabilities() -> dict:
    capabilities = await get_retrieval_capabilities()
    return {"ok": True, **capabilities.to_dict()}
