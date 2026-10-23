# M4 Candidate Prioritisation — Current Coursework Evaluation

## Scope

M4 provides a data-source-independent, deterministic ranking component. It:

- filters ineligible, unauthorised, non-compliant, duplicate, and invalid
  candidates;
- calculates an explainable weighted score;
- applies stable tie-breaking and Top-K selection;
- returns P0/P1/P2 levels, score components, actions, timing, evidence, and
  ranking reasons;
- exposes the contract through the authenticated planning API; and
- evaluates ranking quality against a fixed expected-contribution baseline.

The default score is:

```text
priority_score = 100 × (
    0.40 × expected_contribution_score
  + 0.25 × urgency
  + 0.20 × actionability
  + 0.15 × business_fit
)
```

`expected_contribution_score` is expected contribution divided by the verified
open gap and capped at 1. The remaining inputs use a 0–1 scale. Missing optional
`business_fit` uses 0.5. Missing or invalid required values exclude a candidate
with a deterministic reason. The implementation does not train or tune a model
on the evaluation labels.

## Dataset and labels

The current experiment uses `m2-coursework-candidates-v3`:

- 10 agent scenarios;
- 100 raw candidates;
- 60 candidates remaining after eligibility, permission, and compliance
  filtering; and
- 6 evaluated candidates per scenario.

All monetary values are USD. The candidate and policy records are synthetic
coursework data derived from the project's aggregate and mock records; they are
not production customer data.

Two non-M4 annotators independently ranked the six eligible candidates in each
scenario. The committed labels record AI-assisted evidence adjudication of
disagreements between those human rankings. The adjudication did not use M4
scores, scoring features, baseline rankings, or evaluation metrics, but it is
not equivalent to consensus reached by a third human or a joint human review.
This provenance must remain visible when the results are reported.

The two human rankings show limited agreement: mean Kendall tau-a is 0.173333,
mean Spearman rho is 0.240000, the same candidate is ranked first in 40% of
scenarios, and mean Top-3 overlap is 0.533333. These figures justify treating
the labels as a preliminary coursework reference rather than a stable expert
gold standard.

Graded relevance is assigned from the adjudicated order: positions 1–2 receive
grade 3, positions 3–4 grade 2, position 5 grade 1, and position 6 grade 0.
Precision@K treats every grade above zero as relevant. NDCG@K uses the complete
graded labels and is therefore the more discriminating metric in this setup.

## Reproduction

Run the current multi-scenario experiment:

```bash
./.venv/bin/python scripts/evaluate_prioritization.py \
  --output data/evaluation/m4_prioritization_results.json
```

Run the earlier single-fixture pipeline check when needed:

```bash
./.venv/bin/python scripts/evaluate_prioritization.py --synthetic
```

The tracked JSON result contains every scenario ranking, per-scenario metrics,
aggregate means and population standard deviations, the baseline comparison,
and the sensitivity profiles.

## Current baseline comparison

The following values are macro averages over the 10 scenarios. Parentheses
show population standard deviation across scenarios.

| K | Weighted Precision@K | Baseline Precision@K | Weighted NDCG@K | Baseline NDCG@K |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1.000000 (0.000000) | 1.000000 (0.000000) | 1.000000 (0.000000) | 0.514285 (0.339267) |
| 3 | 1.000000 (0.000000) | 0.933333 (0.133333) | 0.948759 (0.074181) | 0.596313 (0.097358) |
| 5 | 1.000000 (0.000000) | 0.800000 (0.000000) | 0.978259 (0.022715) | 0.633544 (0.082634) |

The weighted model improves mean NDCG over the expected-contribution-only
baseline by 0.485714 at K=1, 0.352446 at K=3, and 0.344716 at K=5. Its mean
Precision improves by 0.066667 at K=3 and 0.200000 at K=5; Precision@1 is tied
because both approaches select a non-zero-relevance candidate first in every
scenario. The NDCG results show that the weighted model places higher-grade
candidates earlier even when binary precision cannot distinguish the orders.

## Feature-scale diagnostic

The default scorer was kept unchanged to avoid choosing a transformation after
seeing the evaluation labels. A separate diagnostic nevertheless reveals an
important data-scale limitation. Across the 60 eligible candidates, the mean
normalised expected-contribution value is 0.010790 and its mean weighted
contribution is only 0.431432 points out of 100 (maximum 1.443200). In contrast,
the mean weighted points are 19.304167 for urgency, 16.333333 for actionability,
and 12.725000 for business fit. The nominal 40% contribution weight therefore
has little effective influence because individual expected contributions are
small relative to the annual open gaps in this dataset.

This is reported as a limitation, not corrected by post-hoc tuning. A future
version should define a business-justified gap horizon that matches the
follow-up period, or pre-register another normalisation rule and evaluate it on
new labels or a holdout set.

## Weight sensitivity

The sensitivity analysis uses fixed stress profiles, not weights selected by
searching the labels. Each `*_heavy` profile assigns 0.50 to the named factor,
except `contribution_heavy`, which assigns 0.70 to create a clear comparison
with the contribution-only baseline. The remaining mass is documented in the
tracked result.

| Profile | Mean Precision@5 | Mean NDCG@5 | NDCG@5 change from default |
| --- | ---: | ---: | ---: |
| Default | 1.000000 | 0.978259 | 0.000000 |
| Balanced | 1.000000 | 0.969070 | -0.009189 |
| Contribution-heavy | 1.000000 | 0.974459 | -0.003800 |
| Urgency-heavy | 1.000000 | 1.000000 | +0.021741 |
| Actionability-heavy | 1.000000 | 0.994512 | +0.016253 |
| Business-fit-heavy | 0.820000 | 0.879161 | -0.099098 |

The default result remains above the baseline, but the sensitivity profiles
show ordering changes. Urgency-heavy and actionability-heavy profiles score
slightly better on these labels, whereas the other profiles score worse. This
must not be treated as evidence for changing the production defaults: the
adjudication criteria explicitly emphasise actionable evidence and earlier
deadlines, so those profiles are especially aligned with this small synthetic
evaluation set.

## Interpretation and limitations

The experiment supports the narrow conclusion that, on these ten synthetic
coursework scenarios and their committed labels, the four-factor ranking orders
follow-ups better than sorting by expected contribution alone. It does not
show improved conversion, premium, retention, or other production outcomes.

Important limitations are:

- only 10 scenarios and 60 eligible candidates are evaluated;
- candidates and case-level evidence are synthetic;
- features and labels share domain concepts such as urgency and actionability;
- the final disagreement resolution is AI-assisted rather than a third-human
  adjudication;
- agreement between the two human annotators is low;
- the annual-gap normalisation makes expected contribution much weaker in
  practice than its nominal 40% weight suggests;
- Precision@K is coarse because five of six candidates per scenario have
  non-zero relevance; and
- no holdout dataset, online experiment, confidence interval, or statistical
  significance test is claimed.

## Integration boundary

M4 accepts prepared, authorised candidate records. It does not query or modify
M2 data, recalculate M1 gaps, or replace M3 evidence. M1 controls whether and
how the chat runtime supplies verified candidates; M5 renders the structured
actions returned by the backend. The experiment code is offline and does not
change those runtime boundaries.
