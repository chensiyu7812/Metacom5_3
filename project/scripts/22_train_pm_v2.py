#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from metacom_pm.config import load_config
from metacom_pm.pm_v2_audit import _regime_pass, audit_training_labels
from metacom_pm.pm_v2_contracts import ActionLabel, CompositeSpec, PMV2Split
from metacom_pm.pm_v2_data import load_states, validate_split_manifests
from metacom_pm.pm_v2_model import (
    PMV2Model,
    RISK_FIELDS,
    SelectionConfig,
    evaluate_policy,
    tune_selection_config,
)
from metacom_pm.io import iter_jsonl, sha256_file, write_json

ROOT = Path(__file__).resolve().parents[1]


def fixed_action_metrics(states, labels, action_id, config):
    label_map = {(label.state_id, label.action_id): label for label in labels}
    spec = config.composite_spec
    rows = []
    for state in states:
        if action_id not in state.allowed_actions:
            return None
        label = label_map.get((state.state_id, action_id))
        if label is None:
            return None
        quality = spec.score(label.response)
        risk = max(float(getattr(label.risk, name)) / 3.0 for name in RISK_FIELDS)
        rows.append(
            {
                "state_id": state.state_id,
                "quality": quality,
                "risk": risk,
                "cost": float(label.observed_input_tokens),
            }
        )
    if not rows:
        return None
    cost_scale = max(float(np.mean([label.observed_input_tokens for label in labels])), 1.0)
    mean_quality = float(np.mean([row["quality"] for row in rows]))
    mean_risk = float(np.mean([row["risk"] for row in rows]))
    mean_cost = float(np.mean([row["cost"] for row in rows]))
    utility = mean_quality - config.risk_weight * mean_risk - config.cost_weight * (mean_cost / cost_scale)
    return {
        "action_id": action_id,
        "n": len(rows),
        "mean_quality": mean_quality,
        "mean_risk": mean_risk,
        "mean_cost": mean_cost,
        "utility": float(utility),
    }


def policy_regime_alignment(model, states):
    by_regime = defaultdict(list)
    actions = []
    for state in states:
        decision = model.choose(state)
        action = decision.chosen_action
        actions.append(action)
        regime = str(state.provenance.get("regime") or "unknown")
        quality_values = sorted(
            (prediction.quality_mean, action_id)
            for action_id, prediction in decision.predictions.items()
        )
        quality_gap = (
            float(quality_values[-1][0] - quality_values[-2][0])
            if len(quality_values) > 1
            else 0.0
        )
        by_regime[regime].append(_regime_pass(regime, action, quality_gap))
    counts = Counter(actions)
    return {
        "action_distribution": dict(counts),
        "distinct_actions": len(counts),
        "maximum_action_share": max(counts.values(), default=0) / max(len(actions), 1),
        "regime_pass_rate": {
            regime: float(np.mean(values)) for regime, values in sorted(by_regime.items())
        },
        "mean_regime_pass_rate": float(
            np.mean([value for values in by_regime.values() for value in values])
        ) if by_regime else 0.0,
    }


def selection_from_file(config):
    quality = config["quality_composite"]
    composite = CompositeSpec(
        version=str(quality["version"]),
        weights={str(key): float(value) for key, value in quality["weights"].items()},
    )
    selection = dict(config["selection"])
    return SelectionConfig(**selection, composite_spec=composite)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pm-v2-config", type=Path, default=ROOT / "configs" / "pm_v2.yaml")
    parser.add_argument("--states", type=Path, default=ROOT / "data" / "pm_v2" / "pm_v2_states.jsonl")
    parser.add_argument("--labels", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "action_labels.jsonl")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "pm_v2_model")
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--minimum-calibration-quality", type=float)
    parser.add_argument("--allow-nonreportable", action="store_true")
    args = parser.parse_args()

    pm_config = load_config(args.pm_v2_config)
    if pm_config.get("version") != "pm-v2.0":
        raise ValueError("unsupported PM-v2 config version")
    model_cfg = pm_config["model"]
    feature_cfg = pm_config["features"]
    grid_cfg = pm_config["calibration_grid"]
    audit_cfg = pm_config["data_label_gate"]
    gate_cfg = pm_config["internal_reportability_gate"]
    initial_selection = selection_from_file(pm_config)

    states = load_states(args.states)
    labels = [ActionLabel.model_validate(row) for row in iter_jsonl(args.labels)]
    states_by_split = {
        split: [state for state in states if state.split is split]
        for split in (PMV2Split.TRAIN, PMV2Split.CALIBRATION, PMV2Split.INTERNAL_TEST)
    }
    if any(not rows for rows in states_by_split.values()):
        raise RuntimeError(
            "PM-v2 requires non-empty train, calibration, and internal-test splits"
        )
    split_manifest = validate_split_manifests(states_by_split)
    state_ids_by_split = {
        split: {state.state_id for state in rows}
        for split, rows in states_by_split.items()
    }
    labels_by_split = {
        split: [label for label in labels if label.state_id in state_ids]
        for split, state_ids in state_ids_by_split.items()
    }
    data_label_audit = audit_training_labels(
        states_by_split[PMV2Split.TRAIN] + states_by_split[PMV2Split.CALIBRATION],
        labels_by_split[PMV2Split.TRAIN] + labels_by_split[PMV2Split.CALIBRATION],
        maximum_single_action_share=float(audit_cfg["maximum_single_action_share"]),
        minimum_m0_share=float(audit_cfg["minimum_m0_share"]),
        minimum_r0_share=float(audit_cfg["minimum_r0_share"]),
        minimum_rs_share=float(audit_cfg["minimum_rs_share"]),
        minimum_distinct_actions=int(audit_cfg["minimum_distinct_actions"]),
        minimum_regime_pass_rate=float(audit_cfg["minimum_regime_pass_rate"]),
        minimum_reliable_rate=float(audit_cfg["minimum_reliable_rate"]),
    )
    model = PMV2Model.train(
        states_by_split[PMV2Split.TRAIN],
        labels_by_split[PMV2Split.TRAIN],
        selection_config=initial_selection,
        n_models=int(model_cfg["bootstrap_models"]),
        seed=args.seed,
        use_precomputed_embeddings=bool(
            feature_cfg["optional_precomputed_semantic_embedding"]
        ),
        word_features=int(feature_cfg["word_hash_features"]),
        char_features=int(feature_cfg["char_hash_features"]),
    )
    tuning = tune_selection_config(
        model,
        states_by_split[PMV2Split.CALIBRATION],
        labels_by_split[PMV2Split.CALIBRATION],
        cost_weights=[float(value) for value in grid_cfg["cost_weights"]],
        risk_weights=[float(value) for value in grid_cfg["risk_weights"]],
        resource_gains=[float(value) for value in grid_cfg["resource_gains"]],
        strategy_gains=[float(value) for value in grid_cfg["strategy_gains"]],
        max_risks=[float(value) for value in grid_cfg["max_risks"]],
        minimum_quality=args.minimum_calibration_quality,
    )
    calibration_pm = evaluate_policy(
        model,
        states_by_split[PMV2Split.CALIBRATION],
        labels_by_split[PMV2Split.CALIBRATION],
    )
    common_actions = sorted(
        set.intersection(
            *(set(state.allowed_actions) for state in states_by_split[PMV2Split.CALIBRATION])
        )
    )
    if not common_actions:
        raise RuntimeError("calibration split has no common fixed action")
    calibration_fixed = [
        fixed_action_metrics(
            states_by_split[PMV2Split.CALIBRATION],
            labels_by_split[PMV2Split.CALIBRATION],
            action_id,
            model.selection_config,
        )
        for action_id in common_actions
    ]
    calibration_fixed = [row for row in calibration_fixed if row is not None]
    cost_matched = min(
        calibration_fixed,
        key=lambda row: (
            abs(row["mean_cost"] - calibration_pm["mean_cost"]),
            row["mean_cost"],
            row["action_id"],
        ),
    )
    best_fixed = max(
        calibration_fixed,
        key=lambda row: (row["utility"], row["mean_quality"], -row["mean_cost"]),
    )
    internal = evaluate_policy(
        model,
        states_by_split[PMV2Split.INTERNAL_TEST],
        labels_by_split[PMV2Split.INTERNAL_TEST],
    )
    internal_cost_matched = fixed_action_metrics(
        states_by_split[PMV2Split.INTERNAL_TEST],
        labels_by_split[PMV2Split.INTERNAL_TEST],
        cost_matched["action_id"],
        model.selection_config,
    )
    internal_best_fixed = fixed_action_metrics(
        states_by_split[PMV2Split.INTERNAL_TEST],
        labels_by_split[PMV2Split.INTERNAL_TEST],
        best_fixed["action_id"],
        model.selection_config,
    )
    if internal_cost_matched is None or internal_best_fixed is None:
        raise RuntimeError("calibration-selected fixed action is not legal on internal test")
    internal_alignment = policy_regime_alignment(
        model, states_by_split[PMV2Split.INTERNAL_TEST]
    )
    quality_delta = internal["mean_quality"] - internal_cost_matched["mean_quality"]
    internal_cost_scale = max(
        float(
            np.mean(
                [
                    label.observed_input_tokens
                    for label in labels_by_split[PMV2Split.INTERNAL_TEST]
                ]
            )
        ),
        1.0,
    )
    internal_pm_utility = (
        internal["mean_quality"]
        - model.selection_config.risk_weight * internal["mean_risk"]
        - model.selection_config.cost_weight
        * (internal["mean_cost"] / internal_cost_scale)
    )
    utility_delta = internal_pm_utility - internal_cost_matched["utility"]
    reportability_checks = {
        "quality_vs_cost_matched": quality_delta
        >= float(gate_cfg["minimum_quality_delta_vs_cost_matched"]),
        "utility_vs_cost_matched": utility_delta
        >= float(gate_cfg["minimum_utility_delta_vs_cost_matched"]),
        "distinct_actions": internal_alignment["distinct_actions"]
        >= int(gate_cfg["minimum_distinct_actions"]),
        "m0_rate": internal["m0_rate"] >= float(gate_cfg["minimum_m0_rate"]),
        "r0_rate": internal["r0_rate"] >= float(gate_cfg["minimum_r0_rate"]),
        "regime_alignment": internal_alignment["mean_regime_pass_rate"]
        >= float(gate_cfg["minimum_regime_pass_rate"]),
    }
    reportable = all(reportability_checks.values())

    args.out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.out_dir / "pm_v2.joblib"
    model.save(checkpoint)
    report = {
        "status": "COMPLETE" if reportable else "NONREPORTABLE",
        "format_version": model.format_version,
        "pm_v2_config": str(args.pm_v2_config),
        "pm_v2_config_sha256": sha256_file(args.pm_v2_config),
        "checkpoint": str(checkpoint),
        "training": model.training_report,
        "split_manifest": split_manifest.model_dump(mode="json"),
        "data_label_audit": {key: value for key, value in data_label_audit.items() if key != "rows"},
        "calibration": tuning,
        "calibration_pm": {key: value for key, value in calibration_pm.items() if key != "rows"},
        "calibration_cost_matched_fixed": cost_matched,
        "calibration_best_fixed": best_fixed,
        "internal_test": {key: value for key, value in internal.items() if key != "rows"},
        "internal_cost_matched_fixed": internal_cost_matched,
        "internal_best_fixed": internal_best_fixed,
        "internal_policy_regime_alignment": internal_alignment,
        "internal_deltas_vs_cost_matched": {
            "quality": float(quality_delta),
            "utility": float(utility_delta),
        },
        "reportability_thresholds": gate_cfg,
        "reportability_checks": reportability_checks,
        "selection_config": model.selection_config.model_dump(mode="json"),
        "selection_config_hash": model.selection_config.digest(),
    }
    write_json(args.out_dir / "training_report.json", report)
    print(report)
    if not reportable and not args.allow_nonreportable:
        raise RuntimeError(
            "PM-v2 failed the frozen internal reportability gate. "
            "Do not run external generation. See training_report.json."
        )


if __name__ == "__main__":
    main()
