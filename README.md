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

**A0 — Repository Skeleton**

This stage establishes the shared repository structure, development configuration, project conventions, and the initial M3 knowledge corpus.

### A0 Deliverables

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

At the A0 stage, these documents are source knowledge assets only. Knowledge search, relevance ranking, source citation, and retrieval evaluation will be introduced in subsequent development stages.


## Development Environment

- Python 3.11+
- Environment-specific configuration is managed through `.env`
- Local secrets and runtime data must not be committed to version control
- Project dependencies will be introduced together with their corresponding modules

## Development

Detailed setup, architecture, API, deployment, and usage instructions will be added as the corresponding system components are implemented.