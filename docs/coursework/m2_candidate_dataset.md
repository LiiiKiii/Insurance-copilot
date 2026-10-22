# M2 Candidate Dataset for M4 Prioritisation

## Delivery scope

`data/evaluation/m2_candidate_scenarios.json` contains five deterministic
agent scenarios and forty candidates. Each scenario contains four pending
policies and four client follow-up candidates, satisfying the requested range
of 5–10 scenarios, 30–50 candidates in total, and 5–10 candidates per
scenario. No random row sampling is used.

All monetary values are denominated in USD. The file is regenerated with:

```powershell
python scripts/build_m2_candidate_dataset.py
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
| `eligible` | Pending positive-premium policy, or active/actionable client | Derived |
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
- **Reference relevance:** a deterministic 0–3 coursework label supports
  offline evaluation. It is explicitly not a production judgement label.

## Data provenance

The original agency-performance dataset contains agency-level performance and
product aggregates, not individual customers or case-level policies. The
project customer and pending-policy records are therefore synthetic coursework
records generated from source-derived agent and product distributions.

The candidate file preserves this distinction in `data_origin`:

- candidate and client records retain their existing synthetic origin labels;
- identifiers, premium, status, dates, tags, and products are copied from the
  existing project records;
- contribution estimates, decisions, scores, dates, and relevance grades are
  marked and documented as derived values.

The dataset is suitable for coursework integration and deterministic testing.
It must not be presented as real customer-level production data or evidence of
commercial performance.
