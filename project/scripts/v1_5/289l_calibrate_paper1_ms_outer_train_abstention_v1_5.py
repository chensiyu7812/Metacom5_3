#!/usr/bin/env python3
"""Calibrate OUTER_TRAIN_ONLY ON/OFF/UNCERTAIN thresholds for MS from the
287l LOGO-OOF held-out probabilities, producing a HeadAbstentionThresholds-
compatible artifact for src/metacom_pm/v1_5_head_semantic_abstention.py.

Every probability in oof_predictions.jsonl was produced by a model that never
saw that row during training (LeaveOneGroupOut) -- this is the outer-train-
only signal the abstention compiler's docstring requires; there is no further
data to hold out beyond the LOGO-OOF itself at this sample size (127 rows).

Threshold rule (isotonic-calibrated, symmetric confidence band): fit a
monotonic isotonic regression mapping raw predicted probability -> empirical
P(suitable) on the 127 (probability, label) OOF pairs, then set on_min as the
smallest raw probability whose calibrated P(suitable) >= 0.75, and off_max as
the largest raw probability whose calibrated P(suitable) <= 0.25. This exact
0.25/0.75 confidence-band choice has no prior precedent in this project (no
earlier component's abstention thresholds were ever calibrated) -- it is a
new, explicit design choice made in this script, not a continuation of an
established convention, and is recorded as such for the user to revisit if a
different risk tolerance is wanted. Everything strictly between the two
thresholds compiles to UNCERTAIN_AS_OFF.

Zero API calls, zero generator calls -- a local calibration over already-
collected OOF predictions.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from sklearn.isotonic import IsotonicRegression


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_head_semantic_abstention import HeadAbstentionThresholds  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
OOF_REPORT = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_logo_oof_20260812/report.json"
OOF_PREDICTIONS = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_logo_oof_20260812/oof_predictions.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_outer_train_abstention_calibration_20260812"
TARGET_ON_CONFIDENCE = 0.75
TARGET_OFF_CONFIDENCE = 0.25


def main() -> None:
    if OUT.exists():
        raise RuntimeError("MS abstention calibration output exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "MS_HEAD_TRAINED_BA_0812_ABSTENTION_CALIBRATION_AND_EXECUTOR_QUALIFICATION_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("MS-head-trained phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    oof = read_json(OOF_REPORT)
    if oof["status"] != "MS_SOURCE_ANNOTATED_CONSENSUS_OOF_SIGNAL_PRESENT_FULL_FIT_MAY_BE_DESIGNED":
        raise RuntimeError("upstream OOF did not authorize downstream calibration")
    predictions = read_jsonl(OOF_PREDICTIONS)
    if len(predictions) != 127:
        raise RuntimeError("frozen MS abstention calibration denominator drifted")

    probability = np.asarray([row["primary_probability"] for row in predictions], dtype=float)
    label = np.asarray([row["consensus_label"] for row in predictions], dtype=int)

    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrated = calibrator.fit_transform(probability, label)

    order = np.argsort(probability)
    sorted_probability = probability[order]
    sorted_calibrated = calibrated[order]

    on_candidates = sorted_probability[sorted_calibrated >= TARGET_ON_CONFIDENCE]
    off_candidates = sorted_probability[sorted_calibrated <= TARGET_OFF_CONFIDENCE]
    if len(on_candidates) == 0 or len(off_candidates) == 0:
        raise RuntimeError("calibration curve does not reach both confidence targets at this sample size")
    on_min = float(on_candidates.min())
    off_max = float(off_candidates.max())
    if not (0.0 <= off_max < on_min <= 1.0):
        raise RuntimeError(f"calibrated thresholds are not well-ordered: off_max={off_max}, on_min={on_min}")

    decision = np.where(probability >= on_min, "ON", np.where(probability <= off_max, "OFF", "UNCERTAIN_AS_OFF"))
    counts = {value: int((decision == value).sum()) for value in ("ON", "OFF", "UNCERTAIN_AS_OFF")}
    on_precision = float(label[decision == "ON"].mean()) if counts["ON"] else None
    off_negative_rate = float(1 - label[decision == "OFF"].mean()) if counts["OFF"] else None
    uncertain_prevalence = float(label[decision == "UNCERTAIN_AS_OFF"].mean()) if counts["UNCERTAIN_AS_OFF"] else None

    report = {
        "protocol": "pm-v1.5-paper1-ms-outer-train-abstention-calibration-v1",
        "status": "MS_OUTER_TRAIN_ABSTENTION_THRESHOLDS_CALIBRATED",
        "component": "MS",
        "calibration_scope": "OUTER_TRAIN_ONLY",
        "calibration_method": "isotonic regression on LOGO-OOF held-out (probability, label) pairs; threshold = crossing point of a symmetric 0.25/0.75 calibrated-confidence band",
        "design_choice_not_a_precedent": "The 0.25/0.75 confidence-band target has no prior calibration precedent in this project (no other component has calibrated abstention thresholds yet); this is a new, explicit, revisitable choice made here.",
        "upstream_oof": {"path": str(OOF_REPORT.relative_to(ROOT)), "sha256": sha256_file(OOF_REPORT)},
        "n_predictions": len(predictions),
        "thresholds": {"off_max": off_max, "on_min": on_min},
        "target_confidence": {"on_min_calibrated_p_suitable_at_least": TARGET_ON_CONFIDENCE, "off_max_calibrated_p_suitable_at_most": TARGET_OFF_CONFIDENCE},
        "realized_confidence_on_oof": {
            "on_bucket": {"n": counts["ON"], "empirical_precision": on_precision},
            "off_bucket": {"n": counts["OFF"], "empirical_negative_rate": off_negative_rate},
            "uncertain_bucket": {"n": counts["UNCERTAIN_AS_OFF"], "empirical_positive_rate": uncertain_prevalence},
        },
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "generator_calls": 0,
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)

    # Validate that the produced thresholds actually satisfy the consuming
    # dataclass's own invariants before declaring success.
    calibration_artifact_sha256 = sha256_file(OUT / "report.json")
    thresholds = HeadAbstentionThresholds(
        component="MS",
        off_max=off_max,
        on_min=on_min,
        calibration_scope="OUTER_TRAIN_ONLY",
        calibration_artifact_sha256=calibration_artifact_sha256,
    )
    write_json(OUT / "ms_head_abstention_thresholds.json", {
        "component": thresholds.component,
        "off_max": thresholds.off_max,
        "on_min": thresholds.on_min,
        "calibration_scope": thresholds.calibration_scope,
        "calibration_artifact_sha256": calibration_artifact_sha256,
    })
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
