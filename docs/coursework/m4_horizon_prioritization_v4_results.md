# M4 Horizon-Aligned Prioritisation — Final v4 Evaluation

## Scope

The final `m4-horizon-weighted-v4` ranker operates on the formal in-horizon
candidate set produced under the M1/M2 v4 contract. It retains eligibility,
permission, compliance, metric, currency, expected-realisation, zero-gap,
Top-K, audit and explanation controls.

Only the 10 available synthetic scenarios are used. Model selection uses
scenario-level leave-one-out validation: each fold selects weights on nine
scenarios and evaluates the untouched tenth scenario. Every scenario is the
held-out fold exactly once. No additional dataset or production outcome is
claimed.

The tracked artifacts are:

- `data/evaluation/m4_horizon_weight_selection_v3.json` — fold allocation,
  grid, selected weights and out-of-fold comparison; and
- `data/evaluation/m4_prioritization_results_v4.json` — final rankings,
  metrics, provenance and sensitivity results.

## Model-selection rule

The search enumerates all 969 four-factor weight combinations on a 0.05 grid
whose weights sum to one and requires every factor to retain at least 0.05
weight. Within each training fold, a candidate must not score below the
expected-contribution baseline on Precision@1. Among eligible candidates,
selection maximises NDCG@3, then NDCG@1, Precision@1 and Precision@3, followed
by deterministic weight tie-breakers.

The final weights selected using all 10 scenarios are:

```text
expected_contribution = 0.20
urgency               = 0.40
actionability         = 0.35
business_fit          = 0.05
```

These weights also reflect the deployed decision context rather than metrics
alone. The tool prioritises actions that can be completed inside a 30-day
planning horizon, so urgency and actionability jointly receive most of the
weight. Expected contribution remains material but is capped once an action
covers the remaining horizon gap. Business fit remains a positive ranking
factor, while incompatible products, permissions and compliance cases have
already been removed by hard eligibility gates before scoring. The 0.05 floor
prevents any factor from being silently discarded.

The resulting score is:

```text
priority_score = 100 × (
    0.20 × min(expected_contribution / horizon_open_gap, 1)
  + 0.40 × urgency
  + 0.35 × actionability
  + 0.05 × business_fit
)
```

This differs from the raw expected-contribution baseline by capping contribution
at the remaining horizon gap and incorporating urgency, actionability and
business fit. Candidates tied on the weighted score use the existing
deterministic urgency, raw-contribution and candidate-ID tie-break sequence.

## Data and human reference

- 10 agent scenarios and 100 raw candidates;
- 37 formal in-horizon candidates, with 3 or 4 per scenario;
- USD written premium over the inclusive 30-day planning horizon;
- three independent non-M4 annotators, each completing all 10 scenarios; and
- deterministic human-only consensus under `m2-v4-consensus-v1`.

Across 30 scenario/annotator-pair comparisons, mean Kendall tau-a is 0.555556,
mean Spearman rho is 0.666667, same Top-1 rate is 0.733333, and mean Top-3
overlap is 0.855556. Top-3 overlap is automatically 1 for three-candidate
scenarios and is less informative than the rank correlations.

## Out-of-fold and final comparison

The leave-one-out folds selected positive-weight models from nine scenarios and
evaluated the untouched tenth. The final fixed model was then selected from all
10 scenarios for the reported fitted comparison.

### Leave-one-out result

| K | OOF Precision@K | Baseline Precision@K | Delta | OOF NDCG@K | Baseline NDCG@K | Delta |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.000000 | 1.000000 | 0.000000 | 0.733333 | 0.666667 | +0.066667 |
| 3 | 0.666667 | 0.833333 | -0.166667 | 0.837984 | 0.876069 | -0.038085 |

This is the more conservative generalisation estimate. It preserves Top-1
Precision and improves NDCG@1, but does not beat the baseline at K=3.

### Final fitted comparison

| K | Selected Precision@K | Baseline Precision@K | Delta | Selected NDCG@K | Baseline NDCG@K | Delta |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.000000 | 1.000000 | 0.000000 | 0.942857 | 0.666667 | +0.276190 |
| 3 | 0.666667 | 0.833333 | -0.166667 | 0.907364 | 0.876069 | +0.031295 |
| 5 | N/A | N/A | N/A | N/A | N/A | N/A |

The fitted model matches baseline Precision@1 and improves both fitted NDCG
metrics, while Precision@3 is lower by 0.166667. It supports only a claim of
better graded ordering on these 10 scenarios. The leave-one-out result above
does not support a K=3 generalisation claim, and neither result establishes
better conversion or premium production.

K=5 is not applicable because at least one scenario contains fewer than five
formal candidates. Out-of-horizon candidates are never used as padding.

## Sensitivity

| Profile | Precision@1 | NDCG@1 | Precision@3 | NDCG@3 | NDCG@3 change |
| --- | ---: | ---: | ---: | ---: | ---: |
| Selected default | 1.000000 | 0.942857 | 0.666667 | 0.907364 | 0.000000 |
| Balanced | 0.600000 | 0.390476 | 0.666667 | 0.698289 | -0.209075 |
| Contribution-heavy | 1.000000 | 0.580952 | 0.666667 | 0.774493 | -0.132871 |
| Urgency-heavy | 0.900000 | 0.690476 | 0.666667 | 0.835954 | -0.071410 |
| Actionability-heavy | 0.700000 | 0.557143 | 0.666667 | 0.798284 | -0.109080 |
| Business-fit-heavy | 0.500000 | 0.290476 | 0.666667 | 0.589936 | -0.317428 |

The selected default has the highest fitted NDCG@1 and NDCG@3 among these fixed
stress profiles while preserving baseline Precision@1. All profiles retain all
four factors; the grid search additionally enforces the explicit 0.05 floor.

## Reproduction

```bash
./.venv/bin/python scripts/select_m4_horizon_weights.py \
  --output data/evaluation/m4_horizon_weight_selection_v3.json

./.venv/bin/python scripts/evaluate_prioritization.py \
  --scenarios data/evaluation/m2_candidate_scenarios_v4.json \
  --annotations data/evaluation/m2_candidate_annotations_v4.json \
  --output data/evaluation/m4_prioritization_results_v4.json
```

The evaluation uses a small synthetic dataset and reuses all ten scenarios
across model-selection folds. It does not provide an external holdout,
confidence interval, significance claim, online experiment or external-validity
claim.
