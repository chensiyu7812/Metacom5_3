#!/usr/bin/env python3
"""Seal and attest the PM-v1.5 dual-domain training inputs without API calls.

The script validates train/calibration labels structurally, but it never
deserializes internal-test ``ActionLabel`` values.  Internal files are opened
only by ``seal_internal_label_bundle``, which records row/schema/state-universe
hashes before candidate fitting begins.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.artifacts import create_artifact_attestation
from metacom_pm.config import load_config
from metacom_pm.internal_holdout import seal_internal_label_bundle
from metacom_pm.io import (
    canonical_json,
    iter_jsonl,
    read_json,
    sha256_file,
    sha256_text,
    write_json,
)
from metacom_pm.pm_v2_contracts import ActionLabel, PMV2Split
from metacom_pm.pm_v2_data import load_states
from metacom_pm.v1_5_dual_domain_training import (
    DUAL_DOMAIN_TRAINING_PROTOCOL,
    validate_dual_domain_training_inputs,
)


ROOT = Path(__file__).resolve().parents[2]


def _state_universe_sha256(states) -> str:
    return sha256_text(canonical_json(sorted(state.state_id for state in states)))


def _require_internal_seal_matches_states(seal: dict, states, *, domain: str) -> None:
    internal_states = [
        state for state in states if state.split is PMV2Split.INTERNAL_TEST
    ]
    expected_rows = sum(len(state.allowed_actions) for state in internal_states)
    if int(seal.get("state_count") or 0) != len(internal_states):
        raise RuntimeError(f"{domain} internal seal state count mismatch")
    if int(seal.get("row_count") or 0) != expected_rows:
        raise RuntimeError(f"{domain} internal seal action-matrix row count mismatch")
    if seal.get("state_universe_sha256") != _state_universe_sha256(internal_states):
        raise RuntimeError(f"{domain} internal seal state universe mismatch")


def _require_auxiliary_build_report(report_path: Path, auxiliary_dir: Path) -> dict:
    report = read_json(report_path)
    if (
        report.get("protocol")
        != "pm-v1.5-esconv-auxiliary-bank-disjoint-seed-training-support-v1"
        or report.get("status") != "COMPLETE"
        or report.get("bank_disjoint") is not True
        or int(report.get("strategy_bank_source_dialogue_overlap_count") or -1) != 0
    ):
        raise RuntimeError("ESConv auxiliary build report is absent or invalid")
    for split in ("train", "calibration", "internal_test"):
        state_path = auxiliary_dir / split / "pm_v2_states.jsonl"
        record = (((report.get("outputs") or {}).get(split) or {}).get("pm_v2_states") or {})
        if record.get("sha256") != sha256_file(state_path):
            raise RuntimeError(
                f"ESConv auxiliary build report state hash mismatch for {split}"
            )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pm-v1-5-config",
        type=Path,
        default=ROOT / "configs" / "pm_v1_5.yaml",
    )
    parser.add_argument(
        "--longitudinal-states",
        type=Path,
        default=ROOT / "data" / "pm_v1_5" / "pm_v2_states.jsonl",
    )
    parser.add_argument("--longitudinal-train-calibration-labels", type=Path, required=True)
    parser.add_argument("--longitudinal-internal-test-labels", type=Path, required=True)
    parser.add_argument(
        "--auxiliary-dir",
        type=Path,
        default=ROOT / "data" / "esconv_auxiliary_v1_5",
    )
    parser.add_argument("--auxiliary-train-labels", type=Path, required=True)
    parser.add_argument("--auxiliary-calibration-labels", type=Path, required=True)
    parser.add_argument("--auxiliary-internal-test-labels", type=Path, required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "outputs" / "pm_v1_5_dual_domain_training_preflight",
    )
    args = parser.parse_args()

    config = load_config(args.pm_v1_5_config)
    if config.get("version") != "pm-v1.5":
        raise RuntimeError("dual-domain preflight requires pm-v1.5")
    auxiliary_build_report_path = args.auxiliary_dir / "build_report.json"
    auxiliary_build_report = _require_auxiliary_build_report(
        auxiliary_build_report_path, args.auxiliary_dir
    )
    longitudinal_states = load_states(args.longitudinal_states)
    auxiliary_state_paths = {
        split: args.auxiliary_dir / split / "pm_v2_states.jsonl"
        for split in ("train", "calibration", "internal_test")
    }
    auxiliary_states = [
        state
        for split in ("train", "calibration", "internal_test")
        for state in load_states(auxiliary_state_paths[split])
    ]
    longitudinal_labels = [
        ActionLabel.model_validate(row)
        for row in iter_jsonl(args.longitudinal_train_calibration_labels)
    ]
    auxiliary_label_paths = {
        "train": args.auxiliary_train_labels,
        "calibration": args.auxiliary_calibration_labels,
    }
    auxiliary_labels = [
        ActionLabel.model_validate(row)
        for split in ("train", "calibration")
        for row in iter_jsonl(auxiliary_label_paths[split])
    ]
    validated = validate_dual_domain_training_inputs(
        longitudinal_states=longitudinal_states,
        auxiliary_states=auxiliary_states,
        longitudinal_train_calibration_labels=longitudinal_labels,
        auxiliary_train_calibration_labels=auxiliary_labels,
        pm_config=config,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    longitudinal_seal_path = args.out_dir / "sealed_internal_longitudinal.json"
    auxiliary_seal_path = args.out_dir / "sealed_internal_esconv_auxiliary.json"
    longitudinal_seal = seal_internal_label_bundle(
        longitudinal_seal_path,
        internal_labels_path=args.longitudinal_internal_test_labels,
    )
    auxiliary_seal = seal_internal_label_bundle(
        auxiliary_seal_path,
        internal_labels_path=args.auxiliary_internal_test_labels,
    )
    _require_internal_seal_matches_states(
        longitudinal_seal, longitudinal_states, domain="longitudinal_synthetic"
    )
    _require_internal_seal_matches_states(
        auxiliary_seal, auxiliary_states, domain="esconv_auxiliary"
    )

    report_path = args.out_dir / "dual_domain_training_preflight.json"
    report = {
        **validated.report,
        "protocol": DUAL_DOMAIN_TRAINING_PROTOCOL,
        "status": "PASS",
        "pm_v1_5_config_sha256": sha256_file(args.pm_v1_5_config),
        "auxiliary_build_report_sha256": sha256_file(
            auxiliary_build_report_path
        ),
        "auxiliary_build_report_status": auxiliary_build_report["status"],
        "sealed_internal_bundles": {
            "longitudinal_synthetic": longitudinal_seal,
            "esconv_auxiliary": auxiliary_seal,
        },
        "internal_label_values_deserialized": False,
    }
    write_json(report_path, report)
    attestation_path = args.out_dir / "artifact_attestation.json"
    create_artifact_attestation(
        attestation_path,
        stage="pm_v1_5_dual_domain_training_preflight",
        inputs={
            "pm_v1_5_config": args.pm_v1_5_config,
            "longitudinal_states": args.longitudinal_states,
            "longitudinal_train_calibration_labels": (
                args.longitudinal_train_calibration_labels
            ),
            "longitudinal_internal_test_labels": args.longitudinal_internal_test_labels,
            "auxiliary_build_report": auxiliary_build_report_path,
            **{
                f"auxiliary_{split}_states": path
                for split, path in auxiliary_state_paths.items()
            },
            **{
                f"auxiliary_{split}_labels": path
                for split, path in {
                    **auxiliary_label_paths,
                    "internal_test": args.auxiliary_internal_test_labels,
                }.items()
            },
        },
        outputs={
            "report": (report_path, False),
            "sealed_internal_longitudinal": (longitudinal_seal_path, False),
            "sealed_internal_esconv_auxiliary": (auxiliary_seal_path, False),
        },
        parameters={
            "protocol": DUAL_DOMAIN_TRAINING_PROTOCOL,
            "top_level_domain_weight": validated.report[
                "top_level_domain_weight"
            ],
            "internal_label_values_deserialized": False,
        },
    )
    print(
        canonical_json(
            {
                "status": "PASS",
                "report": str(report_path),
                "attestation": str(attestation_path),
            }
        )
    )


if __name__ == "__main__":
    main()
