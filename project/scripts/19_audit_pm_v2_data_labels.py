#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.io import iter_jsonl, write_json
from metacom_pm.pm_v2_audit import audit_training_labels
from metacom_pm.pm_v2_contracts import ActionLabel, PMV2Split
from metacom_pm.pm_v2_data import load_states

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, default=ROOT / "data" / "pm_v2" / "pm_v2_states.jsonl")
    parser.add_argument("--labels", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "action_labels.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "data_label_audit.json")
    parser.add_argument(
        "--splits",
        nargs="+",
        default=[PMV2Split.TRAIN.value, PMV2Split.CALIBRATION.value],
    )
    args = parser.parse_args()

    selected_splits = {PMV2Split(value) for value in args.splits}
    states = [state for state in load_states(args.states) if state.split in selected_splits]
    state_ids = {state.state_id for state in states}
    labels = [
        ActionLabel.model_validate(row)
        for row in iter_jsonl(args.labels)
        if str(row.get("state_id")) in state_ids
    ]
    report = audit_training_labels(states, labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, report)
    print({key: value for key, value in report.items() if key != "rows"})


if __name__ == "__main__":
    main()
