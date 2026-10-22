# M4 Candidate Prioritisation — First Implementation Batch

## Scope

This batch implements the data-source-independent M4 ranking core defined by
`prioritization-interface.md`. It is additive: the existing chase-plan and
improvement-advice tools, database schema, and frontend behavior are unchanged.

The implementation provides:

- deterministic eligibility, permission, and compliance filtering;
- required-field validation and explicit exclusion reasons;
- a transparent weighted priority score;
- stable ranking and Top-K selection;
- P0, P1, and P2 assignment;
- score-component breakdowns, actions, timing, and ranking reasons;
- an authenticated `POST /api/planning/prioritization` endpoint;
- Precision@K and NDCG@K evaluation utilities;
- an expected-contribution-only baseline; and
- automated tests for filtering, scoring, missing values, deterministic ties,
  Top-K output, endpoint authorization, and metric correctness.

The default score is:

```text
priority_score = 100 × (
    0.40 × expected_contribution_score
  + 0.25 × urgency
  + 0.20 × actionability
  + 0.15 × business_fit
)
```

`expected_contribution_score` is the expected contribution divided by the
verified open gap and capped at 1. The other components use a 0–1 scale.
Missing optional `business_fit` uses 0.5. Missing or invalid required values
exclude the candidate with a deterministic reason.

## Reproducible synthetic experiment

All monetary values in the tracked M4 fixture are denominated in USD, matching
the integrated general-insurance dataset.

Run:

```bash
./.venv/bin/python scripts/evaluate_prioritization.py
```

The tracked `m4-synthetic-v1` fixture produces:

| Ranking | Precision@3 | NDCG@3 |
| --- | ---: | ---: |
| Weighted M4 ranking | 1.000000 | 1.000000 |
| Expected-contribution baseline | 0.666667 | 0.319818 |

These values validate the implementation and experiment pipeline only. The
fixture is synthetic and intentionally constructed; the result is not evidence
of production effectiveness or improved sales outcomes. A reportable business
experiment still requires an agreed labelled candidate dataset and documented
independent relevance judgements.

## Integration boundary

The endpoint accepts candidate records that have already been prepared and
authorised. It does not query or change M2 data, recalculate M1 gaps, or replace
M3 evidence. The default Agent runtime tool registry is also unchanged in this
batch; enabling LLM access to `prioritize_followups` requires an explicit
integration decision because it changes the tools exposed to the model.
