# 50-agent runtime data consistency

## Two separate, versioned packages

- `data/mock/`: `life-demo-50-v1`, a fully synthetic HKD life-insurance coursework runtime.
- `data/source/agencyperformance-50-v1.zip`: the exact USD general-insurance seed snapshot from Git commit `ea8fce6`. Its SHA-256 is recorded beside it. This archive contains project seed JSON, not the original Kaggle CSV.
- `data/evaluation/`: existing M4 v3 scenarios, blind evidence and adjudicated labels remain frozen. Their `source_path` values refer to `data/mock` **at ea8fce6**, available inside the snapshot, not today's runtime directory. The M4 generator and the default M1 coursework candidate source now read that archive so its existing output is reproducible.
- Original CSV and intermediate processing files remain outside the repository under `files/agencyperformance/`; this change does not overwrite them.

The runtime reuses only stable fictional identity/client identifiers. Life premiums, commission, product mix, activity and qualification examples are synthetic, with explicit provenance. No USD amount was converted or renamed into life-insurance FYC, MDRT credit or premium. The sample recognition thresholds in `data/config/life_demo_rules.json` are inherited coursework fixtures, not verified professional qualification standards. Meeting them is not certification.

## Runtime invariants

All seven JSON files share the same 50 agent IDs and one reporting snapshot (2026-10-23). The package contains 900 clients, 200 pending policies, 150 assessments, 50 attribution records and 250 entries for five independent `LIFE_DEMO_*` competitions/honours. Existing historical competition IDs are not repurposed.

Policy/client links, pending totals, metric rates, competition units/current values/gaps and duplicated identifiers are checked before seed writes. `dataset_manifest.json` records file hashes and scope.

`agent_performance_metrics.metric_metadata` stores business labels, units, descriptions and origin with each performance period. Both the workbench API and Agent snapshot tool use it. `agent_assessments.unit` preserves assessment units. Migration `0009` only adds these nullable fields; older rows keep their values and their legacy read fallback until reseeded.

Premium cannot offset an FYC target just because both are HKD. New honour targets use `fyc`, not `protection_premium`. The `written_premium` alias is rejected for the life runtime. Pending policies use the stored pending-premium currency. Latest target periods sort first in the workbench.

## Reproduction and isolated verification

```powershell
python scripts/build_life_demo_dataset.py --output <temporary-folder>
python -m pytest tests/test_runtime_dataset_consistency.py tests/test_seed_initialization.py tests/test_m2_candidate_dataset.py tests/test_data_layer_tools.py tests/test_gap_analysis.py tests/test_chase_plan.py
```

The seed initialization test creates a disposable SQLite database, seeds twice and verifies all 50 login password hashes, roles, supervisors and idempotence. It does not write the configured shared database.

## Deployment order

1. Back up affected tables, including account hashes, targets and competition entries, outside Git. Do not publish backup contents or credentials.
2. Stop/restart services as a coordinated change so old code cannot silently interpret HKD as USD.
3. On the new code run `python -m alembic upgrade 0009`.
4. Run `python -m admin.seeds` twice. Existing passwords and administrator-edited planning configuration are preserved.
5. Review `python -m scripts.reconcile_runtime_dataset`. Dry-run is the default.
6. Apply only that reviewed plan with `python -m scripts.reconcile_runtime_dataset --apply --backup <verified-pre-update-backup.json>`.
7. Verify 50 active runtime users, current HKD metadata, 900 client links, 200 pending policies, 150 HKD assessments, five active new competitions and their 250 entries.

The reconciliation script deletes only targets that exactly match the old 50-agent seed's agent/period/metric/label/unit/value. It also removes old null-unit assessments only when subject, amounts, status and remark exactly match the archived seed. It preserves modified/custom targets, custom assessments and historical performance. It disables only the four known legacy demo usernames (`AGT001`, `AGT002`, `AGT003`, `AGT_TL01`), without deleting accounts or changing password hashes. New logins use the stable 50-agent IDs (for example `AGT00770`) and their existing credentials; no account is silently aliased to another identity.

No chat, knowledge document, embedding or model configuration is part of this reconciliation. Disable `BUILTIN_KNOWLEDGE_AUTO_SYNC` during unrelated startup acceptance so acceptance itself does not reindex knowledge.

## Rollback boundary

Keep the pre-update backup and the prior code commit. Restore the affected business records from the backup in a controlled transaction; do not blindly replace an entire shared database or remove unrelated new writes. Reenable any explicitly retired demo accounts only as part of that rollback. Migration `0009` supports downgrade to `0008` after the old code/data are restored. The raw source and M4 snapshot remain available independently of runtime rollback.
