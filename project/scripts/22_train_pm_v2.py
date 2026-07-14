#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.io import iter_jsonl, write_json
from metacom_pm.pm_v2_contracts import ActionLabel, PMV2Split
from metacom_pm.pm_v2_data import load_states, validate_split_manifests
from metacom_pm.pm_v2_model import (
    PMV2Model,
    SelectionConfig,
    evaluate_policy,
    tune_selection_config,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, default=ROOT / "data" / "pm_v2" / "pm_v2_states.jsonl")
    parser.add_argument("--labels", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "action_labels.jsonl")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "pm_v2_model")
    parser.add_argument("--n-models", type=int, default=7)
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--minimum-calibration-quality", type=float)
    args = parser.parse_args()

    states = load_states(args.states)
    labels = [ActionLabel.model_validate(row) for row in iter_jsonl(args.labels)]
    states_by_split = {
        split: [state for state in states if state.split is split]
        for split in (PMV2Split.TRAIN, PMV2Split.CALIBRATION, PMV2Split.INTERNAL_TEST)
    }
    split_manifest = validate_split_manifests(states_by_split)
    state_ids_by_split = {
        split: {state.state_id for state in rows}
        for split, rows in states_by_split.items()
    }
    labels_by_split = {
        split: [label for label in labels if label.state_id in state_ids]
        for split, state_ids in state_ids_by_split.items()
    }
    model = PMV2Model.train(
        states_by_split[PMV2Split.TRAIN],
        labels_by_split[PMV2Split.TRAIN],
        selection_config=SelectionConfig(),
        n_models=args.n_models,
        seed=args.seed,
    )
    tuning = tune_selection_config(
        model,
        states_by_split[PMV2Split.CALIBRATION],
        labels_by_split[PMV2Split.CALIBRATION],
        minimum_quality=args.minimum_calibration_quality,
    )
    internal = evaluate_policy(
        model,
        states_by_split[PMV2Split.INTERNAL_TEST],
        labels_by_split[PMV2Split.INTERNAL_TEST],
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.out_dir / "pm_v2.joblib"
    model.save(checkpoint)
    report = {
        "status": "COMPLETE",
        "format_version": model.format_version,
        "checkpoint": str(checkpoint),
        "training": model.training_report,
        "split_manifest": split_manifest.model_dump(mode="json"),
        "calibration": tuning,
        "internal_test": {key: value for key, value in internal.items() if key != "rows"},
        "selection_config": model.selection_config.model_dump(mode="json"),
        "selection_config_hash": model.selection_config.digest(),
    }
    write_json(args.out_dir / "training_report.json", report)
    print(report)


if __name__ == "__main__":
    main()
