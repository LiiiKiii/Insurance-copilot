# Business Optimisation and Recommendation Module

## Purpose

M4 owns the business optimisation and recommendation module. The module will convert verified performance gaps, diagnostic evidence, and eligible customer opportunities into a ranked follow-up list and a practical action plan.

This A0 deliverable documents the boundary between the existing planning baseline and the optimisation work proposed for the coursework. It does not introduce a new optimisation algorithm.

## Existing Prototype Baseline

The existing prototype used as a reference contains two planning tools. Their source code will be introduced in a later development round rather than copied into A0.

### Chase Plan Generation

The existing `GenerateChasePlanTool`:

- selects a specified competition or the most urgent competition with an open gap;
- uses the performance gap after pending-premium deduction;
- divides the remaining gap evenly across the available weeks;
- calculates a daily production requirement;
- returns weekly targets and template-based P0, P1, and P2 actions;
- reads configurable action text from `data/config/action_templates.json`.

This tool provides a deterministic catch-up schedule, but it does not rank individual customers or policies.

### Improvement Advice Generation

The existing `GenerateImprovementAdviceTool`:

- reads performance-attribution results;
- identifies metrics that are below their peer benchmark;
- selects the first `top_n` weaknesses;
- assigns P0 to the first weakness, P1 to the next two, and P2 to the remaining weaknesses;
- converts each weakness into template-based improvement advice.

This tool prioritises diagnostic weaknesses by their existing order. It does not calculate a customer-level priority score or solve a constrained optimisation problem.

## Current Functional Boundary

The existing planning baseline can answer:

- how much production is required each week or day;
- which diagnosed weaknesses should receive attention first;
- which generic actions correspond to each priority level.

The existing planning baseline cannot yet answer:

- which customer or pending policy should be followed up first;
- how much each candidate contributes to closing the performance gap;
- why one customer ranks above another using explicit score components;
- which Top-K recommendations best satisfy business constraints;
- whether the ranking performs better than a simple baseline.

The P0, P1, and P2 labels in the existing prototype are rule and template labels. They must not be presented as the result of a new optimisation algorithm.

## Planned Optimisation Workflow

The coursework implementation will contain five stages.

### 1. Input Preparation

Planned inputs include:

- the verified performance gap and remaining deadline;
- candidate customer and pending-policy records;
- performance diagnosis and attribution results;
- relevant business, permission, and compliance constraints.

M4 will consume these inputs through agreed interfaces. M4 will not redefine the authoritative gap, feasibility, or data-access calculations owned by other modules.

### 2. Candidate Filtering

The module will remove records that are not eligible or actionable. Filtering will account for record status, user scope, required data, and applicable business constraints.

### 3. Priority Scoring and Ranking

The module will implement a transparent and configurable priority-score model. Candidate opportunities will be ranked using documented score components such as expected contribution to the open gap, urgency, customer or policy attributes, and actionability.

Weights, normalisation rules, missing-value behaviour, and tie-breaking rules will be documented and tested. The first version will use an explainable deterministic score rather than a trained conversion-probability model.

### 4. Recommendation and Action Planning

The ranking stage will select the Top-K opportunities and convert them into:

- a ranked customer or policy follow-up list;
- P0, P1, and P2 action priorities;
- a daily or weekly action plan;
- a reason and supporting score components for each recommendation.

### 5. Evaluation

The proposed ranking will be compared with a simple expected-premium baseline. Evaluation will use:

- `Precision@K` to measure how many relevant opportunities appear in the first K recommendations;
- `NDCG@K` to measure whether the most relevant opportunities appear near the top of the ranking.

The evaluation dataset, relevance labels, value of K, and baseline definition will be fixed before reporting results.

## Planned Interfaces

The future optimisation service is expected to accept an agent identifier, a performance objective, candidate records, and configurable constraints. Its structured output should include:

- candidate identifier and rank;
- total priority score;
- score-component breakdown;
- assigned priority level;
- recommended action and timing;
- evidence or reason for the recommendation.

The proposed implementation location is:

```text
nanobot/agent/tools/insurance/planning_layer/prioritization.py
```

The final path and schema will be agreed during the API and integration round.

## Module Ownership Boundary

- M1 owns authoritative business-rule reasoning, feasibility assessment, API conventions, and system integration.
- M2 owns the business data model, prepared records, KPI calculations, and performance diagnosis.
- M3 owns knowledge retrieval, rule matching, source metadata, and retrieval evaluation.
- M4 owns candidate prioritisation, Top-K recommendation, action-plan construction, and ranking evaluation.
- M5 owns presentation of recommendations and the associated user workflow.

## A0 Scope

For A0, M4 delivers this module-boundary document only. The following items are intentionally deferred:

- copying the existing planning tools into the new repository;
- implementing the priority-score model;
- adding customer-ranking APIs or database models;
- generating Top-K recommendations;
- changing the web interface;
- reporting Precision@K or NDCG@K results.

These items will be introduced incrementally in later rounds after the required data, reasoning, and integration foundations are available.
