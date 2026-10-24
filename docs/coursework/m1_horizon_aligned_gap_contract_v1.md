# M1 Business Data Contract — Horizon-Aligned Gap v1

**Status:** M1-approved business definition for coursework v4 preparation; implementation and M2 data generation pending.  
**Owner:** M1 — Reasoning and System Integration  
**Consumers:** M2 (data preparation), M4 (ranking/evaluation), M1 (Agent adapter), M5 (presentation).  
**Scope:** Synthetic coursework follow-up prioritization for **USD written premium**. This contract establishes business meaning, not scoring weights or evaluation results.

## 1. Normative business decision

Short-horizon candidate contribution must be compared against a **gap for the same performance metric, currency, and crediting period**. Annual `open_gap` ending **2026-12-31** is for **annual target tracking and annual feasibility only**. It **MUST NOT** be the formal normalization denominator for short-horizon follow-up contribution.

**Prohibited:** Computing `horizon_target` or `horizon_open_gap` by simply dividing annual gap/target by months or days. Business rules must be defined independently of M4 ranking metrics.

## 2. Planning horizon and boundaries

- Coursework v4 uses a **30-calendar-day** horizon, a declared synthetic planning convention (not an insurance industry standard).
- `as_of_date`: source data snapshot date (`YYYY-MM-DD`).
- `planning_horizon_start`: **day after** `as_of_date`, inclusive.
- `planning_horizon_end`: the **30th day including** `planning_horizon_start`, inclusive; equivalently start + 29 days.
- For `as_of_date = 2026-05-31`: **2026-06-01 through 2026-06-30**.
- Use one documented business calendar/timezone for all snapshot, crediting, and expected-realization dates; do not silently move a record across window boundaries.
- Other horizons require a new documented/versioned business decision.

## 3. Objective schema and calculation

| Field | Type | Definition |
| --- | --- | --- |
| `metric` | string | `written_premium` for this contract. |
| `unit` | string | `USD`; never implicitly convert HKD or policy counts. |
| `as_of_date` | ISO date | Source snapshot date. |
| `annual_open_gap` | number >= 0 | Remaining **annual** written-premium target gap; annual tracking/feasibility only. |
| `annual_deadline` | ISO date | Annual target end, currently `2026-12-31`. |
| `planning_horizon_start` | ISO date | Inclusive horizon start. |
| `planning_horizon_end` | ISO date | Inclusive horizon end. |
| `horizon_target` | number >= 0 | Explicit target for this exact horizon, grounded in a period-specific approved plan or recorded synthetic planning rule. |
| `horizon_current` | number >= 0 | Written premium **confirmed and credited to this horizon**, known at the specified data cutoff; excludes pending/unapproved/forecast income. |
| `horizon_open_gap` | number >= 0 | `max(horizon_target - horizon_current, 0)`. Must be independently recomputable. |
| `horizon_target_source` | object | Source type, source reference or synthetic rule ID/version, inputs and rationale. |
| `horizon_current_source` | object | Evidence of confirmed credits and crediting/cutoff rule; explicitly document zero verified credits. |
| `is_synthetic` | boolean | True if horizon inputs or business assumptions are synthetic. |

### Target sourcing

1. Prefer a written, period-specific sales target or an explicitly documented chase plan for the **same 30 days**, metric, and currency.
2. If the dataset lacks an approved period target, M2 may generate a **reproducible synthetic planning assumption**, with predetermined rule ID, inputs, and rationale. Label it as synthetic; do not misrepresent it as company-approved or choose it to improve M4 scores.
3. **Do not** divide the annual gap or annual target evenly across remaining months/days, or use any undocumented equivalent prorating shortcut.
4. `horizon_current` consists only of **confirmed credited written premium** attributed to the defined future interval as known at the snapshot/cutoff. A future horizon may reasonably have zero credited activity; a nonzero amount requires dated evidence. Do not reuse annual-to-date premium or count projected approvals as `current`.
5. If `horizon_target` or reliable `horizon_current` cannot be established, mark the horizon objective **unavailable**, rather than fabricating a gap or reverting to the annual gap.

## 4. Candidate expected contribution and realization

| Field | Definition |
| --- | --- |
| `action_deadline` | Date by which follow-up should occur; **not** the date premium is credited. |
| `expected_realization_date` | Expected date written premium becomes creditable; ISO date or null if unsupported. |
| `expected_contribution` | Nonnegative **expected USD written premium that may be credited in this 30-day window**, after applying a documented estimate rule; never described as already confirmed income. |
| `contribution_basis` | Source identifiers, input assumptions, rule/version, and synthetic provenance. |
| `within_planning_horizon` | Whether supported expected realization is within inclusive start/end. |
| `out_of_horizon_reason` | If outside/unknown, explanation for exclusion from horizon contribution. |

**Rules:**

- Only in-window expected credits for the same metric and currency can count toward the formal short-horizon contribution component. An action performed within the horizon does not prove its premium will be credited within the horizon.
- **After horizon end:** horizon contribution = 0; retain candidate as a potentially useful **future follow-up opportunity**, distinctly labelled, not as in-window contribution. M2/M4 must disclose whether such candidates are excluded from the current-period ranking or represented in a separate group; never silently score their future premium as current-window credit.
- **Before horizon start:** cannot count as prospective new contribution; prevent double counting against `horizon_current`.
- **Unknown / unsubstantiated realization date or amount:** do not assume in-window credit; exclude from formal horizon contribution and record missing evidence.
- Candidate follow-up eligibility, agent/tenant permission, and compliance decisions remain separate gates. A candidate can warrant attention despite zero short-horizon expected premium.
- Expected contributions are uncertain, not guaranteed, and multiple candidates may be correlated; summation needs an explicit non-duplication policy.

## 5. Formal ranking denominator, exceptions and boundaries

- **Formal v4 short-horizon contribution denominator:** `objective.horizon_open_gap` — never `annual_open_gap` or v3 annual `objective.open_gap`.
- Numerator and denominator must match **written premium**, **USD**, and **the exact inclusive horizon**.
- Where `horizon_open_gap > 0`, a contribution coverage ratio may compare `expected_contribution / horizon_open_gap` under M4's separately versioned ranking implementation. This document does not change its weights or decide evaluation outcomes.
- Where `horizon_open_gap == 0`, **do not divide by zero or fall back to annual gap**. M4 must explicitly define and test the no-open-gap policy before treating such output as a formal horizon ranking.
- Missing, mismatched, or unsupported objective/candidate fields must fail validation or yield explicit unavailable/excluded status. No silent annual-gap fallback.
- Server-side verified tenant/agent identity, permission/compliance gates, and candidate provenance remain authoritative. Model-generated fields are not a source of permission or monetary evidence.
- Explain **estimated coverage** separately from verified performance; preserve supporting data references and auditability.

## 6. Dataset v4 and evaluation handoff

- M2 should generate a separately versioned `m2-coursework-candidates-v4` dataset; **preserve v3 files and annotation/evaluation artifacts without overwrite**.
- Retain 10 scenarios and 100 raw candidates, stable IDs/lineage, and documented eligibility/permission/compliance gates unless a separate, independently justified change is approved.
- Document exact source/rule and crediting timeline for each synthetic horizon target and expected realization **before M4 evaluation**. Do not tune assumptions from M4 scores.
- v3 human rankings/labels cannot be automatically transferred to v4: annotators now see a materially different objective. Prepare new blinded v4 material and obtain fresh independent rankings under this definition.
- M4 owns ranking/evaluation adaptation after valid v4 input is delivered; M1 owns subsequent safe candidate-adapter integration.
- Existing v3 behavior may remain explicitly labelled as an annual-gap historical synthetic demo, **not** as formal horizon-aligned prioritization.

## 7. Illustrative objective only — values are NOT approved planning targets

```json
{
  "metric": "written_premium",
  "unit": "USD",
  "as_of_date": "2026-05-31",
  "annual_open_gap": 228250,
  "annual_deadline": "2026-12-31",
  "planning_horizon_start": "2026-06-01",
  "planning_horizon_end": "2026-06-30",
  "horizon_target": 50000,
  "horizon_current": 18000,
  "horizon_open_gap": 32000,
  "horizon_target_source": {"type": "synthetic_planning_rule", "rule_id": "ILLUSTRATION_ONLY"},
  "horizon_current_source": {"type": "illustration_only", "crediting_rule": "confirmed in-horizon credits"},
  "is_synthetic": true
}
```

The example numbers **50,000**, **18,000**, and **32,000** show the field relationship only. M2 must not copy them as actual scenario values or derive targets by prorating the annual gap.

## 8. M2 v4 acceptance checklist

- [ ] Each scenario has the explicit 30-day inclusive boundaries and business timezone.
- [ ] `horizon_target` has a real approved source or versioned **synthetic** period-specific rule; annual-gap division is absent.
- [ ] `horizon_current` is evidenced as confirmed in-window credited premium, or justified zero.
- [ ] `horizon_open_gap` is recomputed and validated.
- [ ] Expected realization and contribution are matched to the same USD written-premium horizon; out-of-window/unknown contributions are excluded from its monetary coverage.
- [ ] Annual gap is retained solely for annual monitoring and feasibility.
- [ ] Ownership, permission, compliance, source lineage and missing-data behavior are preserved.
- [ ] v3 raw and annotation files are intact; v4 blinded data and new independent annotation files are prepared.
