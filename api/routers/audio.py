"""Speech-to-text endpoint; uploaded bytes are never persisted."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.services import openrouter_asr

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audio", tags=["audio"])
_AUDIO_TAG_RE = re.compile(r"[（(][^)）]{1,30}[)）]")
_MAX_BYTES = 25 * 1024 * 1024
_ALLOWED_MIMES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/ogg",
}


def _strip_audio_tags(text: str) -> str:
    return _AUDIO_TAG_RE.sub("", text).strip()


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict:
    mime = (file.content_type or "").split(";", 1)[0].strip().lower()
    if mime not in _ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail={
                "ok": False,
                "error": {
                    "code": "UNSUPPORTED_MEDIA",
                    "message": f"audio mime {mime!r} not allowed",
                },
            },
        )
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": {"code": "EMPTY_AUDIO", "message": "audio file is empty"},
            },
        )
    if len(audio_bytes) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "ok": False,
                "error": {"code": "TOO_LARGE", "message": "audio exceeds 25 MB"},
            },
        )
    try:
        result = await openrouter_asr.transcribe(audio_bytes, mime=mime)
    except openrouter_asr.OpenRouterAsrMissingKeyError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": {"code": "STT_UNCONFIGURED", "message": str(exc)},
            },
        ) from exc
    except openrouter_asr.OpenRouterAsrTimeoutError as exc:
        logger.warning("OpenRouter STT timeout: %s", exc)
        raise HTTPException(
            status_code=504,
            detail={
                "ok": False,
                "error": {"code": "STT_TIMEOUT", "message": str(exc)},
            },
        ) from exc
    except openrouter_asr.OpenRouterAsrError as exc:
        logger.warning("OpenRouter STT failure: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": {"code": "STT_FAILED", "message": str(exc)},
            },
        ) from exc
    raw_text = result.get("text", "")
    return {
        "ok": True,
        "data": {
            "text": _strip_audio_tags(raw_text if isinstance(raw_text, str) else ""),
            "language_code": result.get("language_code", ""),
        },
    }
