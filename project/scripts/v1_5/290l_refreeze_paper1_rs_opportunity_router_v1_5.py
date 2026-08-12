#!/usr/bin/env python3
"""Re-freeze the pre-Paper1 RS opportunity-router checkpoint under the current
bundle's contract, per plan Sec 12.4 stage 2 ("RS re-seals an executable
checkpoint under the current contract").

The checkpoint (outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1) was
fit 2026-08-01, before this Paper1 phase (2026-08-10) and its bundle-based
governance existed -- it was never bound into paper1_active_execution_bundle_v1.json.
This is not a retraining: it verifies the checkpoint and its Strategy Bank V4
input are byte-identical to what they were at fit time (i.e. the PASSED
result is still valid, nothing drifted underneath it), then binds it into the
current bundle's provenance chain. Zero API calls, zero new fit.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
RS_DIR = ROOT / "outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1"
FIT_REPORT = RS_DIR / "fit_report.json"
FREEZE_MANIFEST = RS_DIR / "freeze_manifest.json"
CHECKPOINT = RS_DIR / "rs_opportunity_router.joblib"
BANK = ROOT / "outputs/pm_v1_5_strategy_bank_v4_final_v1/strategy_cards_v4_final.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_opportunity_router_refreeze_20260812"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS refreeze output exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "MS_ABSTENTION_CALIBRATED_RS_REFREEZE_AND_EXECUTOR_ELIGIBILITY_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("MS-abstention-calibrated phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    fit_report = read_json(FIT_REPORT)
    freeze_manifest = read_json(FREEZE_MANIFEST)

    checks = {
        "fit_status_is_passed": fit_report["status"] == "BASIC_SAME_BANK_HUMAN_ALIGNED_RS_ROUTING_PASSED",
        "freeze_manifest_status_matches": freeze_manifest["status"] == fit_report["status"],
        "checkpoint_hash_unchanged_since_freeze": sha256_file(CHECKPOINT) == freeze_manifest["artifacts"]["rs_opportunity_router.joblib"],
        "fit_report_hash_unchanged_since_freeze": sha256_file(FIT_REPORT) == freeze_manifest["artifacts"]["fit_report.json"],
        "strategy_bank_v4_input_unchanged_since_fit": sha256_file(BANK) == fit_report["inputs"]["bank"]["sha256"],
        "same_bank_used_for_development_and_h2": fit_report["checks"]["same_80_card_bank_for_development_and_h2"] is True,
        "h2_dialogues_excluded_from_fit": fit_report["checks"]["h2_dialogues_excluded_from_fit"] is True,
        "formal_esconv_test_excluded_from_fit": fit_report["checks"]["formal_esconv_test_excluded_from_fit"] is True,
        "five_seed_prediction_agreement_is_1": fit_report["five_seed_h2_prediction_agreement"] == 1.0,
        "human_h2_transfer_balanced_accuracy_at_least_0_75": fit_report["transparent_same_bank_rule_on_h2"]["balanced_accuracy"] >= 0.75,
        "no_response_quality_risk_or_judge_outcome_read": fit_report["checks"]["no_response_quality_risk_or_judge_outcome_read"] is True,
    }
    all_pass = all(checks.values())

    report = {
        "protocol": "pm-v1.5-paper1-rs-opportunity-router-refreeze-v1",
        "status": "RS_REFROZEN_UNDER_CURRENT_CONTRACT_PASS" if all_pass else "RS_REFREEZE_FAIL_DRIFT_OR_REGRESSION_DETECTED",
        "conclusion": (
            "Not a retrain: the 2026-08-01 same-bank RS opportunity-router fit and its "
            "Strategy Bank V4 input are byte-identical to their original state, and the "
            "original PASSED result still holds under re-check. Bound into the current "
            "Paper1 bundle's provenance for the first time (it predates bundle-based "
            "governance and was never previously registered)."
            if all_pass else
            "Drift or regression detected between the original fit-time state and the "
            "current on-disk artifacts; RS_pass cannot be claimed as re-verified."
        ),
        "checks": checks,
        "source_metrics": {
            "human_h2_transfer_balanced_accuracy": fit_report["transparent_same_bank_rule_on_h2"]["balanced_accuracy"],
            "human_h2_transfer_positive_recall": fit_report["transparent_same_bank_rule_on_h2"]["positive_recall"],
            "human_h2_transfer_specificity": fit_report["transparent_same_bank_rule_on_h2"]["specificity"],
            "five_seed_h2_prediction_agreement": fit_report["five_seed_h2_prediction_agreement"],
        },
        "artifacts": {
            "checkpoint": {"path": str(CHECKPOINT.relative_to(ROOT)), "sha256": sha256_file(CHECKPOINT)},
            "fit_report": {"path": str(FIT_REPORT.relative_to(ROOT)), "sha256": sha256_file(FIT_REPORT)},
            "strategy_bank_v4": {"path": str(BANK.relative_to(ROOT)), "sha256": sha256_file(BANK)},
        },
        "not_evaluated_here": {
            "candidate_ranking_top1": "H2 Top-1 acceptable remains 19/31, not repaired by this refreeze",
            "generator_execution": "not evaluated -- RS routing decision only, not response quality",
        },
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
