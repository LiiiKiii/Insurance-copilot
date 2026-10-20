# A6-M4 planning baseline freeze

Validated on 2026-10-20 on branch `M4` at `03caeb8`. This milestone
validates the planning behavior already present in the merged repository. It
does not change planning calculations, action templates, API contracts, or
priority rules.

## Acceptance result

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_chase_plan.py tests/test_insurance_tools.py tests/test_planning_api.py -q
```

Result: **19 passed, 0 failed**.

The accepted scope covers:

- pending-premium deduction before chase-plan construction;
- equal weekly target allocation and daily production requirements;
- automatic selection of the most urgent open competition;
- administrator-managed action templates and safe fallbacks;
- stable responses for covered targets, unknown competitions, and data errors;
- improvement-advice Top-N handling, template rendering, and P0/P1/P2 labels;
- planning API route registration, request forwarding, and invalid-response
  handling.

## Functional boundary

The chase plan is a deterministic schedule. It divides an already calculated
gap across the remaining weeks and attaches configured action text. The
improvement-advice tool selects attribution weaknesses in their supplied order
and maps them to predefined guidance.

These behaviors are **not an optimisation algorithm**. In particular, the
accepted baseline does not:

- score or rank customers, leads, or pending policies;
- estimate conversion probability or expected contribution;
- select an optimal Top-K set under business constraints;
- learn weights from data;
- evaluate a ranking with Precision@K or NDCG@K.

P0, P1, and P2 are deterministic template labels. They must not be described
as the output of a customer-ranking or optimisation model.

## Known limitation

The improvement-advice template behavior is tested against a deterministic
attribution-gap contract. The corresponding attribution calculation module is
not present in the current repository, so an end-to-end runtime call to that
tool remains unavailable until that dependency is implemented. The chase-plan
tool and the planning API boundary are executable within the accepted scope.

Status: **A6-M4 baseline accepted with the documented attribution dependency**.
