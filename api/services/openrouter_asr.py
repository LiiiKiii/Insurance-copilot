"""OpenRouter speech-to-text client used by chat audio input."""
from __future__ import annotations

import base64
import os
from typing import Any

import httpx


class OpenRouterAsrError(RuntimeError):
    pass


class OpenRouterAsrMissingKeyError(OpenRouterAsrError):
    pass


class OpenRouterAsrTimeoutError(OpenRouterAsrError):
    pass


_DEFAULT_BASE_URL = "https://openrouter.ai/api"
_DEFAULT_MODEL = "qwen/qwen3-asr-0.6b"
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0)
_MIME_TO_FORMAT = {
    "audio/webm": "webm",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
    "audio/aac": "aac",
}


def _format_from_mime(mime: str) -> str:
    try:
        return _MIME_TO_FORMAT[mime.lower()]
    except KeyError as exc:
        raise OpenRouterAsrError(
            f"unsupported audio mime for OpenRouter STT: {mime!r}"
        ) from exc


async def transcribe(
    audio: bytes,
    *,
    mime: str = "audio/webm",
    language_code: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise OpenRouterAsrMissingKeyError(
            "OPENROUTER_API_KEY env var is not set; cannot call OpenRouter STT."
        )
    base_url = os.environ.get("OPENROUTER_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    # OPENROUTER_BASE_URL is also used by embeddings and may already include /v1.
    endpoint_base = base_url[:-3] if base_url.endswith("/v1") else base_url
    model = model_id or os.environ.get("OPENROUTER_ASR_MODEL") or _DEFAULT_MODEL
    body: dict[str, Any] = {
        "model": model,
        "input_audio": {
            "data": base64.b64encode(audio).decode("ascii"),
            "format": _format_from_mime(mime),
        },
    }
    if language_code is not None:
        body["language"] = language_code
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{endpoint_base}/v1/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise OpenRouterAsrTimeoutError(
            "OpenRouter STT timed out; try a shorter recording."
        ) from exc
    except httpx.RequestError as exc:
        raise OpenRouterAsrError(
            f"OpenRouter STT request failed: {type(exc).__name__}"
        ) from exc
    if response.status_code >= 400:
        raise OpenRouterAsrError(
            f"OpenRouter STT failed: {response.status_code} {response.text[:300]}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise OpenRouterAsrError("OpenRouter STT returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise OpenRouterAsrError("OpenRouter STT returned an unexpected response shape.")
    payload.setdefault("text", "")
    return payload
