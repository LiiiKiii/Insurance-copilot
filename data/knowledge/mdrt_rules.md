# Written Premium Excellence Standard 2026

## Purpose

This internal standard measures general-insurance production using written premium in USD. It is not an external professional designation.

## 2026 Threshold

| Metric | Requirement | Deadline |
|---|---:|---|
| Written premium | USD 818,000 | 31 December 2026 |

The threshold is based on the annualised 75th percentile of the selected 50-agent demonstration cohort. The database key remains `protection_premium` for API compatibility, but its business meaning is written premium.

## Counting Rules

- Count written premium recorded for bound business in the reporting period.
- Pending cases do not count as achieved production until bound, but may be shown separately as potential gap coverage.
- Cancelled, declined, duplicated, or reversed business does not count.
- Use the source amount in USD; do not apply an exchange-rate conversion.
- When the source denominator or amount is unavailable, report it as unavailable rather than zero.

## Progress Review

1. Calculate the nominal gap: target minus current written premium.
2. Show pending premium separately and deduct it only in scenario analysis.
3. Compare the required daily run rate with the agent's recent monthly average.
4. Prioritise pending cases, high-probability quotations, renewals, and suitable cross-line opportunities.

## Recognition

Agents who reach the threshold receive the internal Written Premium Excellence recognition and a USD 2,500 professional-development allowance, subject to data-quality and compliance review.
