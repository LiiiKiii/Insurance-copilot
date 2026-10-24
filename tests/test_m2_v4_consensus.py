"""Synthetic-only protocol tests; never load real v4 ballots or model results."""

import copy
import hashlib
import json
from itertools import permutations

import pytest

from scripts.aggregate_m2_annotations_v4 import (
    ANNOTATORS,
    DATASET,
    VERSION,
    aggregate,
    agreement,
    consensus,
    validate,
    write_consensus,
)


def fixtures():
    inputs = []
    for aid in ANNOTATORS:
        scenes = []
        for i in range(10):
            ids = [f"fictional-{i}-{c}" for c in ("abcd" if i % 2 else "abc")]
            scenes.append(
                {
                    "scenario_id": f"synthetic-{i:02}",
                    "ranking_candidate_ids": ids,
                    "eligible_candidate_ids": ids + [f"fictional-outside-{i}"],
                    "annotations": [
                        {
                            "annotator_id": aid,
                            "ranking": ids[:],
                            "completed": True,
                            "notes": "synthetic",
                        }
                    ],
                    "consensus_relevance": {},
                }
            )
        inputs.append(
            {
                "dataset_id": DATASET,
                "annotation_version": VERSION,
                "data_fingerprint": "a" * 64,
                "scenarios": scenes,
            }
        )
    return inputs


def sources():
    return {aid: {"filename": f"{aid}.json", "sha256": "b" * 64} for aid in ANNOTATORS}


def test_synthetic_aggregation_grades_and_thirty_comparisons():
    result = aggregate(fixtures(), sources())
    assert result["annotation_status"] == "complete"
    assert result["agreement_summary"]["scenario_pair_count"] == 30
    assert len(result["scenarios"]) == 10
    for scene in result["scenarios"]:
        n = len(scene["ranking_candidate_ids"])
        assert list(scene["consensus_relevance"].values()) == list(range(n - 1, -1, -1))
        assert set(scene["consensus_relevance"]) == set(scene["ranking_candidate_ids"])
        assert len(scene["agreement"]) == 3
    assert aggregate(fixtures()[::-1], sources()) == result
    assert result["agreement_summary"]["overall_macro_mean"] == dict.fromkeys(
        ("kendall_tau_a", "spearman_rho", "top1_agreement", "top3_overlap"), 1
    )


def test_rank_sum_tie_majority():
    order, sums, ties = consensus([list("abcd"), list("dabc"), list("bcad")])
    assert sums["a"] == sums["b"] == 6
    assert order == list("abcd")
    assert ties[0]["pairwise_votes"][0]["votes_a_before_b"] == 2


def test_valid_majority_cycle_fails_closed():
    with pytest.raises(ValueError, match="Majority cycle"):
        consensus([list("abc"), list("bca"), list("cab")])


def test_agreement_known_values():
    stats = agreement(list("abcd"), list("dcba"))
    assert stats == {
        "kendall_tau_a": -1,
        "spearman_rho": -1,
        "top1_agreement": 0,
        "top3_overlap_count": 2,
        "top3_overlap": 2 / 3,
    }
    assert agreement(list("abc"), list("cba"))["top3_overlap"] == 1
    for ranking in permutations("abcd"):
        forward = agreement(list("abcd"), list(ranking))
        assert forward == agreement(list(ranking), list("abcd"))
        assert -1 <= forward["kendall_tau_a"] <= 1
        assert -1 <= forward["spearman_rho"] <= 1


@pytest.mark.parametrize(
    "mutation",
    [
        "dataset",
        "version",
        "fingerprint",
        "missing_scene",
        "scene_id",
        "formal_ids",
        "duplicate_rank",
        "missing_rank",
        "extra_rank",
        "outside_rank",
        "incomplete",
        "identity",
        "duplicate_source",
        "consensus",
    ],
)
def test_invalid_sources_rejected(mutation):
    data = fixtures()
    target = data[1]
    scene = target["scenarios"][0]
    slot = scene["annotations"][0]
    if mutation == "dataset":
        target["dataset_id"] = "other"
    elif mutation == "version":
        target["annotation_version"] = "other"
    elif mutation == "fingerprint":
        target["data_fingerprint"] = "c" * 64
    elif mutation == "missing_scene":
        target["scenarios"].pop()
    elif mutation == "scene_id":
        scene["scenario_id"] = "wrong"
    elif mutation == "formal_ids":
        scene["ranking_candidate_ids"] = scene["ranking_candidate_ids"][::-1]
    elif mutation == "duplicate_rank":
        slot["ranking"][0] = slot["ranking"][1]
    elif mutation == "missing_rank":
        slot["ranking"].pop()
    elif mutation == "extra_rank":
        slot["ranking"].append("unexpected")
    elif mutation == "outside_rank":
        slot["ranking"][0] = scene["eligible_candidate_ids"][-1]
    elif mutation == "incomplete":
        slot["completed"] = False
    elif mutation == "identity":
        slot["annotator_id"] = "other"
    elif mutation == "duplicate_source":
        data[1] = copy.deepcopy(data[0])
    elif mutation == "consensus":
        scene["consensus_relevance"] = {"fictional": 1}
    with pytest.raises(ValueError):
        validate(data)


def test_reproducible_output_and_provenance(tmp_path):
    paths = []
    for aid, data in zip(ANNOTATORS, fixtures(), strict=True):
        path = tmp_path / f"{aid}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        paths.append(path)
    before = [p.read_bytes() for p in paths]
    output = tmp_path / "master.json"
    result = write_consensus(paths, output)
    first = output.read_bytes()
    write_consensus(paths[::-1], output)
    assert output.read_bytes() == first
    assert [p.read_bytes() for p in paths] == before
    for aid, raw in zip(ANNOTATORS, before, strict=True):
        assert (
            result["provenance"]["source_files"][aid]["sha256"]
            == hashlib.sha256(raw).hexdigest()
        )
    with pytest.raises(ValueError, match="overwrite"):
        write_consensus(paths, paths[0])
    bad = json.loads(paths[0].read_text())
    bad["scenarios"][0]["annotations"][0]["completed"] = False
    paths[0].write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        write_consensus(paths, output)
    assert output.read_bytes() == first


def test_cli_does_not_read_inputs_without_explicit_generation(monkeypatch):
    from scripts.aggregate_m2_annotations_v4 import main

    monkeypatch.setattr(
        "sys.argv", ["aggregate", "--inputs", "missing-a", "missing-b", "missing-c"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_cycle_failure_preserves_existing_master(tmp_path):
    data = fixtures()
    ids = data[0]["scenarios"][0]["ranking_candidate_ids"]
    for index, item in enumerate(data):
        item["scenarios"][0]["annotations"][0]["ranking"] = ids[index:] + ids[:index]
    paths = []
    for aid, item in zip(ANNOTATORS, data, strict=True):
        path = tmp_path / f"{aid}.json"
        path.write_text(json.dumps(item))
        paths.append(path)
    output = tmp_path / "master.json"
    output.write_text("existing pending master")
    before = output.read_bytes()
    with pytest.raises(ValueError, match="Majority cycle"):
        write_consensus(paths, output)
    assert output.read_bytes() == before
    assert not output.with_suffix(".json.tmp").exists()


def test_majority_cannot_override_different_rank_sums():
    rankings = [list("abcd"), list("abcd"), list("bcda")]
    order, sums, _ = consensus(rankings)
    assert sums["b"] < sums["a"]
    assert order.index("b") < order.index("a")
