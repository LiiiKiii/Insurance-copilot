"""Run the reproducible M4 ranking comparison on a labelled JSON fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.insurance.planning_layer.evaluation import (
    evaluate_ranking,
    expected_contribution_baseline,
)
from nanobot.agent.tools.insurance.planning_layer.prioritization import (
    prioritize_followups,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = PROJECT_ROOT / "data" / "evaluation" / "prioritization_synthetic.json"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture",
        nargs="?",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to a labelled prioritisation fixture.",
    )
    args = parser.parse_args()
    print(json.dumps(run(args.fixture), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
