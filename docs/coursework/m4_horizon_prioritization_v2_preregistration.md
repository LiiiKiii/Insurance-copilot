# M4 Horizon-Aligned Prioritisation v2 — Pre-registration

**Status:** frozen before any v4 annotation or consensus result is available.  
**Input contract:** M1 Horizon-Aligned Gap v1 and M2 dataset
`m2-coursework-candidates-v4`.  
**Owner:** M4 — Business Optimisation and Recommendation.

## Purpose and independence

This document fixes the v4 ranking and evaluation decisions before the three
independent annotators submit rankings. No v4 label, consensus order, metric,
or sensitivity result has been used to choose the formula, weights, candidate
set, tie-breaks, or K values. Future changes to these decisions require a new
version and must not be presented as this pre-registered experiment.

The existing v1 annual-gap route remains available for backwards
compatibility. The v2 path is selected only by a complete horizon objective;
it never silently falls back to `annual_open_gap` or legacy `open_gap`.

## Formal candidate set

A candidate enters the v2 ranking only when all of the following hold:

- the existing eligibility, tenant/agent permission, and compliance gates pass;
- `horizon_ranking_eligible` and `within_planning_horizon` are true;
- candidate metric and currency match the objective;
- a supported `expected_realization_date` falls inside the inclusive planning
  horizon; and
- expected contribution and the three remaining score inputs are valid.

Future, before-horizon, unknown-date, gate-excluded, or mismatched candidates
remain auditable exclusions. They are not used to fill a requested Top-K.

## Fixed score

For a valid objective with `horizon_open_gap > 0`:

```text
contribution_coverage = min(expected_contribution / horizon_open_gap, 1)

priority_score = 100 × (
    0.40 × contribution_coverage
  + 0.25 × urgency
  + 0.20 × actionability
  + 0.15 × business_fit
)
```

The four inputs use the same meanings and ranges as v1. Missing optional
`business_fit` remains 0.5. The weights are inherited unchanged from the
pre-existing implementation; they are not selected from v4 labels.

If `horizon_open_gap == 0`, the objective is already met for this horizon. The
ranker returns no recommendation, marks candidates `objective_already_met`,
and does not divide by zero or use an annual gap. An incomplete, inconsistent,
negative, or mismatched horizon objective fails validation.

Rankings remain deterministic. They sort by descending total score, urgency,
and expected contribution, followed by ascending stable candidate ID. The
existing P0/P1/P2 thresholds and explanation format remain unchanged.

## Evaluation decisions

The expected-contribution-only comparator remains the fixed baseline and uses
the exact same formal candidate set. The pre-declared stress profiles remain:
balanced, contribution-heavy, urgency-heavy, actionability-heavy, and
business-fit-heavy. They are diagnostics, not a weight search.

M2 v4 requests K values 1, 3, and 5, but its formal sets contain only three or
four candidates per scenario. Therefore:

- Precision@1, NDCG@1, Precision@3, and NDCG@3 are the fixed primary metrics;
- ordinary Precision@5 and NDCG@5 are `not_applicable` because at least one
  scenario has fewer than five formal candidates;
- the evaluator records the requested K, supported K, per-scenario formal
  counts, and the reason K=5 is unavailable; and
- no future or unsupported candidate is padded into the formal ranking.

The evaluator may additionally report a clearly named full-list diagnostic in
a later version, but it must not relabel an adaptive denominator as ordinary
Precision@5. Macro means and population standard deviations will be reported
for the supported fixed K values after human consensus is complete.

## Reproducibility boundary

The v4 annotation master is currently `pending`; final metrics must not be
generated yet. After three independent blind rankings and M2's pre-declared
consensus procedure are complete, M4 will run the same committed code without
changing this score or the primary K policy. The result will retain dataset,
annotation, formula, candidate-count, agreement, baseline, and sensitivity
provenance.

After M2 marks the v4 consensus file complete, reproduce it with:

```bash
./.venv/bin/python scripts/evaluate_prioritization.py \
  --scenarios data/evaluation/m2_candidate_scenarios_v4.json \
  --annotations data/evaluation/m2_candidate_annotations_v4.json \
  --output data/evaluation/m4_prioritization_results_v4.json
```
