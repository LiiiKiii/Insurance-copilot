"""Deterministic v4 human-only consensus; run only after stage-one review."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path
from statistics import fmean

DATASET = "m2-coursework-candidates-v4"
VERSION = "human-v4"
PROTOCOL = "m2-v4-consensus-v1"
ANNOTATORS = tuple(f"non_m4_annotator_{i}" for i in range(1, 4))
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/evaluation/m2_candidate_annotations_v4.json"
FREEZE_STATEMENT = (
    "The consensus protocol was frozen after the three independent blind annotations had "
    "been collected, but before their rankings were inspected or aggregated and before any "
    "M4 v4 evaluation was run."
)
READ_DISCLOSURE = (
    "Before protocol freeze, automated structural checks loaded ranking arrays to verify "
    "completion, uniqueness and candidate-set membership; an earlier Git diff also exposed "
    "part of annotator 2 input during submission. No joint ranking comparison or aggregation "
    "was performed. The freeze statement refers to substantive comparative inspection, "
    "not a claim that ranking arrays had never been accessed. No M4 evaluation was run "
    "by this consensus workflow; execution elsewhere has not been independently audited."
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(inputs):
    require(len(inputs) == 3, "Exactly three independent inputs required")
    by_annotator = {}
    reference = None
    for data in inputs:
        require(data.get("dataset_id") == DATASET, "Dataset mismatch")
        require(
            data.get("annotation_version") == VERSION, "Annotation version mismatch"
        )
        fp = data.get("data_fingerprint")
        require(
            isinstance(fp, str)
            and len(fp) == 64
            and all(c in "0123456789abcdef" for c in fp),
            "Invalid fingerprint",
        )
        scenarios = data.get("scenarios")
        require(
            isinstance(scenarios, list) and len(scenarios) == 10,
            "Ten completed scenarios required",
        )
        scene_map = {}
        identity = None
        for scene in scenarios:
            sid = scene.get("scenario_id")
            require(
                isinstance(sid, str) and sid and sid not in scene_map,
                "Duplicate or invalid scenario ID",
            )
            ids = scene.get("ranking_candidate_ids")
            require(
                isinstance(ids, list)
                and len(ids) in (3, 4)
                and all(isinstance(x, str) and x for x in ids)
                and len(set(ids)) == len(ids),
                "Expected three or four unique formal candidates",
            )
            eligible = scene.get("eligible_candidate_ids")
            require(
                isinstance(eligible, list)
                and all(isinstance(x, str) for x in eligible)
                and len(set(eligible)) == len(eligible)
                and set(ids) <= set(eligible),
                "Formal candidates must be a subset of eligible IDs",
            )
            slots = scene.get("annotations")
            require(
                isinstance(slots, list) and len(slots) == 1,
                "One independent annotator per source",
            )
            slot = slots[0]
            aid = slot.get("annotator_id")
            require(
                aid in ANNOTATORS and (identity is None or aid == identity),
                "Annotator identity mismatch",
            )
            identity = aid
            ranking = slot.get("ranking")
            require(slot.get("completed") is True, "Incomplete annotation")
            require(
                isinstance(ranking, list)
                and all(isinstance(x, str) for x in ranking)
                and len(ranking) == len(ids)
                and len(set(ranking)) == len(ids)
                and set(ranking) == set(ids),
                "Ranking must be an exact permutation of formal IDs",
            )
            require(
                not scene.get("consensus_relevance"),
                "Independent inputs must not contain consensus labels",
            )
            scene_map[sid] = scene
        require(identity not in by_annotator, "Duplicate annotator source")
        if reference is None:
            reference = (fp, scene_map)
        else:
            require(fp == reference[0], "Evidence fingerprint mismatch")
            require(set(scene_map) == set(reference[1]), "Scenario set mismatch")
            for sid, scene in scene_map.items():
                require(
                    scene["ranking_candidate_ids"]
                    == reference[1][sid]["ranking_candidate_ids"],
                    "Formal candidate lists differ",
                )
                require(
                    scene["eligible_candidate_ids"]
                    == reference[1][sid]["eligible_candidate_ids"],
                    "Eligible candidate lists differ",
                )
        by_annotator[identity] = scene_map
    require(
        set(by_annotator) == set(ANNOTATORS), "All three designated annotators required"
    )
    return by_annotator, reference[0]


def consensus(rankings):
    positions = [{cid: rank for rank, cid in enumerate(r, 1)} for r in rankings]
    sums = {cid: sum(p[cid] for p in positions) for cid in rankings[0]}
    result, ties = [], []
    for total in sorted(set(sums.values())):
        group = sorted(cid for cid in sums if sums[cid] == total)
        if len(group) == 1:
            result.extend(group)
            continue
        # Majority edges must be respected within a rank-sum tie. A majority
        # tournament can contain a Condorcet cycle: fail closed, never hide it.
        edges = {cid: set() for cid in group}
        pair_votes = []
        for a, b in combinations(group, 2):
            votes = sum(p[a] < p[b] for p in positions)
            winner, loser = (a, b) if votes >= 2 else (b, a)
            edges[winner].add(loser)
            pair_votes.append(
                {"a": a, "b": b, "votes_a_before_b": votes, "winner": winner}
            )
        remaining = set(group)
        ordered = []
        while remaining:
            available = sorted(
                cid
                for cid in remaining
                if not any(cid in edges[other] for other in remaining)
            )
            require(
                bool(available),
                "Majority cycle in tied rank sums: stop for protocol review; do not generate consensus",
            )
            # Lexicographic fallback if malformed/non-tournament extensions ever
            # leave multiple incomparable nodes; valid strict ballots have one.
            chosen = available[0]
            ordered.append(chosen)
            remaining.remove(chosen)
        result.extend(ordered)
        ties.append(
            {
                "rank_sum": total,
                "candidates": group,
                "pairwise_votes": pair_votes,
                "resolved_order": ordered,
            }
        )
    return result, sums, ties


def agreement(a, b):
    pa, pb = ({cid: i for i, cid in enumerate(r, 1)} for r in (a, b))
    n = len(a)
    concordant = sum(
        (pa[x] - pa[y]) * (pb[x] - pb[y]) > 0 for x, y in combinations(a, 2)
    )
    pairs = n * (n - 1) // 2
    overlap = len(set(a[:3]) & set(b[:3]))
    return {
        "kendall_tau_a": (2 * concordant - pairs) / pairs,
        "spearman_rho": 1
        - 6 * sum((pa[c] - pb[c]) ** 2 for c in a) / (n * (n * n - 1)),
        "top1_agreement": int(a[0] == b[0]),
        "top3_overlap_count": overlap,
        "top3_overlap": overlap / 3,
    }


def aggregate(inputs, sources):
    validated, fp = validate(inputs)
    require(
        set(sources) == set(ANNOTATORS), "Source provenance required for all annotators"
    )
    scenes, comparisons = [], []
    for sid in sorted(validated[ANNOTATORS[0]]):
        source = validated[ANNOTATORS[0]][sid]
        slots = [validated[aid][sid]["annotations"][0] for aid in ANNOTATORS]
        rankings = [slot["ranking"] for slot in slots]
        order, sums, ties = consensus(rankings)
        grades = list(range(len(order) - 1, -1, -1))
        local = []
        for i, j in combinations(range(3), 2):
            record = {
                "scenario_id": sid,
                "annotators": [ANNOTATORS[i], ANNOTATORS[j]],
                **agreement(rankings[i], rankings[j]),
            }
            local.append(record)
            comparisons.append(record)
        scenes.append(
            {
                "scenario_id": sid,
                "eligible_candidate_ids": source["eligible_candidate_ids"],
                "ranking_candidate_ids": source["ranking_candidate_ids"],
                "annotations": slots,
                "consensus_ranking": order,
                "rank_sums": sums,
                "tie_resolution": ties,
                "consensus_relevance": dict(zip(order, grades, strict=True)),
                "agreement": local,
            }
        )
    metrics = ("kendall_tau_a", "spearman_rho", "top1_agreement", "top3_overlap")
    summary = {
        "scenario_pair_count": len(comparisons),
        "overall_macro_mean": {k: fmean(r[k] for r in comparisons) for k in metrics},
        "per_annotator_pair": [],
    }
    for pair in combinations(ANNOTATORS, 2):
        records = [r for r in comparisons if r["annotators"] == list(pair)]
        summary["per_annotator_pair"].append(
            {
                "annotators": list(pair),
                "scenario_count": len(records),
                "macro_mean": {k: fmean(r[k] for r in records) for k in metrics},
            }
        )
    return {
        "dataset_id": DATASET,
        "annotation_version": VERSION,
        "data_fingerprint": fp,
        "annotation_status": "complete",
        "consensus_protocol": PROTOCOL,
        "annotators": list(ANNOTATORS),
        "aggregation_method": "Ascending sum of three one-based human ranks (Borda equivalent).",
        "tie_breaking_method": "Within equal rank sums: pairwise majority, then candidate_id ascending for incomparable nodes; majority cycles fail closed for protocol review.",
        "grading_policy": {
            "4": [3, 2, 1, 0],
            "3": [2, 1, 0],
            "precision_relevant_if": "relevance > 0",
            "ndcg": "full graded relevance",
            "excluded_candidates": "Never add non-formal IDs or pad to K=5.",
        },
        "agreement_summary": summary,
        "scenarios": scenes,
        "provenance": {
            "source_files": sources,
            "protocol_document": "docs/coursework/m2_v4_consensus_protocol.md",
            "freeze_statement": FREEZE_STATEMENT,
            "prior_access_disclosure": READ_DISCLOSURE,
            "no_model_inputs": "Only the three independent human input files are read; no M4 scores, baseline, v3 labels or evaluation results.",
            "limitations": [
                "Protocol fixed after collection, not preregistered before annotation.",
                "Synthetic small dataset; agreement is descriptive and does not establish external validity.",
                "Three-candidate Top-3 overlap is necessarily 1 and is uninformative.",
                "Majority cycles are possible even with valid strict ballots and require an explicit protocol revision before aggregation.",
            ],
        },
    }


def canonical_json_sha256(data):
    """Hash JSON meaning independently of line endings, indentation and key order."""
    canonical = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def write_consensus(paths, output):
    require(len(paths) == 3, "Exactly three source paths required")
    require(len({p.resolve() for p in paths}) == 3, "Independent source paths required")
    require(
        output.resolve() not in {p.resolve() for p in paths},
        "Never overwrite an independent source",
    )
    inputs, sources = [], {}
    for path in paths:
        raw = path.read_bytes()
        data = json.loads(raw)
        inputs.append(data)
        # Structural validation runs before this identity is trusted or output is written.
        aid = data["scenarios"][0]["annotations"][0]["annotator_id"]
        sources[aid] = {
            "filename": path.name,
            "canonical_json_sha256": canonical_json_sha256(data),
        }
    result = aggregate(inputs, sources)
    require(
        all(
            math.isfinite(r[k])
            for s in result["scenarios"]
            for r in s["agreement"]
            for k in ("kendall_tau_a", "spearman_rho")
        ),
        "Nonfinite agreement",
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Explicit stage-two operation; only after protocol review",
    )
    parser.add_argument(
        "--inputs",
        nargs=3,
        type=Path,
        default=[
            ROOT / f"data/evaluation/m2_candidate_annotations_v4_{aid}.json"
            for aid in ANNOTATORS
        ],
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.generate:
        parser.error(
            "No inputs were read. Stage two requires review and explicit --generate."
        )
    result = write_consensus(args.inputs, args.output)
    print(f"Wrote {len(result['scenarios'])} consensus scenarios to {args.output}")


if __name__ == "__main__":
    main()
