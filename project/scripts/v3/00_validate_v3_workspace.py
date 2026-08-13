#!/usr/bin/env python3
"""Validate the portable, tracked V3 authority and optional private evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _combined_private_hash(root: Path) -> str:
    lines: list[bytes] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(REPO_ROOT).as_posix()
        lines.append(f"{digest}  {relative}\n".encode("utf-8"))
    return hashlib.sha256(b"".join(lines)).hexdigest()


def validate(require_private_evidence: bool = False) -> dict[str, Any]:
    authority_path = AUTHORITY_DIR / "v3_research_authority_v1.json"
    assets_path = AUTHORITY_DIR / "v3_asset_compatibility_manifest_v1.json"
    profile_path = AUTHORITY_DIR / "v3_active_test_profile_v1.json"
    evaluation_path = AUTHORITY_DIR / "v3_evaluation_freeze_contract_v1.json"
    reconciliation_path = AUTHORITY_DIR / "es_memeval_repository_reconciliation_v1.json"
    implementation_path = AUTHORITY_DIR / "official_benchmark_implementation_audit_v1.json"
    snapshot_path = AUTHORITY_DIR / "official_benchmark_surface_snapshot_v1.json"
    checklist_path = AUTHORITY_DIR / "p0_exit_checklist_v1.json"
    generator_contract_path = AUTHORITY_DIR / "generator_qualification_measurement_contract_v1.json"
    esc_rank_audit_path = AUTHORITY_DIR / "esc_rank_public_qualification_audit_v1.json"
    same_stack_reference_path = AUTHORITY_DIR / "same_stack_generator_reference_v1.json"
    margin_contract_path = AUTHORITY_DIR / "evaluation_margin_justification_v1.json"
    esc_rank_runtime_preflight_path = AUTHORITY_DIR / "esc_rank_runtime_preflight_v1.json"
    risk_protocol_path = AUTHORITY_DIR / "risk_adjudication_protocol_v1.json"
    runtime_lock_path = AUTHORITY_DIR / "benchmark_runtime_lock_v1.json"
    benchmark_dry_run_path = AUTHORITY_DIR / "benchmark_protocol_dry_run_manifest_v1.json"
    overlap_summary_path = AUTHORITY_DIR / "esc_training_exam_overlap_summary_v1.json"
    overlap_rows_path = AUTHORITY_DIR / "esc_training_exam_overlap_v1.jsonl"
    risk_qualification_path = AUTHORITY_DIR / "risk_instrument_qualification_v1.json"
    risk_packets_path = AUTHORITY_DIR / "atomic_risk_fixture_packets_v1.jsonl"
    risk_assignments_path = AUTHORITY_DIR / "atomic_risk_fixture_assignments_v1.jsonl"
    memeval_decision_path = AUTHORITY_DIR / "es_memeval_public_v1_0_0_1427_identity_decision_v1.json"
    memeval_row_identity_path = AUTHORITY_DIR / "es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl"
    authority = _load_json(authority_path)
    assets = _load_json(assets_path)
    profile = _load_json(profile_path)
    evaluation = _load_json(evaluation_path)
    reconciliation = _load_json(reconciliation_path)
    implementation = _load_json(implementation_path)
    snapshot = _load_json(snapshot_path)
    checklist = _load_json(checklist_path)
    generator_contract = _load_json(generator_contract_path)
    esc_rank_audit = _load_json(esc_rank_audit_path)
    same_stack_reference = _load_json(same_stack_reference_path)
    margin_contract = _load_json(margin_contract_path)
    esc_rank_runtime_preflight = _load_json(esc_rank_runtime_preflight_path)
    risk_protocol = _load_json(risk_protocol_path)
    runtime_lock = _load_json(runtime_lock_path)
    benchmark_dry_run = _load_json(benchmark_dry_run_path)
    overlap_summary = _load_json(overlap_summary_path)
    risk_qualification = _load_json(risk_qualification_path)
    memeval_decision = _load_json(memeval_decision_path)

    failures: list[str] = []

    expected_commit = "ef318c3e35982e277883e06c5ec25cc7392eab67"
    if authority["source_revision"]["source_commit"] != expected_commit:
        failures.append("unexpected authority source commit")
    if assets["source_commit"] != expected_commit:
        failures.append("authority/asset source commit mismatch")
    if authority["execution_boundary"]["this_file_authorizes"] == []:
        failures.append("execution boundary is empty")
    if any(phase.get("api_authority") for phase in authority["execution_phases"]):
        failures.append("a planning phase unexpectedly authorizes API execution")
    if evaluation["status"] != "P0_DESIGN_FREEZE_COMPLETE_P1_MEASUREMENT_QUALIFICATION_REQUIRED":
        failures.append("evaluation P0/P1 boundary changed")
    required_blocks = {"unqualified scorer or judge use", "numeric Quality/Risk margin absent", "same-stack generator selection incomplete"}
    if not required_blocks.issubset(set(evaluation["p1_blocks_before_formal_verdict"])):
        failures.append("evaluation P1 formal-verdict blocks are incomplete")

    phase_ids = [phase["phase"] for phase in authority["execution_phases"]]
    if phase_ids != [f"V3-P{index}" for index in range(7)]:
        failures.append("execution phases are not the frozen V3-P0..V3-P6 sequence")

    memeval = authority["external_tracks"]["ES_MemEval"]
    if memeval["status"] != "FROZEN_AS_ES_MEMEVAL_PUBLIC_V1_0_0_1427_NOT_EXACT_PAPER_REPLICATION":
        failures.append("ES-MemEval public-1427 identity decision changed")
    if not all(token in memeval["version_discrepancy"] for token in ("1209", "1427", "418")):
        failures.append("ES-MemEval discrepancy does not bind all known counts")

    required_documents = [
        PROJECT_ROOT / "docs" / "V3_MASTER_RESEARCH_PROGRAM_ZH.md",
        PROJECT_ROOT / "docs" / "V3_EVALUATION_BENCHMARK_PLAN_ZH.md",
        PROJECT_ROOT / "docs" / "V3_DATASET_AND_EVIDENCE_CARDS_ZH.md",
        PROJECT_ROOT / "docs" / "V3_EVALUATION_FREEZE_AUDIT_20260813_ZH.md",
        PROJECT_ROOT / "docs" / "V3_P0_IMPLEMENTATION_AUDIT_AND_EXIT_PLAN_ZH.md",
        PROJECT_ROOT / "scripts" / "v3" / "01_audit_official_benchmark_surfaces.py",
        PROJECT_ROOT / "scripts" / "v3" / "02_materialize_es_memeval_public_identity.py",
        PROJECT_ROOT / "scripts" / "v3" / "03_materialize_benchmark_protocol_dry_run.py",
        PROJECT_ROOT / "scripts" / "v3" / "04_materialize_esc_training_exam_overlap.py",
        PROJECT_ROOT / "scripts" / "v3" / "05_materialize_atomic_risk_instrument.py",
        PROJECT_ROOT / "scripts" / "v3" / "06_run_v3_active_tests.py",
        PROJECT_ROOT / "scripts" / "v3" / "07_audit_esc_rank_public_qualification.py",
        PROJECT_ROOT / "scripts" / "v3" / "08_materialize_esc_rank_runtime_preflight.py",
        REPO_ROOT / "V3_MIGRATION_REPORT_ZH.md",
    ]
    failures.extend(
        f"missing required document: {path.relative_to(REPO_ROOT)}"
        for path in required_documents
        if not path.is_file()
    )

    test_paths = [PROJECT_ROOT / relative for relative in profile["tests"]]
    failures.extend(
        f"missing active test: {path.relative_to(PROJECT_ROOT)}"
        for path in test_paths
        if not path.is_file()
    )
    if profile["expected_test_count"] != 53:
        failures.append("active profile expected test count changed without authority update")

    dataset_cards = [_load_json(PROJECT_ROOT / relative) for relative in authority["evaluation_freeze"]["dataset_cards"]]
    if {card["dataset"] for card in dataset_cards} != {"ESConv", "EvoEmo", "ES-MemEval", "ESC-Eval"}:
        failures.append("the four required structured dataset cards are incomplete")
    esconv = next(card for card in dataset_cards if card["dataset"] == "ESConv")
    esconv_path = PROJECT_ROOT / esconv["official_source"]["local_path"]
    if hashlib.sha256(esconv_path.read_bytes()).hexdigest() != esconv["official_source"]["sha256"]:
        failures.append("local ESConv file does not match its pinned official hash")
    es_memeval = next(card for card in dataset_cards if card["dataset"] == "ES-MemEval")
    paper_qa = es_memeval["formal_paper"]["reported_counts"]["qa"]
    public_qa = es_memeval["public_repository"]["observed_counts"]["qa"]
    if (paper_qa, public_qa, public_qa - paper_qa) != (1209, 1427, 218):
        failures.append("ES-MemEval 1209/1427/218 identity conflict changed")
    if es_memeval["status"] != "FROZEN_AS_ES_MEMEVAL_PUBLIC_V1_0_0_1427_WITH_DISCLOSURE":
        failures.append("ES-MemEval dataset card lost the public-1427 decision")
    comparison = reconciliation["qa_count_comparison"]
    if comparison[-1] != {"capability": "total", "formal_paper": 1209, "public_v1_0_0": 1427, "difference": 218}:
        failures.append("ES-MemEval reconciliation total is inconsistent")
    if sum(row["difference"] for row in comparison[:-1]) != 218:
        failures.append("ES-MemEval capability deltas do not sum to 218")

    if implementation["status"] != "OFFICIAL_PROTOCOLS_PINNED_LOCAL_QUALIFICATION_REQUIRED":
        failures.append("official implementation audit status changed")
    if runtime_lock["status"] != "P0_PROTOCOL_AND_IDENTITIES_FROZEN_P1_RUNTIME_QUALIFICATION_NOT_AUTHORIZED":
        failures.append("benchmark runtime lock status changed")
    if runtime_lock["authorization"] != {"model_calls": False, "judge_calls": False, "fine_tuning": False}:
        failures.append("benchmark runtime lock unexpectedly authorizes execution")
    if hashlib.sha256(benchmark_dry_run_path.read_bytes()).hexdigest() != runtime_lock["dry_run"]["sha256"]:
        failures.append("benchmark dry-run hash does not match runtime lock")
    if benchmark_dry_run["api_calls"] != 0 or benchmark_dry_run["contains_role_or_dialogue_text"] is not False:
        failures.append("benchmark dry run is not zero-call and text-free")
    if benchmark_dry_run["ESC-Eval"]["card_count"] != 655:
        failures.append("benchmark dry run lost the 655 ESC-Eval cards")
    if (benchmark_dry_run["ESC-Judge"]["public_role_count"], benchmark_dry_run["ESC-Judge"]["selected_role_count"], benchmark_dry_run["ESC-Judge"]["judge_unit_count"]) != (100, 25, 150):
        failures.append("benchmark dry run lost the frozen ESC-Judge 100/25/150 shape")
    if snapshot["ESC-Eval"]["high_quality_cards"] != {"en": 331, "zh": 324, "total": 655}:
        failures.append("ESC-Eval public 655-card identity changed")
    if snapshot["ESC-Eval"]["commit"] != implementation["benchmarks"]["ESC-Eval"]["commit"]:
        failures.append("ESC-Eval audit/snapshot commit mismatch")
    if snapshot["ESC-Judge"]["roles_v1_records"] != 100:
        failures.append("ESC-Judge public role count changed")
    if snapshot["ESC-Judge"]["explicit_bidirectional_order_aggregation_present"] is not False:
        failures.append("ESC-Judge position-order audit changed without qualification update")
    if snapshot["ES-MemEval"]["qa"] != 1427 or snapshot["ES-MemEval"]["public_git_commits"] != 2:
        failures.append("ES-MemEval public history surface changed")
    row_identity_bytes = memeval_row_identity_path.read_bytes()
    row_identity_records = [json.loads(line) for line in row_identity_bytes.decode("utf-8").splitlines() if line]
    row_identity_sha256 = hashlib.sha256(row_identity_bytes).hexdigest()
    if len(row_identity_records) != 1427 or len({row["row_id"] for row in row_identity_records}) != 1427:
        failures.append("ES-MemEval public-1427 row identity is incomplete or non-unique")
    if row_identity_sha256 != memeval_decision["identity_manifest"]["sha256"]:
        failures.append("ES-MemEval public-1427 row identity hash mismatch")
    local_memeval_path = PROJECT_ROOT / "data" / "external" / "evo_emo.json"
    if hashlib.sha256(local_memeval_path.read_bytes()).hexdigest() != memeval_decision["source"]["sha256"]:
        failures.append("local ES-MemEval/EvoEmo file does not match the frozen public-v1.0.0 source")
    capability_counts: dict[str, int] = {}
    for row in row_identity_records:
        capability_counts[row["capability"]] = capability_counts.get(row["capability"], 0) + 1
    if capability_counts != memeval_decision["identity_manifest"]["capability_counts"]:
        failures.append("ES-MemEval public-1427 capability counts changed")
    if any("question" in row or "answer" in row or "evidence" in row for row in row_identity_records):
        failures.append("ES-MemEval row identity unexpectedly contains benchmark text")
    if memeval_decision["formal_paper_boundary"]["forbidden_wording"] == "":
        failures.append("ES-MemEval exact-paper-replication boundary is empty")
    if checklist["p0_exit_now"] is not True:
        failures.append("P0 design checklist is not complete")
    if checklist["p0_completion_authorizes_api_calls"] or checklist["p0_completion_authorizes_formal_verdicts"]:
        failures.append("P0 design completion unexpectedly authorizes execution or verdicts")
    complete_gates = {gate["gate"] for gate in checklist["gates"] if gate["status"] == "COMPLETE"}
    if complete_gates != {"dataset_identity", "official_implementation_pin", "scorer_and_judge_role_and_qualification_plan", "same_stack_reference", "pass_margin_derivation_plan", "training_exam_overlap", "atomic_risk_instrument_design", "statistical_units_and_estimands", "claim_boundaries_and_function_role"}:
        failures.append("P0 complete-gate set changed without authority update")
    overlap_bytes = overlap_rows_path.read_bytes()
    overlap_rows = [json.loads(line) for line in overlap_bytes.decode("utf-8").splitlines() if line]
    if overlap_summary["cards_in_known_training_source_scope"] != 228 or len(overlap_rows) != 228:
        failures.append("ESC training/exam overlap row count changed")
    if hashlib.sha256(overlap_bytes).hexdigest() != overlap_summary["row_manifest"]["sha256"]:
        failures.append("ESC training/exam overlap row hash mismatch")
    if overlap_summary["qualification_identity_policy"]["clean_english_holdout_if_esconv_and_extes_train"]["cards"] != 103:
        failures.append("contamination-aware ESC English holdout changed")
    if overlap_summary["contains_source_or_card_text"] is not False or overlap_summary["api_calls"] != 0:
        failures.append("ESC overlap artifact is not zero-call and text-free")
    forbidden_overlap_fields = {"text", "raw_text", "source_text", "card_text", "problem", "problem_text"}
    if any(key in forbidden_overlap_fields for row in overlap_rows for key in row):
        failures.append("ESC overlap rows unexpectedly expose benchmark/source text")
    risk_packets = [json.loads(line) for line in risk_packets_path.read_text(encoding="utf-8").splitlines() if line]
    risk_assignments = [json.loads(line) for line in risk_assignments_path.read_text(encoding="utf-8").splitlines() if line]
    if risk_qualification["status"] != "INSTRUMENT_DRY_RUN_COMPLETE_HUMAN_QUALIFICATION_PENDING":
        failures.append("Risk instrument qualification status changed")
    if (len(risk_packets), len(risk_assignments), risk_qualification["review_tasks"]) != (18, 36, 36):
        failures.append("Risk fixture/assignment shape changed")
    if risk_qualification["mechanical_validation_failures"] or risk_qualification["formal_replies_consumed"] != 0:
        failures.append("Risk fixture failed validation or consumed formal replies")
    if any("gold" in key or "expected" in key for row in risk_packets + risk_assignments for key in row):
        failures.append("blinded Risk packets or assignments expose gold")
    leaked_id_tokens = {*risk_protocol["events"], "positive", "safe", "ambiguous"}
    if risk_qualification["public_identifier_contains_target_or_variant"] is not False:
        failures.append("Risk qualification does not attest blinded public identifiers")
    if any(any(token in row["packet_id"] for token in leaked_id_tokens) for row in risk_packets + risk_assignments):
        failures.append("Risk public packet identifiers expose target or fixture variant")
    if len(risk_qualification["artifact_hashes"]["gold"]) != 64 or "HASH_COMMITMENT_ONLY" not in risk_qualification["gold_release_policy"]:
        failures.append("Risk fixture gold is not bound by an embargoed hash commitment")
    if not generator_contract["primary_exam"]["pass_margin"].startswith("NO_SOLE_ESC_RANK_NUMERIC_CUTOFF"):
        failures.append("generator contract permits an unsupported sole ESC-RANK cutoff")
    if esc_rank_audit["status"] != "PUBLIC_SCORER_REPLAYABLE_ONLY_AFTER_REPAIR_HUMAN_CALIBRATION_NOT_INDEPENDENTLY_REPRODUCIBLE":
        failures.append("ESC-RANK public qualification decision changed")
    if esc_rank_audit["api_calls"] != 0 or esc_rank_audit["model_inference_calls"] != 0:
        failures.append("ESC-RANK public audit unexpectedly consumed inference")
    if esc_rank_audit["sources"]["ESC-Eval"]["public_human_label_rows"] != 0:
        failures.append("ESC-RANK audit human-label availability changed without review")
    if esc_rank_audit["sources"]["ESC-RANK"]["primary_language_dimension_adapters"] != 14:
        failures.append("ESC-RANK adapter surface changed")
    if same_stack_reference["status"] != "REFERENCE_SELECTED_ZERO_INFERENCE_EXECUTION_PENDING_APPROVAL":
        failures.append("same-stack reference status changed")
    if same_stack_reference["reference"]["model_route"] != "meta/llama-3.3-70b-instruct":
        failures.append("same-stack reference route changed")
    if same_stack_reference["accessibility_check"]["inference_calls"] != 0:
        failures.append("same-stack accessibility check unexpectedly used inference")
    if margin_contract["status"] != "DERIVATION_RULE_FROZEN_NUMERIC_CALIBRATION_VALUES_PENDING_P1":
        failures.append("margin derivation status changed")
    if margin_contract["p1_registration_gate"]["formal_outcomes_may_not_change_these_values"] is not True:
        failures.append("formal outcomes can change calibration values")
    if esc_rank_runtime_preflight["status"] != "STATIC_OVERLAY_PREFLIGHT_PASS_WEIGHTS_AND_INFERENCE_NOT_EXECUTED":
        failures.append("ESC-RANK static runtime preflight status changed")
    if esc_rank_runtime_preflight["inference_calls"] != 0 or esc_rank_runtime_preflight["model_weights_downloaded"] != 0:
        failures.append("ESC-RANK runtime preflight unexpectedly consumed weights or inference")
    if risk_protocol["statistics"]["noninferiority_margin"] != "NOT_NUMERICALLY_FROZEN_PENDING_FIXTURE_AND_HUMAN_CALIBRATION":
        failures.append("Risk margin was set without instrument calibration")
    if "uncertain" not in risk_protocol["events"]:
        failures.append("atomic Risk protocol lost UNCERTAIN")

    for path in (
        authority_path,
        assets_path,
        profile_path,
        evaluation_path,
        reconciliation_path,
        implementation_path,
        snapshot_path,
        checklist_path,
        generator_contract_path,
        esc_rank_audit_path,
        same_stack_reference_path,
        margin_contract_path,
        esc_rank_runtime_preflight_path,
        risk_protocol_path,
        runtime_lock_path,
        benchmark_dry_run_path,
        overlap_summary_path,
        risk_qualification_path,
        memeval_decision_path,
    ):
        if "/home/tokkio/snap/" in path.read_text(encoding="utf-8"):
            failures.append(f"legacy absolute path leaked into {path.name}")

    private_spec = assets["private_evidence"]
    private_root = REPO_ROOT / private_spec["path"]
    private_result: dict[str, Any] = {"present": private_root.is_dir()}
    if private_root.is_dir():
        files = [path for path in private_root.rglob("*") if path.is_file()]
        private_result.update(
            {
                "file_count": len(files),
                "bytes": sum(path.stat().st_size for path in files),
                "combined_sha256": _combined_private_hash(private_root),
            }
        )
        if private_result["file_count"] != private_spec["file_count"]:
            failures.append("private evidence file count mismatch")
        if private_result["bytes"] != private_spec["bytes"]:
            failures.append("private evidence byte count mismatch")
        if private_result["combined_sha256"] != private_spec["deterministic_combined_sha256"]:
            failures.append("private evidence combined hash mismatch")
    elif require_private_evidence:
        failures.append("private evidence is required locally but not present")
    else:
        private_result["public_clone_status"] = "not_present_public_ok"

    return {
        "protocol": "metacom-v3-workspace-validation-v1",
        "valid": not failures,
        "failures": failures,
        "source_commit": expected_commit,
        "phase_ids": phase_ids,
        "active_test_files": len(test_paths),
        "expected_active_test_count": profile["expected_test_count"],
        "evaluation_freeze_status": evaluation["status"],
        "dataset_cards": [card["dataset"] for card in dataset_cards],
        "es_memeval_identity": {"formal_paper_qa": paper_qa, "public_v1_0_0_qa": public_qa, "difference": public_qa - paper_qa},
        "official_benchmark_surfaces": {
            "esc_eval_cards": snapshot["ESC-Eval"]["high_quality_cards"]["total"],
            "esc_judge_public_roles": snapshot["ESC-Judge"]["roles_v1_records"],
            "es_memeval_public_git_commits": snapshot["ES-MemEval"]["public_git_commits"],
        },
        "p0_exit_now": checklist["p0_exit_now"],
        "p0_complete_gates": sorted(complete_gates),
        "benchmark_dry_run": {"esc_eval_cards": 655, "esc_judge_roles": 25, "esc_judge_units": 150, "api_calls": 0},
        "esc_overlap": {"rows": len(overlap_rows), "clean_english_if_esconv_extes_sft": 103},
        "risk_instrument": {"packets": len(risk_packets), "assignments": len(risk_assignments), "formal_replies_consumed": 0},
        "esc_rank_public_qualification": {"public_human_label_rows": 0, "primary_adapters": 14, "inference_calls": 0},
        "esc_rank_runtime_preflight": {"status": "STATIC_PASS", "weights_downloaded": 0, "inference_calls": 0},
        "same_stack_reference": same_stack_reference["reference"]["model_route"],
        "numeric_calibration_phase": "P1_PENDING_BEFORE_FORMAL_VERDICT",
        "es_memeval_primary_task": memeval_decision["primary_task_name"],
        "es_memeval_row_identity": {"rows": len(row_identity_records), "sha256": row_identity_sha256},
        "private_evidence": private_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-private-evidence", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = validate(require_private_evidence=args.require_private_evidence)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
