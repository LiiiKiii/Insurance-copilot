# M2 Horizon-Aligned candidates v4 handoff

Based on M1 contract `2a50a94` (`m1_horizon_aligned_gap_contract_v1.md`). This is an independent synthetic USD written-premium evaluation snapshot, not a replacement for the live HKD life demo. No database or application behavior changes are included. v3 files and labels remain unchanged.

## Objective and provenance

All ten scenarios use the inclusive 30-calendar-day window **2026-06-01 to 2026-06-30**, business timezone **Asia/Hong_Kong**, snapshot cutoff **2026-05-31 23:59:59 +08:00**. The annual gap is retained only as `annual_open_gap`; the formal denominator is `horizon_open_gap`.

`data/config/m2_horizon_v4_rules.json` records independently declared synthetic capacity plans: planned bound cases multiplied by planned average USD written premium. These are scenario assumptions, not verified business targets, ranker output, annual-gap prorating, or the illustrative numbers in M1's document. The future-window confirmed credit ledger is explicitly empty at the cutoff, so `horizon_current` is zero. Each objective carries target/current source objects and a synthetic flag. Zero/missing/nonfinite horizon gaps fail validation rather than falling back to annual gaps.

Candidate expected credit dates use explicitly recorded synthetic timeline rules and original source evidence. Action deadlines and credit dates are separate. Estimated contribution is premium times historical conversion probability (renewal uses retention), only for supported credit dates within the window. These estimates are uncertain, not booked revenue. Before-window, after-window, and unsupported dates receive zero horizon contribution and explicit reasons. No annual gap is divided by month.

## Population and evaluation implications

The same ten v3 scenarios and 100 raw candidates are retained with the original permission, eligibility and compliance gates. Sixty pass those original gates; **37 additionally have supported in-window credit estimates**. The other gate-eligible cards remain visible as separate evidence, including future follow-up. They are not silently promoted into this horizon's ranking. A source record is used once per scenario; scenes must not be summed as independent portfolio income.

M4 must adapt its v4 evaluator to the horizon denominator and formal candidate partition before producing v4 metrics. Some scenes have fewer than five formal candidates: do not pad Top-5 with future money or silently report an ordinary K=5 result. Explicitly report candidate counts and agree on unavailable-K handling. v3's six-position relevance mapping must not be transferred automatically to these variable-size v4 lists. Fresh human rankings and a documented v4 adjudication/graded-relevance policy are still required. No v4 consensus or evaluation result is claimed here.

## Files and blind annotation

- `data/evaluation/m2_candidate_scenarios_v4.json`: full machine input, including contribution assumptions and explicit partitions.
- `data/evaluation/m2_candidate_blind_v4.json`: evidence cards without model scores, conversion probabilities, expected-contribution scores or prior consensus.
- `data/evaluation/m2_candidate_annotations_v4.json`: pending master with three empty independent slots per scene and empty consensus.
- `data/evaluation/m2_candidate_annotations_v4_non_m4_annotator_1.json` (and 2/3): separate empty files for parallel blind work. Keep one file per annotator; the master is a later adjudication template, not an automatic synchronizer.

Run from the repository root, separately for each annotator:

```powershell
python -m scripts.annotate_m2_candidates_v4 --annotator non_m4_annotator_1
python -m scripts.annotate_m2_candidates_v4 --annotator non_m4_annotator_2
python -m scripts.annotate_m2_candidates_v4 --annotator non_m4_annotator_3
```

Local ports are 8771/8772/8773. Each annotator sees only their own saved rankings, independently shuffled initial cards, the exact horizon objective, and source assumptions. Rank all formal cards, record reasoning, and save each scene. Excluded evidence is read-only. Do not consult M4 scoring, v3 rankings, or other annotators. Saving does not generate consensus labels or mark the dataset complete. Collect the three independently completed files before adjudication.

Rebuild with `python -m scripts.build_m2_candidate_dataset_v4`. Existing annotation files are never overwritten. Fingerprints tie them to the exact evidence; a mismatch aborts before rewriting machine inputs. A changed evidence version requires a new dataset version and fresh annotation files.

## Rules-hash metadata repair (2026-10-24)

The original `rules_sha256` hashed raw file bytes before Git text normalization. Git history confirms the parsed rules have not changed since `02b00d5`; rebuilding against the frozen sources differs only in that hash. The field now hashes parsed JSON using `json.dumps(rules, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')`, with `rules_hash_method = sha256_canonical_json_utf8_v1`. It is a canonical content hash, not the raw file SHA-256. The builder validates it, and cross-platform formatting must produce the same dataset fingerprint.

Because the dataset fingerprint includes rule provenance, this metadata repair updates the fingerprint in the machine input, blind evidence, all three independent annotation files and consensus. The three ballots, notes, completion states, candidate evidence, rank sums, consensus order, tie resolution, relevance and agreement statistics are unchanged. Consensus source canonical hashes are regenerated to reflect only the annotation fingerprint change. No reannotation is needed; this is not a new business-data version.

M4's already committed result embeds the old source canonical hashes. M2 does not edit M4-owned output or rerun its evaluation here. M4 should refresh/revalidate its result provenance against the corrected sources; numerical results should remain identical. M1 should validate the canonical hash according to `rules_hash_method`, rather than compare against raw worktree bytes.
