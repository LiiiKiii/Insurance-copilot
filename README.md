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

Current development stage:

**A1 Platform Foundation (In Progress)**

The A0 repository foundation and initial knowledge corpus remain available. A1 is establishing the reusable runtime building blocks for the later agent system; basic local tests pass, but no real LLM API calls have been made.

### A1 Platform Foundation

The following foundation modules are currently implemented:

- **MessageBus**: `InboundMessage`, `OutboundMessage`, and asynchronous inbound/outbound message queues.
- **Provider Foundation**: the `LLMProvider` interface, `OpenAICompatProvider`, and an OpenRouter provider registry.
- **Runtime Configuration**: configuration schema, JSON loader/saver, and runtime path helpers.

### A0 Foundation Assets

The repository currently includes:

- the base project structure and development configuration;
- initial mock data and business configuration directories;
- a minimal Markdown knowledge base under `data/knowledge/`;
- four competition rule documents;
- MDRT and COT qualification rules;
- insurance sales scripts for common customer-facing scenarios.

### Knowledge Base Contents

| Category | Documents |
| -------- | --------- |
| Competition rules | `competition_starlight.md`, `competition_elite_challenge.md`, `competition_quarterly_sprint.md`, `competition_rookie_king.md` |
| Qualification rules | `mdrt_rules.md`, `cot_rules.md` |
| Sales guidance | `sales_scripts.md` |

These documents are source knowledge assets only. Knowledge search, relevance ranking, source citation, and retrieval evaluation will be introduced in subsequent development stages.


## Development Environment

- Python 3.11+
- Install the local project and its declared dependencies with:

  ```powershell
  python -m pip install -e .
  ```

- The default provider is OpenRouter and the default model is `openai/gpt-4o-mini`.
- Configure an OpenRouter key in PowerShell when needed for a future provider call:

  ```powershell
  $env:NANOBOT_PROVIDERS__OPENROUTER__API_KEY = "<your-openrouter-api-key>"
  ```

- `.env` files are not loaded automatically at this stage; use the nested `NANOBOT_` environment variable shown above for runtime configuration.
- Local secrets and runtime data must not be committed to version control
- Project dependencies will be introduced together with their corresponding modules

## Development

Agent Loop orchestration, insurance business rules, application APIs, database persistence, and frontend integration are not implemented in A1. Detailed setup, architecture, deployment, and usage instructions will be added as the corresponding system components are implemented.
