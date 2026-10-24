import json
from datetime import date, timedelta

import pytest

from scripts import build_m2_candidate_dataset as v3
from scripts import build_m2_candidate_dataset_v4 as v4
from scripts.annotate_m2_candidates_v4 import save, state


@pytest.fixture
def data():
    return v4.build_dataset()


def test_original_population_and_gates_preserved(data):
    old = v3.build_dataset()
    assert len(data["scenarios"]) == 10
    for current, previous in zip(data["scenarios"], old["scenarios"], strict=True):
        assert [r["candidate_id"] for r in current["candidates"]] == [
            r["candidate_id"] for r in previous["candidates"]
        ]
        assert [v4.gates(r) for r in current["candidates"]] == [
            v4.gates(r) for r in previous["candidates"]
        ]
        assert len(current["candidates"]) == 10
    assert (
        sum(
            r["horizon_ranking_eligible"]
            for s in data["scenarios"]
            for r in s["candidates"]
        )
        == 37
    )


def test_horizon_money_and_provenance(data):
    groups = set()
    for s in data["scenarios"]:
        o = s["objective"]
        start, end = map(
            date.fromisoformat, (o["planning_horizon_start"], o["planning_horizon_end"])
        )
        assert (end - start).days == 29
        assert o["business_timezone"] == "Asia/Hong_Kong"
        assert o["horizon_current"] == 0
        assert o["horizon_open_gap"] == o["horizon_target"] > 0
        assert "open_gap" not in o
        assert o["horizon_target_source"] and o["horizon_current_source"]
        for r in s["candidates"]:
            groups.add(r["realization_group"])
            assert r["expected_realization_source"]
            if not r["within_planning_horizon"]:
                assert r["expected_contribution"] == 0
                assert r["out_of_horizon_reason"]
    assert len(groups) >= 4


def test_inclusive_dates():
    start, end = date(2026, 6, 1), date(2026, 6, 30)
    assert v4.within_horizon(start, start, end)
    assert v4.within_horizon(end, start, end)
    assert not v4.within_horizon(start - timedelta(days=1), start, end)
    assert not v4.within_horizon(end + timedelta(days=1), start, end)
    assert not v4.within_horizon(None, start, end)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "HKD"),
        ("metric", "fyc"),
        ("horizon_open_gap", 0),
        ("horizon_target", float("nan")),
    ],
)
def test_invalid_objective_rejected(data, field, value):
    data["scenarios"][0]["objective"][field] = value
    with pytest.raises((ValueError, KeyError)):
        v4.validate(data)


def test_blind_no_model_or_consensus_fields(data):
    blind = v4.build_blind(data)
    forbidden = {
        "expected_contribution",
        "probability",
        "urgency",
        "actionability",
        "business_fit",
        "consensus_relevance",
    }

    def check(obj):
        if isinstance(obj, dict):
            assert not forbidden.intersection(obj)
            for value in obj.values():
                check(value)
        elif isinstance(obj, list):
            for value in obj:
                check(value)

    check(blind)
    annotations = v4.annotation_template(data)
    assert annotations["annotation_status"] == "pending"
    assert all(
        len(s["annotations"]) == 3 and not s["consensus_relevance"]
        for s in annotations["scenarios"]
    )
    assert all(
        not a["ranking"] for s in annotations["scenarios"] for a in s["annotations"]
    )


def test_annotator_isolation_and_exact_permutation(data):
    annotations = v4.annotation_template(data)
    scene = annotations["scenarios"][0]
    ranking = scene["ranking_candidate_ids"][::-1]
    save(
        annotations,
        v4.ANNOTATORS[0],
        scene["scenario_id"],
        ranking,
        "Independent notes",
    )
    own = state(v4.build_blind(data), annotations, v4.ANNOTATORS[0])
    other = state(v4.build_blind(data), annotations, v4.ANNOTATORS[1])
    assert own["saved"][scene["scenario_id"]] == ranking
    assert other["saved"][scene["scenario_id"]] == []
    assert other["notes"][scene["scenario_id"]] == ""
    for invalid in [
        ranking[:-1],
        ranking + ranking[:1],
        ["unknown"] * len(ranking),
        scene["eligible_candidate_ids"],
    ]:
        if invalid != ranking and set(invalid) != set(ranking):
            with pytest.raises(ValueError):
                save(annotations, v4.ANNOTATORS[0], scene["scenario_id"], invalid, "")
    assert annotations["annotation_status"] == "pending"
    assert not scene["consensus_relevance"]


def test_regeneration_preserves_human_work_and_rejects_stale(tmp_path):
    v4.write(tmp_path)
    path = tmp_path / "m2_candidate_annotations_v4_non_m4_annotator_1.json"
    annotations = json.loads(path.read_text())
    scene = annotations["scenarios"][0]
    save(
        annotations,
        v4.ANNOTATORS[0],
        scene["scenario_id"],
        scene["ranking_candidate_ids"],
        "Human input",
    )
    path.write_text(json.dumps(annotations))
    before = path.read_bytes()
    v4.write(tmp_path)
    assert path.read_bytes() == before
    annotations["data_fingerprint"] = "stale"
    path.write_text(json.dumps(annotations))
    machine = tmp_path / "m2_candidate_scenarios_v4.json"
    before = machine.read_bytes()
    with pytest.raises(ValueError, match="different evidence"):
        v4.write(tmp_path)
    assert machine.read_bytes() == before


def test_http_annotation_roundtrip(tmp_path):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen

    from scripts.annotate_m2_candidates_v4 import handler

    v4.write(tmp_path)
    annotation = tmp_path / "m2_candidate_annotations_v4_non_m4_annotator_1.json"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        handler(tmp_path / "m2_candidate_blind_v4.json", annotation, v4.ANNOTATORS[0]),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/state") as response:
            current = json.load(response)
        scene = current["scenarios"][0]
        payload = {
            "scenario_id": scene["scenario_id"],
            "ranking": scene["formal_ranking_candidate_ids"][::-1],
            "notes": "Independent HTTP input",
        }
        request = Request(
            base + "/api/save",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            assert response.status == 200
        with urlopen(base + "/api/state") as response:
            saved = json.load(response)
        assert saved["saved"][scene["scenario_id"]] == payload["ranking"]
        assert saved["notes"][scene["scenario_id"]] == payload["notes"]
        assert json.loads(annotation.read_text())["annotation_status"] == "pending"
        with urlopen(base) as response:
            assert b"Target and current provenance" in response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_rule_hash_and_full_fingerprint_ignore_json_formatting(tmp_path, monkeypatch):
    rules = json.loads(v4.RULES.read_text(encoding="utf-8"))
    original = v4.build_dataset()
    path = tmp_path / "data/config/m2_horizon_v4_rules.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(
        json.dumps(rules, ensure_ascii=True, sort_keys=True, indent=4)
        .replace("\n", "\r\n")
        .encode("utf-8")
    )
    monkeypatch.setattr(v4, "RULES", path)
    monkeypatch.setattr(v4, "ROOT", tmp_path)
    rebuilt = v4.build_dataset()
    assert rebuilt == original
    assert v4.fingerprint(rebuilt) == v4.fingerprint(original)
    rules["horizon_calendar_days"] = 31
    assert v4.canonical_rules_sha256(rules) != original["rules_sha256"]


def test_invalid_rules_hash_rejected(data):
    data["rules_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Rules canonical hash mismatch"):
        v4.validate(data)
