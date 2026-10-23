"""Run reproducible synthetic or multi-scenario M4 ranking evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.insurance.planning_layer.evaluation import (
    evaluate_ranking,
    expected_contribution_baseline,
)
from nanobot.agent.tools.insurance.planning_layer.experiment import (
    evaluate_coursework_dataset,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    prioritize_followups,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = PROJECT_ROOT / "data" / "evaluation" / "prioritization_synthetic.json"
DEFAULT_SCENARIOS = PROJECT_ROOT / "data" / "evaluation" / "m2_candidate_scenarios.json"
DEFAULT_ANNOTATIONS = (
    PROJECT_ROOT / "data" / "evaluation" / "m2_candidate_annotations_v3.json"
)


def run(fixture_path: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    ranking = prioritize_followups({
        key: fixture[key]
        for key in ("agent_id", "objective", "constraints", "candidates")
    })
    proposed = [row["candidate_id"] for row in ranking["recommendations"]]
    baseline = expected_contribution_baseline(fixture["candidates"], proposed)
    return {
        "dataset_id": fixture.get("dataset_id"),
        "dataset_notice": fixture.get("description"),
        "proposed_ranking": proposed,
        "baseline_ranking": baseline,
        "metrics": evaluate_ranking(
            proposed,
            baseline,
            fixture["relevance"],
            fixture["evaluation_k"],
        ),
    }


def run_coursework(scenarios_path: Path, annotations_path: Path) -> dict[str, Any]:
    """Load and evaluate the complete labelled M2 coursework dataset."""
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    annotations = json.loads(annotations_path.read_text(encoding="utf-8"))
    return evaluate_coursework_dataset(scenarios, annotations)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture",
        nargs="?",
        type=Path,
        help=(
            "Optional legacy single-fixture path. Supplying it preserves the "
            "original command-line behaviour."
        ),
    )
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=DEFAULT_SCENARIOS,
        help="Path to the complete M2 candidate scenarios.",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=DEFAULT_ANNOTATIONS,
        help="Path to the completed M2 consensus annotations.",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run the original single-fixture smoke experiment instead.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Also write the JSON result to this path.",
    )
    args = parser.parse_args()
    result = (
        run(args.fixture or DEFAULT_FIXTURE)
        if args.synthetic or args.fixture is not None
        else run_coursework(args.scenarios, args.annotations)
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
