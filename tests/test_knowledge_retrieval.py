"""Baseline acceptance tests for the M3 knowledge-retrieval tools."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine

import nanobot.agent.tools.insurance.knowledge_layer.search_kb as search_module
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


@pytest.mark.asyncio
async def test_competition_search_returns_a_source_reference():
    result = json.loads(
        await SearchCompetitionRulesTool(PROJECT_ROOT).execute(
            query="MDRT qualification requirements"
        )
    )

    assert result["results"]
    assert result["results"][0]["source"] == "mdrt_rules.md"


@pytest.mark.asyncio
async def test_best_practice_search_returns_matching_guidance():
    result = json.loads(
        await SearchBestPracticeTool(PROJECT_ROOT).execute(
            topic="improve a low lead conversion rate"
        )
    )

    assert result["matched_count"] > 0
    assert result["practices"]


@pytest.mark.asyncio
async def test_sales_script_search_returns_customer_facing_guidance():
    result = json.loads(
        await SearchSalesScriptsTool(PROJECT_ROOT).execute(
            scenario="handle an expensive product objection"
        )
    )

    assert result["matched_count"] > 0
    assert result["scripts"]


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
