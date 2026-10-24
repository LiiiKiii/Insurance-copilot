# M2 v4 consensus protocol v1 — stage-one freeze

Status: rules and implementation submitted for review **after three independent annotations were collected**, before joint comparative inspection or aggregation by this consensus workflow. Stage one does not create labels, modify annotations, or run M4 evaluation. Stage two requires human confirmation that the protocol and implementation have passed review.

## Scope and validation

Read only the three independent `m2_candidate_annotations_v4_non_m4_annotator_{1,2,3}.json` files. No M4 ranking, priority score, expected contribution, baseline, v3 consensus, Precision/NDCG result, or machine candidate file is an input. Use only each scene's `ranking_candidate_ids`; never add outside-window, unsupported-date, or other merely eligible candidates, including to fill K=5.

Require dataset `m2-coursework-candidates-v4`, annotation version `human-v4`, one identical 64-character evidence fingerprint, exactly ten distinct identical scenario IDs, identical ordered formal candidate lists per scene, identical eligible lists, and all three designated distinct annotator identities. Every source has one completed ballot per scene, an exact unique permutation of its formal IDs. Formal IDs must be a subset of eligible IDs. Reject missing, extra, duplicated, incomplete or mismatched input before writing anything. Only 3- and 4-candidate scenes are supported by this version.

## Aggregation and grades

1. Assign one-based positions to every candidate in each of the three ballots; sum the positions. Smaller sum ranks earlier (equivalent to Borda).
2. Within equal sums, compare candidates using the three ballots' pairwise majority. The candidate preferred by at least two annotators comes first.
3. Use candidate ID in ascending lexicographic order only when remaining candidates are incomparable. Valid strict three-ballot pairwise comparisons cannot tie.
4. **Review boundary:** a multi-candidate equal-sum group can have a Condorcet cycle even with fully valid ballots: `ABC`, `BCA`, `CAB`. No total order can respect every majority in this case. The script fails closed without writing a master file; it does not apply a nontransitive sort comparator or silently break a majority edge. A cycle requires an explicit reviewed protocol revision. This is a necessary edge-case clarification for stage-one review, not a rule inferred from real rankings.
5. Four candidates map consensus positions to `[3, 2, 1, 0]`; three map to `[2, 1, 0]`. Only formal IDs receive `consensus_relevance`. Precision treats relevance > 0 as relevant; NDCG uses full graded relevance. M4 final evaluation is K=1 and K=3; do not pad for K=5.

## Agreement statistics

For all ten scenarios and all three annotator pairs, store 30 scenario-pair records with identities:

- Kendall tau-a: `(concordant - discordant) / choose(n, 2)`; ballots have no ties.
- Spearman rho: `1 - 6 * sum(squared rank differences) / (n * (n^2 - 1))`.
- Top-1 agreement: 1 for identical first choice, otherwise 0.
- Top-3 overlap: intersection count divided by 3; retain the count too. For n=3 this is always 1 and is uninformative.

Store per-pair ten-scene macro means and overall 30-record macro means. Do not interpret these descriptive small-sample statistics as proof of validity.

## Output and provenance

Stage two writes only `data/evaluation/m2_candidate_annotations_v4.json`, with complete status, identities and original ballots, consensus order, rank sums, majority tie audit, grades, aggregation/tie/grading methods, dataset/version/fingerprint, all agreement records/summary, protocol version, source filenames and SHA-256 hashes, and limitations. Source files remain byte-for-byte unchanged. No timestamps or absolute machine-specific paths are inserted; identical source bytes produce identical output bytes regardless of input path order. Write atomically only after all validation, aggregation and statistics succeed; failure leaves the previous master unchanged.

Required provenance wording, qualified by the access disclosure below:

> The consensus protocol was frozen after the three independent blind annotations had been collected, but before their rankings were inspected or aggregated and before any M4 v4 evaluation was run.

**Access disclosure:** before freeze, automated structural checks loaded ranking arrays to check completion, uniqueness and set membership; an earlier submission-time Git diff also exposed part of annotator 2's ranking. No joint comparative inspection or aggregation was performed. Therefore “inspected” above means substantive comparative inspection; it must not be presented as a claim that no ranking data was ever accessed. This workflow has run no M4 v4 evaluation, but cannot independently certify activity by other team members. The generated provenance includes both the requested wording and these qualifications. This is not preregistration before annotation. Rules are fixed from the supplied instruction, not selected using observed agreement or evaluation outcomes.

## Two-stage execution

Stage one commits this document, `scripts/aggregate_m2_annotations_v4.py`, and synthetic-only tests. Merge into main for review. Do not run the script on real sources yet; do not change the pending master. No real annotation or model files are read by the tests.

After explicit review confirmation, stage two runs:

```powershell
python -m scripts.aggregate_m2_annotations_v4 --generate
```

Omitting `--generate` exits before reading any inputs. After validating the generated master and committing it through M2 into main, hand off to M4 to rerun final Precision@1/3, NDCG@1/3, baseline and sensitivity evaluation. Do not adjust labels or this protocol using those results. No new annotation is required for this protocol alone.
