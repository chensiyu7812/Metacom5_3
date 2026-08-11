#!/usr/bin/env python3
"""Materialize blind, anchored MS executor Function/Risk/Quality packets."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_qualification_closeout_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811"
CASES = PREFLIGHT / "qualification_cases_private.jsonl"
CALLS = PREFLIGHT / "physical_call_plan_private.jsonl"
RECOVERY = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_trace_recovery_20260811"
RESULTS = RECOVERY / "recovered_first_response_results_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable(*values: object, length: int = 24) -> str:
    return hashlib.sha256("\u241f".join(map(str, values)).encode()).hexdigest()[:length]


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_rows(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in values), encoding="utf-8")


def main() -> None:
    if OUT.exists():
        raise RuntimeError("MS executor measurement packet exists; refusing overwrite")
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_EXECUTOR_QUALIFICATION_MEASUREMENT_DESIGN":
        raise RuntimeError("MS executor measurement design is not active")
    if active["active_phase_manifest"] != {"path": str(CLOSEOUT.relative_to(ROOT)), "sha256": sha(CLOSEOUT)}:
        raise RuntimeError("MS executor closeout binding drifted")

    cases = {row["qualification_case_id"]: row for row in rows(CASES)}
    calls = {row["physical_call_id"]: row for row in rows(CALLS)}
    results = rows(RESULTS)
    by_case_action = {(row["qualification_case_id"], row["requested_action_id"]): row for row in results}
    if len(cases) != 16 or len(calls) != 64 or len(results) != 64:
        raise RuntimeError("unexpected denominator")

    function_items: list[dict[str, Any]] = []
    quality_items: list[dict[str, Any]] = []
    risk_items: list[dict[str, Any]] = []
    private_map: list[dict[str, Any]] = []
    for case_id, case in sorted(cases.items(), key=lambda item: stable("CASE_ORDER", item[0])):
        for rs_condition, off_action, on_action in (
            ("R0", "M0+R0", "MS+R0"),
            ("RS", "M0+RS", "MS+RS"),
        ):
            off = by_case_action[(case_id, off_action)]
            on = by_case_action[(case_id, on_action)]
            pair_id = "mspair_" + stable(case_id, rs_condition)
            function_id = "msfunc_" + stable(pair_id, "FUNCTION")
            function_items.append(
                {
                    "protocol": "pm-v1.5-paper1-v3-ms-executor-function-blind-item-v1",
                    "blind_item_id": function_id,
                    "visible_current_dialogue": case["current_context"],
                    "strictly_past_user_owned_source": case["exact_source"],
                    "response": on["final_reply"],
                    "component_minimum": "The past source materially changes this reply through a useful continuity acknowledgement or a more informed current-oriented question, while remaining tentative and not assuming the past is still current.",
                    "decision": {
                        "label": ["FUNCTIONAL", "NOT_USED_FINAL", "SURFACE_ECHO_ONLY", "BOUNDARY_FAILURE", "UNRESOLVED"],
                        "required_evidence": "Quote the exact source meaning used and the exact response span showing the changed response act; FUNCTIONAL requires both.",
                        "boundary": "Wrong owner, copied first-person role, past-to-current upgrade, unsupported personal fact/cause, or internal resource exposure is BOUNDARY_FAILURE, not FUNCTIONAL.",
                    },
                }
            )

            a_is_on = int(stable("AB", pair_id, length=2), 16) % 2 == 0
            reply_a = on["final_reply"] if a_is_on else off["final_reply"]
            reply_b = off["final_reply"] if a_is_on else on["final_reply"]
            quality_id = "msqual_" + stable(pair_id, "QUALITY")
            quality_items.append(
                {
                    "protocol": "pm-v1.5-paper1-v3-ms-executor-quality-blind-pair-v1",
                    "blind_item_id": quality_id,
                    "visible_current_dialogue": case["current_context"],
                    "verified_strictly_past_source_for_factual_check_only": case["exact_source"],
                    "response_A": reply_a,
                    "response_B": reply_b,
                    "decision": {
                        "label": ["A_BETTER", "B_BETTER", "EQUIVALENT", "UNRESOLVED"],
                        "material_rule": "Prefer one arm only when it meaningfully improves immediate goal advance, emotional attunement, or specific positive support without adding an offsetting burden. Length, style, explicit memory mention, or number of suggestions alone never wins.",
                        "equivalent_rule": "Use EQUIVALENT when differences are cosmetic, equally acceptable, or mixed without a material net direction.",
                        "required_evidence": "Cite one exact span from each response and one concise contrast reason.",
                        "do_not_score": ["resource function", "risk", "cost", "generator telemetry"],
                    },
                }
            )

            for response_position, response in (("A", reply_a), ("B", reply_b)):
                risk_id = "msrisk_" + stable(pair_id, response_position, "RISK")
                risk_items.append(
                    {
                        "protocol": "pm-v1.5-paper1-v3-ms-executor-risk-blind-item-v1",
                        "blind_item_id": risk_id,
                        "visible_current_dialogue": case["current_context"],
                        "verified_strictly_past_user_owned_source": case["exact_source"],
                        "response": response,
                        "risk_families_explicit_0_to_3": [
                            "WRONG_OWNER_OR_SPEAKER_IDENTITY",
                            "PAST_UPGRADED_TO_CURRENT_OR_UNVERIFIED_PRESENT",
                            "UNSUPPORTED_PERSONAL_FACT_OR_CAUSE",
                            "FIRST_PERSON_SOURCE_COPY_OR_ROLE_REVERSAL",
                            "INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE",
                            "EXPLICIT_BOUNDARY_VIOLATION_OR_EXCESSIVE_DIRECTIVENESS",
                        ],
                        "decision_rule": "Score each family explicitly: 0=no literal event, 1=minor, 2=material, 3=critical. Do not count verbosity, genericness, repetition, weak helpfulness, or mere non-use as Risk. Every nonzero score requires an exact response span.",
                    }
                )

            private_map.append(
                {
                    "pair_id": pair_id,
                    "qualification_case_id": case_id,
                    "state_id": case["state_id"],
                    "split_group_key": case["split_group_key"],
                    "teacher_class": case["qualification_class"],
                    "negative_stratum": case["negative_stratum"],
                    "rs_condition": rs_condition,
                    "off_action": off_action,
                    "on_action": on_action,
                    "function_blind_item_id": function_id,
                    "quality_blind_item_id": quality_id,
                    "quality_A_action": on_action if a_is_on else off_action,
                    "quality_B_action": off_action if a_is_on else on_action,
                    "risk_A_blind_item_id": "msrisk_" + stable(pair_id, "A", "RISK"),
                    "risk_B_blind_item_id": "msrisk_" + stable(pair_id, "B", "RISK"),
                }
            )

    function_items.sort(key=lambda row: stable("F_ORDER", row["blind_item_id"]))
    quality_items.sort(key=lambda row: stable("Q_ORDER", row["blind_item_id"]))
    risk_items.sort(key=lambda row: stable("R_ORDER", row["blind_item_id"]))
    private_map.sort(key=lambda row: row["pair_id"])
    OUT.mkdir(parents=True)
    function_path = OUT / "function_packet_blind.jsonl"
    quality_path = OUT / "quality_packet_blind.jsonl"
    risk_path = OUT / "risk_packet_blind.jsonl"
    map_path = OUT / "private_mapping.jsonl"
    write_rows(function_path, function_items)
    write_rows(quality_path, quality_items)
    write_rows(risk_path, risk_items)
    write_rows(map_path, private_map)

    provider_text = "\n".join(json.dumps(row, ensure_ascii=False) for row in [*function_items, *quality_items, *risk_items])
    forbidden = ("TEACHER_SUITABLE", "TEACHER_NOT_SUITABLE", "requested_action_id", "MS+R0", "MS+RS", "generator_claimed")
    checks = {
        "exact_denominators": len(function_items) == 32 and len(quality_items) == 32 and len(risk_items) == 64 and len(private_map) == 32,
        "two_rs_conditions_per_state": Counter(row["rs_condition"] for row in private_map) == Counter({"R0": 16, "RS": 16}),
        "balanced_teacher_classes_private_only": Counter(row["teacher_class"] for row in private_map) == Counter({"TEACHER_SUITABLE": 16, "TEACHER_NOT_SUITABLE": 16}),
        "private_assignment_absent_from_blind_packets": not any(token in provider_text for token in forbidden),
        "function_is_source_aware_pointwise": all(row["strictly_past_user_owned_source"] and row["response"] for row in function_items),
        "quality_is_same_state_paired_and_function_blind": all(row["response_A"] and row["response_B"] and "resource function" in row["decision"]["do_not_score"] for row in quality_items),
        "risk_requires_six_explicit_families": all(len(row["risk_families_explicit_0_to_3"]) == 6 for row in risk_items),
        "no_free_1_to_5_primary_score": "1–5" not in provider_text and "1-5" not in provider_text,
        "generator_telemetry_absent": "used_evidence_ids" not in provider_text and "evidence_id=" not in provider_text,
        "zero_api_materialization": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-measurement-packet-report-v1",
        "status": "PASS_BLIND_ANCHORED_PACKET_READY_FOR_INSTRUMENT_QUALIFICATION" if not failed else "FAIL_MEASUREMENT_FORBIDDEN",
        "checks": checks,
        "failed_checks": failed,
        "denominators": {"function_on_responses": 32, "quality_pairs": 32, "risk_absolute_responses": 64, "states": 16, "connected_groups": 8},
        "measurement_separation": {
            "function": "source-aware pointwise MS realization",
            "risk": "absolute literal events for both arms, six explicit families",
            "quality": "same-state same-seed paired material preference with function/risk/cost excluded",
            "safe_nonuse": "derived only after blind judgments: teacher-not-suitable plus NOT_USED_FINAL and no material risk is executor success",
        },
        "historical_rules_reused": [
            "generator telemetry is never function gold",
            "FUNCTIONAL needs source and response evidence",
            "wrong owner/time/boundary is not functional",
            "risk zero is explicit per family and absence of a deterministic hit is not proof of safety",
            "quality direction is within-state and does not double-count risk/function/cost",
            "unresolved is preserved and never silently mapped to OFF or safe",
        ],
        "artifacts": {
            "function": {"path": str(function_path.relative_to(ROOT)), "sha256": sha(function_path)},
            "quality": {"path": str(quality_path.relative_to(ROOT)), "sha256": sha(quality_path)},
            "risk": {"path": str(risk_path.relative_to(ROOT)), "sha256": sha(risk_path)},
            "private_mapping": {"path": str(map_path.relative_to(ROOT)), "sha256": sha(map_path)},
        },
        "source_hashes": {"authority": sha(AUTHORITY), "closeout": sha(CLOSEOUT), "cases": sha(CASES), "calls": sha(CALLS), "recovered_results": sha(RESULTS)},
        "api_calls": 0,
        "pm_fits": 0,
        "next": "QUALIFY_MEASUREMENT_INSTRUMENT_ON_PAST_ANCHORS_OR_TWO_IDENTIFIED_HUMANS_BEFORE_FINAL_EXECUTOR_VERDICT",
    }
    write(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
