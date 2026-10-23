"""Baseline acceptance tests for the M3 knowledge-retrieval tools."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import nanobot.agent.tools.insurance.knowledge_layer.best_practice as best_module
import nanobot.agent.tools.insurance.knowledge_layer.competition_rules as competition_module
import nanobot.agent.tools.insurance.knowledge_layer.sales_scripts as sales_module
import nanobot.agent.tools.insurance.knowledge_layer.search_kb as search_module
from nanobot.agent.tools.insurance.knowledge_layer._vector_search import VectorChunkHit
from nanobot.agent.tools.insurance.knowledge_layer.best_practice import (
    SearchBestPracticeTool,
)
from nanobot.agent.tools.insurance.knowledge_layer.competition_rules import (
    SearchCompetitionRulesTool,
)
from nanobot.agent.tools.insurance.knowledge_layer.sales_scripts import (
    SearchSalesScriptsTool,
)
from nanobot.agent.tools.insurance.knowledge_layer.search_kb import (
    SearchKnowledgeBaseTool,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HAN_RE = re.compile(r"[\u3400-\u9fff]")


def _assert_english_payload(values: list[str]) -> None:
    assert values
    assert not HAN_RE.search("\n".join(values))


@pytest.mark.asyncio
async def test_competition_search_returns_a_source_reference():
    chinese = json.loads(
        await SearchCompetitionRulesTool(PROJECT_ROOT).execute(
            query="MDRT資格條件"
        )
    )
    english = json.loads(
        await SearchCompetitionRulesTool(PROJECT_ROOT).execute(
            query="Million Dollar Round Table qualification"
        )
    )

    assert chinese["results"][0]["source"] == "AG25035.md"
    assert english["results"][0]["source"] == chinese["results"][0]["source"]
    _assert_english_payload([item["snippet"] for item in chinese["results"]])
    assert chinese["citations"][0]["source_path"] == english["citations"][0]["source_path"]


@pytest.mark.asyncio
async def test_best_practice_search_returns_matching_guidance():
    chinese = json.loads(
        await SearchBestPracticeTool(PROJECT_ROOT).execute(
            topic="件均保費偏低"
        )
    )
    english = json.loads(
        await SearchBestPracticeTool(PROJECT_ROOT).execute(
            topic="average premium per policy is low"
        )
    )

    assert chinese["practices"][0] == english["practices"][0]
    _assert_english_payload(chinese["practices"])
    assert chinese["citations"][0]["section_title"] == english["citations"][0]["section_title"]


@pytest.mark.asyncio
async def test_sales_script_search_returns_customer_facing_guidance():
    chinese = json.loads(
        await SearchSalesScriptsTool(PROJECT_ROOT).execute(
            scenario="客戶說太貴，需要處理異議"
        )
    )
    english = json.loads(
        await SearchSalesScriptsTool(PROJECT_ROOT).execute(
            scenario="the client says it is too expensive; handle the objection"
        )
    )

    assert chinese["scripts"][0] == english["scripts"][0]
    _assert_english_payload(chinese["scripts"])
    assert chinese["citations"][0]["section_title"] == english["citations"][0]["section_title"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chinese", "english", "expected_title"),
    [
        ("線索轉化率低", "low lead conversion rate", "How to improve low lead follow-up rate"),
        ("MDRT衝刺", "MDRT sprint", "MDRT sprint time management"),
        ("競賽最後30天", "last 30 days of the competition", "Sprint tactics for the last 30 days"),
        ("老客加保", "existing-client additional coverage", "Timing for old customers to add insurance"),
    ],
)
async def test_other_best_practice_aliases_share_the_expected_section(
    chinese,
    english,
    expected_title,
):
    chinese_result = json.loads(
        await SearchBestPracticeTool(PROJECT_ROOT).execute(topic=chinese)
    )
    english_result = json.loads(
        await SearchBestPracticeTool(PROJECT_ROOT).execute(topic=english)
    )

    assert chinese_result["practices"][0].startswith(expected_title)
    assert english_result["practices"][0] == chinese_result["practices"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chinese", "english", "expected_title"),
    [
        ("需求挖掘", "FABE needs analysis", "Scenario 2: Demand mining"),
        ("轉介紹", "referral", "Scenario 3: Extension and referral"),
        ("老客加保", "existing-client upsell", "Scenario 3: Extension and referral"),
        ("促成成交", "closing the sale", "Scene 4: Facilitating conversational skills"),
    ],
)
async def test_other_sales_script_aliases_share_the_expected_section(
    chinese,
    english,
    expected_title,
):
    chinese_result = json.loads(
        await SearchSalesScriptsTool(PROJECT_ROOT).execute(scenario=chinese)
    )
    english_result = json.loads(
        await SearchSalesScriptsTool(PROJECT_ROOT).execute(scenario=english)
    )

    assert chinese_result["scripts"][0].startswith(expected_title)
    assert english_result["scripts"][0] == chinese_result["scripts"][0]


def test_builtin_retrieval_markdown_is_english_and_preserves_section_contracts():
    files = [
        PROJECT_ROOT / "data/knowledge/sales_scripts.md",
        PROJECT_ROOT / "data/knowledge/best_practices.md",
        *sorted((PROJECT_ROOT / "data/knowledge").glob("competition_*.md")),
        PROJECT_ROOT / "data/knowledge/mdrt_rules.md",
        PROJECT_ROOT / "data/knowledge/cot_rules.md",
        *sorted((PROJECT_ROOT / "data/knowledge/competitions").glob("*.md")),
    ]

    assert len(files) == 16
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert not HAN_RE.search(content), path
        assert content.startswith("# "), path
    assert "\n## " in files[0].read_text(encoding="utf-8")
    assert "\n## " in files[1].read_text(encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "tool", "argument", "queries", "filename", "source_path", "section_title"),
    [
        (
            competition_module,
            SearchCompetitionRulesTool,
            "query",
            ("MDRT資格條件", "MDRT qualification"),
            "AG25035.md",
            "data/knowledge/competitions/AG25035.md",
            "AG25035 - MDRT Qualification Rules",
        ),
        (
            best_module,
            SearchBestPracticeTool,
            "topic",
            ("件均保費偏低", "average premium is low"),
            "best_practices.md",
            "data/knowledge/best_practices.md",
            "Improvement strategies for low average premium per case",
        ),
        (
            sales_module,
            SearchSalesScriptsTool,
            "scenario",
            ("客戶說太貴", "client says it is too expensive"),
            "sales_scripts.md",
            "data/knowledge/sales_scripts.md",
            'Scenario 1: Objection handling when the customer says "I\'ll think about it"',
        ),
    ],
)
async def test_bilingual_vector_queries_resolve_to_the_same_english_source(
    monkeypatch,
    module,
    tool,
    argument,
    queries,
    filename,
    source_path,
    section_title,
):
    content = f"# {section_title}\n\nEnglish-only retrieval guidance."
    calls = []

    async def fake_vector_search(query, **kwargs):
        calls.append((query, kwargs))
        return [
            VectorChunkHit(
                content=content,
                token_count=8,
                filename=filename,
                knowledge_base="Built-in test knowledge",
                chunk_index=0,
                chunk_id="chunk-1",
                metadata={
                    "source_path": source_path,
                    "section_title": section_title,
                    "heading_path": [section_title],
                },
                distance=0.1,
                embedding_model="test/multilingual",
            )
        ]

    monkeypatch.setattr(module, "search_builtin_vectors", fake_vector_search)
    outputs = []
    for query in queries:
        outputs.append(
            json.loads(
                await tool(PROJECT_ROOT).execute(
                    **{argument: query, "search_mode": "vector"}
                )
            )
        )

    assert [call[0] for call in calls] == list(queries)
    assert outputs[0]["citations"][0]["source_path"] == source_path
    assert outputs[1]["citations"][0]["source_path"] == source_path
    assert outputs[0]["citations"][0]["section_title"] == section_title
    assert outputs[1]["citations"][0]["section_title"] == section_title
    assert not HAN_RE.search(outputs[0]["citations"][0]["content_excerpt"])


@pytest.mark.asyncio
async def test_database_search_returns_indexed_content(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'knowledge.db'}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE knowledge_bases ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, "
            "document_count INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE documents ("
            "id TEXT PRIMARY KEY, knowledge_base_id TEXT NOT NULL, filename TEXT NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE document_chunks ("
            "id TEXT PRIMARY KEY, document_id TEXT NOT NULL, knowledge_base_id TEXT NOT NULL, "
            "chunk_index INTEGER NOT NULL, content TEXT NOT NULL, token_count INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE VIRTUAL TABLE knowledge_fts USING fts5(doc_id, title, content)"
        )
        connection.exec_driver_sql(
            "INSERT INTO knowledge_bases VALUES ('kb-1', 'Sales Handbook', 'active', 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO documents VALUES ('doc-1', 'kb-1', 'handbook.pdf')"
        )
        connection.exec_driver_sql(
            "INSERT INTO document_chunks VALUES "
            "('chunk-1', 'doc-1', 'kb-1', 0, "
            "'Ask discovery questions before recommending protection.', 8)"
        )
        connection.exec_driver_sql(
            "INSERT INTO knowledge_fts(rowid, doc_id, title, content) VALUES "
            "(1, 'doc-1', 'Discovery', "
            "'Ask discovery questions before recommending protection.')"
        )

    monkeypatch.setattr(search_module, "sync_engine", engine)
    monkeypatch.setattr(search_module, "_is_sqlite", True)

    result = json.loads(
        await SearchKnowledgeBaseTool(PROJECT_ROOT).execute(
            query="discovery protection", kb_name="Sales Handbook", top_k=3
        )
    )

    assert result["found"] is True
    assert result["result_count"] == 1
    assert "Sales Handbook / handbook.pdf" in result["results"][0]["source"]
    engine.dispose()


@pytest.mark.asyncio
async def test_database_search_rejects_an_empty_query():
    result = json.loads(await SearchKnowledgeBaseTool(PROJECT_ROOT).execute(query=""))

    assert result == {"error": "Query is required"}
