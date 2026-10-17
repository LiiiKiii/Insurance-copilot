# Candidate Prioritisation Interface

## Status and Scope

This document defines the planned boundary for
`nanobot/agent/tools/insurance/planning_layer/prioritization.py`.

The interface is an A3 integration contract only. The prioritisation model,
candidate-ranking algorithm, Top-K selection, and ranking evaluation are not
implemented in this round. The existing chase-plan and improvement-advice
tools remain deterministic, template-based functions and must not be described
as optimisation results.

## Proposed Tool Contract

The future tool name will be `prioritize_followups`. It will accept one JSON
object and return one JSON object so that the same contract can be used by the
agent tool registry and a future planning API endpoint.

### Input

| Field | Type | Required | Definition |
| --- | --- | --- | --- |
| `agent_id` | string | yes | Agent whose authorised opportunities are ranked |
| `objective` | object | yes | Target metric, verified open gap, unit, and deadline |
| `candidates` | array | yes | Eligible customer or pending-policy records supplied by the data layer |
| `constraints` | object | no | Top-K limit, permission scope, compliance exclusions, and capacity limits |
| `weights` | object | no | Versioned, configurable score-component weights |

The authoritative performance gap, feasibility result, candidate records, and
permission/compliance decisions are inputs. The prioritisation module will not
recalculate or override them.

Each candidate must provide a stable `candidate_id`, an `expected_contribution`,
an `urgency` value, an `actionability` value, and the evidence fields required
by the configured score components. Missing optional values must be handled by
documented deterministic defaults; missing required values make the candidate
ineligible.

### Output

| Field | Type | Definition |
| --- | --- | --- |
| `agent_id` | string | Agent associated with the ranking |
| `objective` | object | Echo of the objective version used for the run |
| `ranking_version` | string | Version of the scoring configuration |
| `recommendations` | array | Eligible candidates ordered from highest to lowest priority |
| `excluded_candidates` | array | Candidate identifiers with deterministic exclusion reasons |

Each recommendation will contain:

- `candidate_id` and `rank`;
- `priority_score` and a `score_components` breakdown;
- an assigned `priority_level` (`P0`, `P1`, or `P2`);
- a recommended action and timing;
- supporting evidence and a human-readable ranking reason.

Scores tied after normalisation will be ordered by urgency, expected
contribution, and finally `candidate_id`, in that order. This makes repeated
runs over identical inputs stable and auditable.

## Proposed API Boundary

The future HTTP endpoint is reserved as:

```text
POST /api/planning/prioritization
```

It will use the same input and output objects as the tool contract. It is not
registered in A3. The two routes registered in this round expose only the
existing baseline:

```text
POST /api/planning/chase-plan
POST /api/planning/improvement-advice
```

## Ownership and Validation

- M1 supplies authoritative rules, feasibility, and shared API conventions.
- M2 supplies prepared candidate and performance records.
- M3 supplies relevant knowledge and source metadata.
- M4 owns filtering, scoring, ranking, recommendation construction, and
  Precision@K/NDCG@K evaluation.
- M5 renders the structured recommendation response.

The implementation round must add unit tests for filtering, score components,
normalisation, missing values, tie-breaking, Top-K selection, and deterministic
ordering. Evaluation must compare the ranking with the agreed
expected-contribution baseline using a fixed labelled dataset.
