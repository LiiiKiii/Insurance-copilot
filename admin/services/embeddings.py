"""Validated, batched OpenRouter embedding client for knowledge ingestion."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Sequence

import httpx

DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
DEFAULT_EMBEDDING_BATCH_SIZE = 32
_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0)


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be generated or validated."""


class EmbeddingMissingKeyError(EmbeddingError):
    """Raised when OPENROUTER_API_KEY is not configured."""


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    dimensions: int
    batch_size: int
    endpoint: str


@dataclass(frozen=True)
class EmbeddingBatch:
    model: str
    dimensions: int
    vectors: list[list[float]]


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise EmbeddingError(f"{name} must be an integer") from exc
    if value <= 0:
        raise EmbeddingError(f"{name} must be greater than zero")
    return value


def load_embedding_config() -> EmbeddingConfig:
    model = os.environ.get("OPENROUTER_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
    dimensions = _positive_int_env("OPENROUTER_EMBEDDING_DIMENSIONS", DEFAULT_EMBEDDING_DIMENSIONS)
    batch_size = _positive_int_env("OPENROUTER_EMBEDDING_BATCH_SIZE", DEFAULT_EMBEDDING_BATCH_SIZE)
    base_url = os.environ.get("OPENROUTER_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    if base_url.endswith("/api"):
        base_url += "/v1"
    return EmbeddingConfig(model, dimensions, batch_size, f"{base_url}/embeddings")


async def embed_texts(
    texts: Sequence[str],
    *,
    config: EmbeddingConfig | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> EmbeddingBatch:
    cfg = config or load_embedding_config()
    if not texts:
        return EmbeddingBatch(cfg.model, cfg.dimensions, [])
    if any(not isinstance(value, str) or not value for value in texts):
        raise EmbeddingError("embedding inputs must be non-empty strings")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise EmbeddingMissingKeyError(
            "OPENROUTER_API_KEY is not configured; cannot generate document embeddings"
        )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    vectors: list[list[float]] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT, transport=transport) as client:
        for start in range(0, len(texts), cfg.batch_size):
            batch = list(texts[start:start + cfg.batch_size])
            try:
                response = await client.post(
                    cfg.endpoint,
                    headers=headers,
                    json={
                        "model": cfg.model,
                        "input": batch,
                        "dimensions": cfg.dimensions,
                        "encoding_format": "float",
                    },
                )
            except httpx.TimeoutException as exc:
                raise EmbeddingError("OpenRouter embedding request timed out") from exc
            except httpx.RequestError as exc:
                raise EmbeddingError(
                    f"OpenRouter embedding request failed: {type(exc).__name__}"
                ) from exc
            if response.status_code >= 400:
                raise EmbeddingError(
                    f"OpenRouter embedding request failed with HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
            try:
                data = response.json()["data"]
            except (ValueError, KeyError, TypeError) as exc:
                raise EmbeddingError("OpenRouter returned an invalid embedding response") from exc
            if not isinstance(data, list) or len(data) != len(batch):
                raise EmbeddingError(
                    "OpenRouter embedding count does not match the submitted chunk count"
                )

            ordered: list[list[float] | None] = [None] * len(batch)
            for item in data:
                if not isinstance(item, dict):
                    raise EmbeddingError("OpenRouter returned an invalid embedding item")
                index, raw_vector = item.get("index"), item.get("embedding")
                if not isinstance(index, int) or not 0 <= index < len(batch):
                    raise EmbeddingError("OpenRouter returned an invalid embedding index")
                if not isinstance(raw_vector, list) or len(raw_vector) != cfg.dimensions:
                    actual = len(raw_vector) if isinstance(raw_vector, list) else "invalid"
                    raise EmbeddingError(
                        f"embedding dimension mismatch: expected {cfg.dimensions}, received {actual}"
                    )
                try:
                    vector = [float(value) for value in raw_vector]
                except (TypeError, ValueError) as exc:
                    raise EmbeddingError("embedding contains a non-numeric value") from exc
                if not all(math.isfinite(value) for value in vector):
                    raise EmbeddingError("embedding contains a non-finite value")
                if ordered[index] is not None:
                    raise EmbeddingError("OpenRouter returned a duplicate embedding index")
                ordered[index] = vector
            if any(vector is None for vector in ordered):
                raise EmbeddingError("OpenRouter omitted one or more embeddings")
            vectors.extend(vector for vector in ordered if vector is not None)
    return EmbeddingBatch(cfg.model, cfg.dimensions, vectors)
