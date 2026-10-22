# M2 Candidate Dataset for M4 Prioritisation

## Delivery scope

`data/evaluation/m2_candidate_scenarios.json` contains ten deterministic agent
scenarios and one hundred raw candidates. Each scenario contains four pending
policies, two clients with explicit renewal/follow-up signals, and four
filter-control clients without such a signal. The eligibility filter therefore
retains six candidates per scenario and sixty candidates overall. This meets
the requested range of 8–10 scenarios, 10–15 raw candidates per scenario,
80–120 raw candidates overall, and at least 50–60 candidates after filtering.
No random row sampling is used.

The primary evaluation cut-offs are `K = 1, 3, 5`.

All monetary values are denominated in USD. The file is regenerated with:

```powershell
python scripts/build_m2_candidate_dataset.py
```

The generator writes two files:

- `data/evaluation/m2_candidate_scenarios.json` contains complete candidate
  inputs, derived features, filtering evidence, and source traceability;
- `data/evaluation/m2_candidate_blind.json` contains only evidence fields for
  independent human ranking.

Human rankings and consensus labels are stored separately in
`data/evaluation/m2_candidate_annotations.json`. The generator never reads,
creates, or overwrites that annotation file.

## Human annotation UI

Start the first annotator's local interface from the repository root:

```powershell
python scripts/annotate_m2_candidates.py
```

The interface displays six eligible candidates per scenario and asks one
question: which candidate should the agent follow up first to reduce the open
gap before the deadline? Rank all six candidates without ties. Consider, in
order, whether there is a clear action to take, time pressure, and potential
premium impact. Premium must not determine the ranking by itself. The UI saves
only the human ordering to `data/evaluation/m2_candidate_annotations.json`.

A later independent annotator should avoid viewing the first ranking and run:

```powershell
python scripts/annotate_m2_candidates.py --annotator non_m4_annotator_2
```

## Field mapping

| Candidate field | Existing project field or rule | Lineage |
| --- | --- | --- |
| `scenario_id` | `SCN-<agent_id>` | Derived identifier |
| `agent_id` | Agent record `agent_id` | Source-derived project field |
| `candidate_id` | Policy `policy_id` or client `client_id` | Existing project field |
| `premium` | Policy or client `premium` | Existing project field |
| `expected_contribution` | Policy premium × agent conversion rate; client premium × agent retention rate | Derived |
| `policy_status` | Policy `status`; null for client-only candidates | Existing project field / not applicable |
| `submit_date` | Policy `submit_date`; null for client-only candidates | Existing project field / not applicable |
| `estimated_approval_days` | Policy minimum and maximum approval days | Existing project field / not applicable |
| `client_tags` | Client `tag_labels` | Existing project field |
| `product_type` | Policy product or deterministic client-need mapping | Direct or derived |
| `eligible` | Pending positive-premium policy, or client with an explicit renewal/follow-up signal | Derived |
| `permission_allowed` | Candidate belongs to the scenario agent | Derived |
| `compliance_allowed` | Agent is not blocked by the training-compliance gate | Derived |
| `source_record_id` | Original project policy/client identifier | Traceability field |

## Score rules

- **Expected contribution:** policy candidates use premium multiplied by the
  agent's historical conversion rate. Client candidates use premium multiplied
  by the agent's retention rate. This is a transparent estimate, not a trained
  probability model.
- **Urgency:** policy urgency uses the expected decision date calculated from
  submit date plus maximum approval days. Awaiting-document cases receive an
  additional urgency increment. Client urgency uses renewal-due, follow-up, and
  high-value tags in that order.
- **Actionability:** awaiting-document policies rank above passive underwriting
  cases because the agent can take a direct action. Client follow-up and renewal
  tags indicate high actionability.
- **Business fit:** starts at 0.4 and adds documented increments for matching
  the agent's product specialties, matching client need category, and a
  high-value tag. The result is capped at 1.

These derived scores are M4 inputs and data-quality aids. They are not final
relevance labels and are not included in the blinded annotation view.

## Filtering and evaluation scope

Each scenario starts with ten candidates. Four pending policies and two
renewal/follow-up clients pass the deterministic eligibility, permission, and
compliance gates. Four ordinary active clients are retained in the raw input as
filter-control records and are excluded with the explicit `ineligible` reason.
Consequently the complete dataset contains 100 raw candidates and 60 eligible
candidates.

M4 should report Precision@K and NDCG@K at `K = 1`, `K = 3`, and `K = 5`.
M2 supplies the candidate structure but does not implement the final ranking
comparison or tune M4 results against the labels.

## Blinded human annotation

The blind file contains, for each scenario, only the scenario ID, agent ID,
open gap, deadline, currency, and the six eligible candidates' business
evidence. It excludes expected contribution, urgency, actionability, business
fit, M4 scores/rankings, baseline rankings, and generated relevance grades.

Two non-M4 team members should independently rank the six eligible candidates
in each scenario. After resolving disagreements, convert the consensus order
to graded relevance:

- positions 1–2: grade 3;
- positions 3–4: grade 2;
- position 5: grade 1;
- position 6: grade 0.

The forty filtered candidates remain in the full dataset for filtering tests
but do not participate in ranking-quality evaluation. A single annotator is
acceptable for a preliminary coursework run, but it must be reported as a
single-annotator limitation. Two independent annotators are preferred because
they provide a defensible consensus process and reduce individual bias.

## Data provenance

The original agency-performance dataset contains agency-level performance and
product aggregates, not individual customers or case-level policies. The
project customer and pending-policy records are therefore synthetic coursework
records generated from source-derived agent and product distributions.

The candidate file preserves this distinction in `data_origin`:

- candidate and client records retain their existing synthetic origin labels;
- identifiers, premium, status, dates, tags, and products are copied from the
  existing project records;
- contribution estimates, decisions, scores, and dates are marked and
  documented as derived values;
- final relevance labels are collected independently from blinded human
  rankings and never generated from the M4 input features.

The dataset is suitable for coursework integration and deterministic testing.
It must not be presented as real customer-level production data or evidence of
commercial performance.
