#!/usr/bin/env python3
"""Validate the source-annotated method before any label row or fit exists."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_p2b_control_failure_closeout_phase_v1.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_source_annotated_resource_suitability_method_candidate_v1.json"
RULE = ROOT / "data/pm_v1_5_contracts/paper1_source_annotated_primary_head_rule_v1.json"
CAPACITY = ROOT / "outputs/pm_v1_5_paper1_source_annotated_label_capacity_20260810/report.json"
PAID = ROOT / "outputs/pm_v1_5_paid_run_release.json"
SURFACE = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_paper1_source_annotated_method_validation_20260810/report.json"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    authority = read(AUTHORITY)
    closeout = read(CLOSEOUT)
    contract = read(CONTRACT)
    rule = read(RULE)
    capacity = read(CAPACITY)
    paid = read(PAID)
    runtime_rows = [
        *rows(SURFACE / "esconv_states_unlabeled.jsonl"),
        *rows(SURFACE / "evoemo_states_unlabeled.jsonl"),
        *rows(SURFACE / "evoemo_candidates_unlabeled.jsonl"),
    ]
    forbidden_keys = {"annotation", "event_experience", "influenced_by", "answer", "evidence", "capability"}
    runtime_keys = {key for row in runtime_rows for key in row}
    checks = {
        "terminal_closeout_active_and_bound": authority["current_phase"]["id"]
        == "P2B_CONTROL_FAILED_ANNOTATED_LABEL_REDESIGN_PENDING"
        and authority["current_phase"]["active_phase_manifest"]["sha256"] == sha256_file(CLOSEOUT),
        "closeout_bindings_exact": all(sha256_file(ROOT / row["path"]) == row["sha256"] for row in closeout["bindings"]),
        "paid_calls_closed": paid["paid_execution_authorized"] is False and paid["stage_approvals"] == {},
        "new_method_identity": contract["method_id"] == "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V1"
        and contract["supersedes_for_future_training"] == "PAPER1_BOUNDED_SUITABILITY_SAFE_YIELD_V1",
        "primary_requires_rs_plus_memory": contract["claim"]["paper1_primary_machine_predicate"]
        == "RS_pass AND count_pass(MP,MS,ME)>=1"
        and rule["effective_machine_predicate"] == "RS_pass AND count_pass(MP,MS,ME)>=1",
        "rule_binds_contract": rule["base_method"]["contract_sha256"] == sha256_file(CONTRACT),
        "mp_not_fabricated": contract["label_factory"]["MP"]["status"].startswith("FIXED_OFF")
        and rule["initial_fixed_off"] == ["MP"],
        "rs_and_ms_capacity": capacity["status"] == "SOURCE_ANNOTATED_LABEL_CAPACITY_PASS_METHOD_VALIDATION_MAY_CONTINUE"
        and capacity["counts"]["RS"]["positive"] == 1378
        and capacity["counts"]["MS"]["positive"] == 832
        and capacity["counts"]["MS"]["positive_groups"] == capacity["counts"]["MS"]["negative_groups"] == 17,
        "runtime_surface_physically_excludes_label_keys": not (forbidden_keys & runtime_keys),
        "all_execution_still_false": not any(contract["authorization"].values()),
        "no_label_rows_or_fit_yet": capacity["label_rows_written"] == 0 and capacity["pm_fit"] is False,
        "sixteen_actions_and_same_stack_baselines_preserved": contract["action_space"]["legal_actions"] == 16
        and "always_off" in contract["same_stack_baselines"]
        and "learned_pm_qualified" in contract["same_stack_baselines"],
        "three_external_tracks_preserved": set(contract["external_tracks"]) == {"ESConv", "EvoEmo", "ES_MemEval"},
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "protocol": "pm-v1.5-paper1-source-annotated-method-validation-v1",
        "status": "SOURCE_ANNOTATED_METHOD_PASS_LABEL_FACTORY_PHASE_MAY_BE_DESIGNED" if not failed else "SOURCE_ANNOTATED_METHOD_FAIL",
        "method_contract_sha256": sha256_file(CONTRACT),
        "primary_rule_sha256": sha256_file(RULE),
        "capacity_report_sha256": sha256_file(CAPACITY),
        "checks": checks,
        "failed_checks": failed,
        "api_calls": 0,
        "label_rows_created": 0,
        "pm_fit": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
