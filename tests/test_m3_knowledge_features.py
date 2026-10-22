"""Offline regression tests for the M3 retrieval, citation and speech additions."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from admin.services.embeddings import EmbeddingConfig, EmbeddingError, embed_texts
from nanobot.retrieval import apply_retrieval_mode
from nanobot.retrieval_citations import (
    build_keyword_citation,
    build_vector_citation,
    extract_retrieval_citations,
    strip_retrieval_citations,
)


@pytest.mark.asyncio
async def test_embeddings_batch_and_restore_response_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    seen: list[list[str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body["input"])
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [float(index), 1.0, 2.0]}
                    for index in reversed(range(len(body["input"])))
                ]
            },
        )

    result = await embed_texts(
        ["a", "b", "c"],
        config=EmbeddingConfig(
            model="test/model",
            dimensions=3,
            batch_size=2,
            endpoint="https://openrouter.test/api/v1/embeddings",
        ),
        transport=httpx.MockTransport(handler),
    )
    assert seen == [["a", "b"], ["c"]]
    assert result.vectors == [
        [0.0, 1.0, 2.0],
        [1.0, 1.0, 2.0],
        [0.0, 1.0, 2.0],
    ]


@pytest.mark.asyncio
async def test_embeddings_reject_wrong_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0]}]}
        )

    with pytest.raises(EmbeddingError, match="dimension mismatch"):
        await embed_texts(
            ["chunk"],
            config=EmbeddingConfig(
                model="test/model",
                dimensions=3,
                batch_size=2,
                endpoint="https://openrouter.test/api/v1/embeddings",
            ),
            transport=httpx.MockTransport(handler),
        )


def test_retrieval_mode_is_forced_only_on_knowledge_tools() -> None:
    search = SimpleNamespace(
        name="search_knowledge_base",
        arguments={"query": "policy", "search_mode": "keyword"},
    )
    other = SimpleNamespace(name="calculate_run_rate", arguments={"current": 1})
    apply_retrieval_mode([search, other], "vector")
    assert search.arguments["search_mode"] == "vector"
    assert "search_mode" not in other.arguments


def test_citations_remain_structured_and_are_hidden_from_model_context() -> None:
    keyword = build_keyword_citation(
        tool="search_knowledge_base",
        file_name="rules.md",
        content="The sales policy applies to every sales agent.",
        query_terms=["sales", "policy", "missing"],
        chunk_index=2,
    )
    vector = build_vector_citation(
        tool="search_best_practice",
        file_name="best_practices.md",
        content="Improve average case size.",
        distance=0.18,
        rank=1,
    )
    serialized = json.dumps(
        {"results": [{"content": "context"}], "citations": [keyword, vector]}
    )
    assert extract_retrieval_citations("search_knowledge_base", serialized) == [
        keyword,
        vector,
    ]
    assert json.loads(
        strip_retrieval_citations("search_knowledge_base", serialized)
    ) == {"results": [{"content": "context"}]}


def test_audio_route_transcribes_and_strips_model_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.routers.audio import router

    fake = AsyncMock(
        return_value={"text": "(beatbox) hello (music) world", "language_code": "en"}
    )
    monkeypatch.setattr("api.routers.audio.openrouter_asr.transcribe", fake)
    application = FastAPI()
    application.include_router(router)
    response = TestClient(application).post(
        "/api/audio/transcribe",
        files={"file": ("clip.webm", b"audio", "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "text": "hello  world",
        "language_code": "en",
    }
