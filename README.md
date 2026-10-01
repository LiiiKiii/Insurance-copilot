# Insurance Performance Intelligence Copilot

A Hybrid Intelligent Reasoning System for insurance agents' performance gap diagnosis and action planning.

## Overview

Insurance agents operate in a target-driven environment and need to monitor performance targets, competition progress, pending policies, and customer follow-up opportunities.

This project aims to build an intelligent decision-support system that helps insurance agents and supervisors:

- identify performance gaps;
- understand relevant contributing factors;
- assess whether remaining targets are achievable;
- retrieve relevant business knowledge and guidance;
- prioritise appropriate follow-up actions.

The system will progressively integrate data-driven diagnosis, deterministic business-rule reasoning, knowledge retrieval, optimisation-based planning, and natural-language interaction.

## Project Status

Current migration stage:

**A1 — Platform and Data Layer**

This stage includes the implemented platform foundation and the M3 knowledge storage model definitions and database-backed keyword search tool implementation. The A0 repository foundation and initial knowledge corpus remain available.

The platform foundation has been tested offline with a Mock Provider; no real OpenRouter API call has been made. The M3 modules have separate database and tool infrastructure prerequisites, described below. Platform foundation completion does not imply that knowledge retrieval is integrated into the agent runtime.

### A1 Platform Foundation

The following foundation modules are currently implemented:

- **MessageBus**: `InboundMessage`, `OutboundMessage`, and asynchronous inbound/outbound message queues.
- **Provider Foundation**: the `LLMProvider` interface, `OpenAICompatProvider`, and an OpenRouter provider registry.
- **Runtime Configuration**: configuration schema, JSON loader/saver, and runtime path helpers.
- **Minimal Agent Runtime**: `ContextBuilder` assembles the system prompt, runtime context, and current user message; `AgentLoop` connects MessageBus, ContextBuilder, and LLMProvider for minimal text interaction with basic error handling, stopping, and task cancellation.

### A0 Deliverables Retained

- the base project structure, development configuration, and project conventions;
- initial mock data and business configuration directories;
- a minimal Markdown knowledge corpus under `data/knowledge/`;
- four competition rule documents, MDRT and COT qualification rules, and insurance sales scripts.

| Category | Documents |
| -------- | --------- |
| Competition rules | `competition_starlight.md`, `competition_elite_challenge.md`, `competition_quarterly_sprint.md`, `competition_rookie_king.md` |
| Qualification rules | `mdrt_rules.md`, `cot_rules.md` |
| Sales guidance | `sales_scripts.md` |

These Markdown documents remain source knowledge assets. Adding the A1 model and search modules does not automatically import them into the database.

### A1 M3 Deliverables

| File | Responsibility |
| ---- | -------------- |
| `admin/models/knowledge.py` | SQLAlchemy model definitions for knowledge bases, documents, and document chunks |
| `nanobot/agent/tools/insurance/knowledge_layer/search_kb.py` | Keyword lookup over existing database document chunks through `SearchKnowledgeBaseTool` |

Shared utilities and the tool base class are required by these modules and should be supplied by the corresponding platform contribution, or included as shared foundations in this stage.

## Knowledge Storage Models

The M3 storage model defines three related tables:

| Table | Purpose | Selected Fields |
| ----- | ------- | --------------- |
| `knowledge_bases` | Knowledge base configuration and counters | `id`, `tenant_id`, `name`, `kb_type`, `chunk_size`, `chunk_overlap`, `top_k`, `status` |
| `documents` | Document metadata and processing state | `id`, `knowledge_base_id`, `tenant_id`, `filename`, `file_type`, `file_size`, `status`, `chunk_count` |
| `document_chunks` | Stored document content blocks | `id`, `document_id`, `knowledge_base_id`, `chunk_index`, `content`, `token_count`, `chunk_metadata` |

Knowledge bases and documents reference the shared `tenants` table. Model definitions must be loaded and their tables created by the platform database initialization before they can be used.

The `embedding_model_id` field is configuration metadata; this stage does not implement embeddings or vector search.

## Basic Database Knowledge Search

`SearchKnowledgeBaseTool` exposes the tool name `search_knowledge_base` and accepts:

| Parameter | Purpose |
| --------- | ------- |
| `query` | Search text; required |
| `kb_name` | Optional knowledge base name filter |
| `top_k` | Maximum number of returned results; default `5` |

The implementation attempts SQLite FTS5 lookup when available and falls back to SQL `LIKE` matching. Returned matches include a content excerpt, token count, and source metadata identifying the knowledge base, document filename, and chunk index.

The `top_k` parameter caps the result count. The implementation does not provide semantic relevance ranking or measured retrieval quality.

### Integration Status

The A1 M3 deliverable is model and search module code. Execution requires:

- shared database infrastructure providing `Base`, `sync_engine`, and `_is_sqlite` from `admin.db`;
- the shared timestamp utility `now_beijing` from `admin.utils`;
- the shared tool interface `Tool` from `nanobot.agent.tools.base`;
- the tenant model and initialized knowledge tables;
- document and chunk records already stored in the database.

The FTS5 path additionally requires a populated `knowledge_fts` table whose row IDs match the corresponding document chunk row IDs. The search tool does not create or populate that index.

The M3 modules alone do not establish a knowledge service, an ingestion pipeline, or a retrieval-enabled agent flow. The existing minimal AgentLoop does not yet execute this knowledge search tool. Returning source metadata does not establish answer-level citation generation or citation correctness.

## Subsequent Development

Later stages will introduce and document the corresponding implementations for:

- knowledge base management endpoints and document ingestion;
- automatic document extraction, chunking, and indexing;
- specialised competition rule, sales script, and best-practice tools;
- knowledge tool registration and integration with the agent runtime, reasoning, and planning;
- answer-level source citations and explainable responses;
- relevance-labelled evaluation data and retrieval metrics;
- knowledge management UI and end-to-end validation.

Vector retrieval remains a possible extension and is not implemented by the A1 keyword search module.

## Development Environment

- Python 3.11+

Install the local project and its declared dependencies with:

```powershell
python -m pip install -e .
```

### Agent Runtime Configuration

The default provider is OpenRouter and the default model is `openai/gpt-4o-mini`.

Configure an OpenRouter key in PowerShell when needed for a future provider call:

```powershell
$env:NANOBOT_PROVIDERS__OPENROUTER__API_KEY = "<your-openrouter-api-key>"
```

The minimal agent runtime does not automatically load `.env` files at this stage. Use the nested `NANOBOT_` environment variable shown above for runtime configuration.

`save_config()` may store API keys as plaintext in a local JSON configuration file. Prefer environment variables, protect local files containing keys, and never commit them to Git.

### Knowledge Data Layer Dependencies

The M3 model and search modules require SQLAlchemy 2.x. Their shared SQLite database infrastructure also requires `aiosqlite` and the dependencies used by the integrated `admin.db` implementation, including `python-dotenv` when using its `.env` loader.

Database configuration is separate from the minimal agent runtime configuration. The presence of a database `.env` loader does not mean that the agent runtime automatically loads `.env` files.

Required dependencies and package configuration should be integrated with the shared A1 platform setup. Installing the project's currently declared dependencies does not by itself establish the database tables or import the Markdown corpus. Project dependencies will be introduced together with their corresponding modules; the complete project's dependency list includes later-stage modules and should not be adopted wholesale.

Local secrets, runtime configuration containing keys, and runtime database files must not be committed to version control.

## Development

The Minimal AgentLoop is implemented in A1. Tool execution, session persistence, Memory, Skills, MCP, Subagents, business reasoning, advanced agent orchestration, application APIs, database persistence integrated with the agent runtime, and frontend integration remain outside the current minimal runtime scope.

The M3 contribution adds knowledge model and search module code; database initialization, document ingestion, and tool execution through AgentLoop must be integrated and verified before describing knowledge retrieval as an end-to-end feature.

Detailed setup, architecture, application startup, API, ingestion, deployment, and usage instructions will be added as the corresponding system components are integrated and verified.