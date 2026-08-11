#!/usr/bin/env python3
"""Freeze the exact dual-family 12-control source-aware MS qualification plan."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_source_annotated_suitability_review import (  # noqa: E402
    MSSourceAnnotatedSuitabilityReview,
    prompt_messages,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_ms_supervision_repair_packet_closeout_v1.json"
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/qualification_controls_blind.jsonl"
CONTROL_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812/qualification_control_key.jsonl"
ENDPOINTS = ROOT / "configs/paper1_ms_source_annotated_review_endpoints_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_control_preflight_20260812"
REVIEWERS = {
    "MS_SOURCE_PRIMARY_GPT56": "openai_gpt_5_6_sol",
    "MS_SOURCE_CHALLENGER_GEMINI": "google_gemini_2_5_flash",
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _stable(*parts: str, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("qualification preflight exists; refusing overwrite")
    authority = _read(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_binding = {"path": str(CLOSEOUT.relative_to(ROOT)), "sha256": sha256_file(CLOSEOUT)}
    if current["id"] != "MS_SUPERVISION_REPAIR_PACKET_READY" or current["active_phase_manifest"] != expected_binding:
        raise RuntimeError("MS repair packet is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_binding:
        raise RuntimeError("authority compatibility alias drifted")
    controls = _rows(CONTROLS)
    key = _rows(CONTROL_KEY)
    endpoints = _read(ENDPOINTS)
    request = endpoints["request_contract"]
    if not (len(controls) == len(key) == 12):
        raise RuntimeError("exact 12 controls required")
    by_id = {row["repair_item_id"]: row for row in key}
    if set(by_id) != {row["repair_item_id"] for row in controls}:
        raise RuntimeError("control/key join mismatch")

    plan = []
    for reviewer_id, endpoint_key in REVIEWERS.items():
        endpoint = endpoints["candidates"][endpoint_key]
        for item in controls:
            messages = prompt_messages(item, reviewer_id)
            plan.append({
                "protocol": "pm-v1.5-paper1-ms-source-annotated-control-call-v1",
                "logical_call_id": "mssrcctrlcall_" + _stable(reviewer_id, item["repair_item_id"]),
                "reviewer_id": reviewer_id,
                "endpoint_key": endpoint_key,
                "model": endpoint["model"],
                "repair_item_id": item["repair_item_id"],
                "messages": messages,
                "messages_sha256": sha256_text(canonical_json(messages)),
                "schema_sha256": sha256_text(canonical_json(MSSourceAnnotatedSuitabilityReview.model_json_schema())),
                "seed": int(request["seed"]) + int(_stable(reviewer_id, item["repair_item_id"], length=8), 16) % 100000,
                "temperature": request["temperature"],
                "max_output_tokens": request["max_output_tokens"],
            })
    provider_text = canonical_json([row["messages"] for row in plan])
    gold_counts = Counter(row["expected_final_suitability"] for row in key)
    checks = {
        "unique_current_execution_pointer": alias.get("compatibility_alias_of") == "current_execution_phase",
        "exact_12_blind_controls": len(controls) == 12 and len({row["repair_item_id"] for row in controls}) == 12,
        "exact_24_dual_family_calls": len(plan) == 24 and len({row["logical_call_id"] for row in plan}) == 24,
        "two_provider_families": len({endpoints["candidates"][key]["family"] for key in REVIEWERS.values()}) == 2,
        "control_distribution_5_5_2": gold_counts == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2},
        "gold_and_old_teacher_never_provider_visible": all(term not in provider_text for term in ("expected_final_suitability", "gold_decision", "teacher_decision", "selection_score", "outer_fold")),
        "one_strict_schema": len({row["schema_sha256"] for row in plan}) == 1,
        "gemini_thinking_explicitly_zero": endpoints["candidates"]["google_gemini_2_5_flash"]["gemini_thinking_budget"] == 0,
        "gpt_reasoning_effort_frozen_low": endpoints["candidates"]["openai_gpt_5_6_sol"]["openai_reasoning_effort"] == "low",
        "zero_api_zero_label_zero_fit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"qualification preflight failed: {checks}")
    OUT.mkdir(parents=True)
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-ms-source-annotated-control-preflight-v1",
        "status": "PASS_EXACT_24_CONTROL_CALL_EXECUTION_PHASE_MAY_BE_DESIGNED",
        "checks": checks,
        "reviewers": REVIEWERS,
        "qualification_gate": {
            "primary_gpt56": {
                "schema_valid": "12/12",
                "exact_final_decision": "12/12",
                "opposite_suitable_vs_not_suitable_errors": 0,
                "positive": "5/5",
                "negative": "5/5",
                "abstain": "2/2"
            },
            "challenger_gemini": {
                "schema_valid": "12/12",
                "exact_final_decision_min": "11/12",
                "opposite_suitable_vs_not_suitable_errors": 0,
                "positive_min": "4/5",
                "negative_min": "4/5",
                "abstain_min": "1/2"
            },
            "source_plan_field_audit": "All 24 outputs must name a source-attributable increment or explicit NONE/UNRESOLVED, a permitted response change or explicit NONE/UNRESOLVED, a forbidden focus shift, and a safe nonuse condition. This is audited before any 201-item review authorization.",
            "no_threshold_relaxation_after_results": True,
        },
        "execution_bounds": {
            "logical_calls": 24,
            "maximum_physical_attempts": 48,
            "absolute_usd_cap": 0.75,
            "public_201_calls_if_qualification_fails": 0,
        },
        "artifacts": {
            "call_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "closeout": sha256_file(CLOSEOUT),
            "controls": sha256_file(CONTROLS),
            "control_key_private": sha256_file(CONTROL_KEY),
            "endpoints": sha256_file(ENDPOINTS),
            "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_ms_source_annotated_suitability_review.py"),
        },
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "next": "INDEPENDENT_ZERO_API_PREFLIGHT_AUDIT_THEN_EXACT_24_CONTROL_CALL_PHASE",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
