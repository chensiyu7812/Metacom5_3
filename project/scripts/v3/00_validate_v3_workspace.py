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
    risk_protocol_path = AUTHORITY_DIR / "risk_adjudication_protocol_v1.json"
    authority = _load_json(authority_path)
    assets = _load_json(assets_path)
    profile = _load_json(profile_path)
    evaluation = _load_json(evaluation_path)
    reconciliation = _load_json(reconciliation_path)
    implementation = _load_json(implementation_path)
    snapshot = _load_json(snapshot_path)
    checklist = _load_json(checklist_path)
    generator_contract = _load_json(generator_contract_path)
    risk_protocol = _load_json(risk_protocol_path)

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
    if evaluation["status"] != "P0_NOT_COMPLETE_BLOCKS_HEAD_TUNING_AND_FORMAL_JUDGING":
        failures.append("evaluation P0 status no longer blocks premature head decisions")
    required_blocks = {"new head tuning", "selector refit", "formal PM judge calls", "generator fine-tuning"}
    if not required_blocks.issubset(set(evaluation["execution_blocks_until_p0_complete"])):
        failures.append("evaluation P0 execution blocks are incomplete")

    phase_ids = [phase["phase"] for phase in authority["execution_phases"]]
    if phase_ids != [f"V3-P{index}" for index in range(7)]:
        failures.append("execution phases are not the frozen V3-P0..V3-P6 sequence")

    memeval = authority["external_tracks"]["ES_MemEval"]
    if memeval["status"] != "BLOCKED_ON_FORMAL_1209_IDENTITY_OR_PUBLIC_1427_NAMING_DECISION":
        failures.append("ES-MemEval version discrepancy is not an explicit blocker")
    if not all(token in memeval["version_discrepancy"] for token in ("1209", "1427", "418")):
        failures.append("ES-MemEval discrepancy does not bind all known counts")

    required_documents = [
        PROJECT_ROOT / "docs" / "V3_MASTER_RESEARCH_PROGRAM_ZH.md",
        PROJECT_ROOT / "docs" / "V3_EVALUATION_BENCHMARK_PLAN_ZH.md",
        PROJECT_ROOT / "docs" / "V3_DATASET_AND_EVIDENCE_CARDS_ZH.md",
        PROJECT_ROOT / "docs" / "V3_EVALUATION_FREEZE_AUDIT_20260813_ZH.md",
        PROJECT_ROOT / "docs" / "V3_P0_IMPLEMENTATION_AUDIT_AND_EXIT_PLAN_ZH.md",
        PROJECT_ROOT / "scripts" / "v3" / "01_audit_official_benchmark_surfaces.py",
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
    if profile["expected_test_count"] != 39:
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
    comparison = reconciliation["qa_count_comparison"]
    if comparison[-1] != {"capability": "total", "formal_paper": 1209, "public_v1_0_0": 1427, "difference": 218}:
        failures.append("ES-MemEval reconciliation total is inconsistent")
    if sum(row["difference"] for row in comparison[:-1]) != 218:
        failures.append("ES-MemEval capability deltas do not sum to 218")

    if implementation["status"] != "OFFICIAL_PROTOCOLS_PINNED_LOCAL_QUALIFICATION_REQUIRED":
        failures.append("official implementation audit status changed")
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
    if checklist["p0_exit_now"] is not False:
        failures.append("P0 checklist unexpectedly permits exit")
    complete_gates = {gate["gate"] for gate in checklist["gates"] if gate["status"] == "COMPLETE"}
    if complete_gates != {"statistical_units_and_estimands", "claim_boundaries_and_function_role"}:
        failures.append("P0 complete-gate set changed without authority update")
    if generator_contract["primary_exam"]["pass_margin"] != "NOT_NUMERICALLY_FROZEN":
        failures.append("generator margin was set without qualification evidence")
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
        risk_protocol_path,
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
