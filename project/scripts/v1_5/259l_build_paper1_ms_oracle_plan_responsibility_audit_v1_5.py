#!/usr/bin/env python3
"""Build a zero-API responsibility audit and blind three-arm packet."""

from __future__ import annotations

from collections import Counter
import html
import json
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_oracle_plan_upper_bound_closeout_v1.json"
ANNOTATIONS = ROOT / "data/pm_v1_5_contracts/paper1_ms_oracle_plan_development_audit_v1.json"
CASES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/qualification_cases_private.jsonl"
OLD = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_live_20260811/generator_results_private.jsonl"
NEW = ROOT / "outputs/pm_v1_5_paper1_ms_oracle_plan_upper_bound_live_20260811/generator_results_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_oracle_plan_responsibility_audit_20260811"


def main() -> None:
    phase = read_json(PHASE)
    if phase["authorization"]["api_calls"] != 0 or not phase["authorization"]["zero_api_responsibility_audit"]:
        raise RuntimeError("zero-API responsibility audit is not active")
    for item in phase["artifacts"]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"live artifact drifted: {item['path']}")
    cases = {row["qualification_case_id"]: row for row in read_jsonl(CASES)}
    old = {(row["qualification_case_id"], row["requested_action_id"]): row for row in read_jsonl(OLD)}
    new = {row["qualification_case_id"]: row for row in read_jsonl(NEW)}
    annotations = read_json(ANNOTATIONS)["annotations"]
    if len(annotations) != len(new) or {row["qualification_case_id"] for row in annotations} != set(new):
        raise RuntimeError("annotation denominator drifted")
    for row in annotations:
        cid = row["qualification_case_id"]
        if row["response_evidence_quote"] not in new[cid]["final_reply"]:
            raise RuntimeError(f"response quote drifted: {cid}")
        if row["source_evidence_quote"] not in cases[cid]["exact_source"]:
            raise RuntimeError(f"source quote drifted: {cid}")

    blind_quality = []
    private_key = []
    function_packet = []
    for cid in sorted(new):
        arms = {
            "R0": old[(cid, "M0+R0")]["final_reply"],
            "GENERIC_MS": old[(cid, "MS+R0")]["final_reply"],
            "ORACLE_PLAN": new[cid]["final_reply"],
        }
        names = list(arms)
        random.Random(int(stable_hex(cid, "blind3", n=12), 16)).shuffle(names)
        mapping = {letter: name for letter, name in zip(("A", "B", "C"), names, strict=True)}
        blind_quality.append({
            "protocol": "pm-v1.5-paper1-ms-oracle-plan-three-arm-quality-blind-v1",
            "blind_item_id": "msoracleq_" + stable_hex(cid, n=20),
            "visible_current_dialogue": cases[cid]["current_context"],
            "response_A": arms[mapping["A"]],
            "response_B": arms[mapping["B"]],
            "response_C": arms[mapping["C"]],
            "decision": {
                "labels": ["A_BEST", "B_BEST", "C_BEST", "ALL_EQUIVALENT", "MIXED_NO_CLEAR_BEST", "UNRESOLVED"],
                "rule": "Judge current-goal support, emotional fit, focus, burden, naturalness, and closure. Do not reward a response merely for mentioning past information.",
                "required": "Quote one decisive span and give one concise reason."
            },
            "annotation": {"label": "", "decisive_quote": "", "reason": ""},
        })
        private_key.append({"blind_item_id": blind_quality[-1]["blind_item_id"], "qualification_case_id": cid, "arm_mapping": mapping})
        function_packet.append({
            "protocol": "pm-v1.5-paper1-ms-oracle-plan-function-blind-v1",
            "blind_item_id": "msoraclef_" + stable_hex(cid, n=20),
            "visible_current_dialogue": cases[cid]["current_context"],
            "strictly_past_source": cases[cid]["exact_source"],
            "response": new[cid]["final_reply"],
            "decision": {
                "labels": ["FUNCTIONAL", "NOT_USED_FINAL", "BOUNDARY_FAILURE", "EXECUTION_FAILURE", "UNRESOLVED"],
                "rule": "FUNCTIONAL requires a material source-attributable contribution not already supplied by the current dialogue. A better reply is not automatically memory Function.",
                "required": "Quote the source and response spans that establish the label."
            },
            "annotation": {"label": "", "source_quote": "", "response_quote": "", "reason": ""},
        })

    counts = Counter(row["function_label"] for row in annotations)
    intended = [row for row in annotations if new[row["qualification_case_id"]]["oracle_disposition_private"] == "USE_IF_NATURAL"]
    safe = [row for row in annotations if new[row["qualification_case_id"]]["oracle_disposition_private"] == "SAFE_NONUSE"]
    analysis = {
        "protocol": "pm-v1.5-paper1-ms-oracle-plan-responsibility-audit-analysis-v1",
        "status": "ZERO_API_DEVELOPMENT_AUDIT_COMPLETE_BLIND_PACKET_READY_REVIEW_NOT_AUTHORIZED",
        "observed_generation": {
            "states": 8,
            "generator_claimed_ms": sum(bool(row["generator_claimed"]["MS"]) for row in new.values()),
            "guard_reported_clean": sum(not row["guard_errors"] for row in new.values()),
            "actual_scaffold_exposure_found_by_source_aware_audit": sum(row["scaffold_exposure"] for row in annotations),
        },
        "unblinded_development_function": {
            "counts": dict(counts),
            "intended_use_denominator": len(intended),
            "intended_use_functional": sum(row["function_label"] == "FUNCTIONAL" for row in intended),
            "intended_use_not_used": sum(row["function_label"] == "NOT_USED_FINAL" for row in intended),
            "intended_use_execution_failure": sum(row["function_label"] == "EXECUTION_FAILURE" for row in intended),
            "safe_nonuse_denominator": len(safe),
            "safe_nonuse_correct": sum(row["function_label"] == "SAFE_NONUSE_CORRECT" for row in safe),
        },
        "diagnosis": {
            "kelly_case_fixed": True,
            "generic_nli_model_needed": False,
            "candidate_specific_plan_is_sufficient_for_some_cases": True,
            "candidate_specific_plan_is_not_sufficient_for_reliable_memory_function": True,
            "teacher_suitable_contains_nonincremental_or_entity_unsafe_cases": True,
            "guard_misses_plan_scaffold_exposure": True,
            "primary_bottleneck": "MS gold and selected-candidate material increment are not aligned with source-attributable execution; generator/guard is a secondary bottleneck.",
        },
        "next_decision": "Do not retrain yet. Repair the MS supervision unit so ON requires a source-grounded candidate-specific response change that is not already available from current context; add plan-scaffold guard; then rerun grouped OOF once on the corrected frozen labels.",
        "claim_limit": "Single-Codex unblinded development diagnosis. Blind packets are materialized but review execution is not authorized.",
        "api_calls": 0,
        "pm_fits": 0,
        "training_labels_changed": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "function_blind_packet.jsonl", function_packet)
    write_jsonl(OUT / "quality_three_arm_blind_packet.jsonl", blind_quality)
    write_jsonl(OUT / "quality_three_arm_private_key.jsonl", private_key)
    write_json(OUT / "analysis.json", analysis)
    rows = "".join(
        f"<tr><td>{html.escape(row['qualification_case_id'])}</td><td>{html.escape(row['candidate_increment'])}</td><td>{html.escape(row['plan_followed'])}</td><td>{html.escape(row['function_label'])}</td><td>{html.escape(row['quality_direction'])}</td><td>{html.escape(row['reason'])}</td></tr>"
        for row in annotations
    )
    report_html = f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>MS oracle plan responsibility audit</title><style>body{{font-family:system-ui;max-width:1200px;margin:32px auto;line-height:1.55}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #ddd;padding:6px;vertical-align:top}}th{{background:#f5f5f5}}</style></head><body><h1>MS oracle-plan 责任漏斗</h1><p><strong>主诊断：</strong>{html.escape(analysis['diagnosis']['primary_bottleneck'])}</p><ul><li>预设应使用：2/6 FUNCTIONAL，3/6 NOT_USED，1/6 execution failure。</li><li>预设安全不用：2/2 正确不用。</li><li>Kelly 已修正；通用 NLI 已拒绝进入正式系统。</li><li>本表是已解盲工程诊断，不是论文人评结果。</li></ul><table><thead><tr><th>case</th><th>candidate increment</th><th>plan followed</th><th>Function</th><th>quality dev</th><th>reason</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""
    (OUT / "report.html").write_text(report_html, encoding="utf-8")
    report = {
        "protocol": "pm-v1.5-paper1-ms-oracle-plan-responsibility-audit-report-v1",
        "status": analysis["status"],
        "analysis": {"path": str((OUT / "analysis.json").relative_to(ROOT)), "sha256": sha256_file(OUT / "analysis.json")},
        "development_annotations": {"path": str(ANNOTATIONS.relative_to(ROOT)), "sha256": sha256_file(ANNOTATIONS), "rows": 8},
        "function_packet": {"path": str((OUT / "function_blind_packet.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "function_blind_packet.jsonl"), "rows": 8},
        "quality_packet": {"path": str((OUT / "quality_three_arm_blind_packet.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "quality_three_arm_blind_packet.jsonl"), "rows": 8},
        "private_key": {"path": str((OUT / "quality_three_arm_private_key.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "quality_three_arm_private_key.jsonl"), "rows": 8},
        "html": {"path": str((OUT / "report.html").relative_to(ROOT)), "sha256": sha256_file(OUT / "report.html")},
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
