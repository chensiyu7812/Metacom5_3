#!/usr/bin/env python3
"""Materialize (zero-API) the formal blind quality/risk measurement for the
MS-only ablation, using the EXACT SAME instrument as the EvoEmo and ESConv
measurements (v1_5_rs_ms_quality_risk_blind_review.py -- unmodified), for
genuine cross-track comparability. This isolates MS's own same_stack_outcome
criterion for the first time (previously confounded with RS).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import (  # noqa: E402
    RSMSQualityBlindReview,
    RSMSRiskBlindReview,
    quality_prompt_messages,
    risk_prompt_messages,
)

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
EXTERNAL_TEST_CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl"
EXTERNAL_TEST_RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_live_20260812/generator_results_private.jsonl"
MS_ONLY_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_only_ablation_live_20260812/generator_results_private.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_only_quality_risk_measurement_preflight_20260812"
STAGE = "paper1_ms_only_quality_risk_measurement_v1"
USD_CAP = 0.7

REVIEWER_ID = "MS_ONLY_QUALITY_RISK_INDEPENDENT_GPT56"
ENDPOINT_KEY = "openai_gpt_5_6_sol"


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("MS-only quality/risk measurement preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    if current["id"] != "MS_ONLY_ABLATION_EXECUTION":
        raise RuntimeError("MS-only ablation execution phase is not current")

    cases = {row["case_id"]: row for row in read_jsonl(EXTERNAL_TEST_CASES)}
    baselines = {row["case_id"]: row for row in read_jsonl(EXTERNAL_TEST_RESULTS) if row["is_baseline"]}
    ms_only = {row["case_id"]: row for row in read_jsonl(MS_ONLY_RESULTS)}
    if len(ms_only) != 19:
        raise RuntimeError(f"expected 19 MS-only results, found {len(ms_only)}")

    eligible_case_ids = sorted(
        case_id for case_id, row in ms_only.items()
        if row["execution_status"] in ("clean", "clean_safe_personal_nonuse")
        and baselines.get(case_id, {}).get("execution_status") in ("clean", "clean_trace_sanitized")
    )

    quality_items: list[dict[str, Any]] = []
    risk_items: list[dict[str, Any]] = []
    quality_plan: list[dict[str, Any]] = []
    risk_plan: list[dict[str, Any]] = []
    private_map: list[dict[str, Any]] = []

    for case_id in eligible_case_ids:
        case = cases[case_id]
        baseline = baselines[case_id]
        ms_routed = ms_only[case_id]
        dialogue = case["current_context"]

        pair_id = "msonlypair_" + stable_hex(case_id)
        a_is_routed = int(stable_hex("AB", pair_id, length=2), 16) % 2 == 0
        reply_a = ms_routed["final_reply"] if a_is_routed else baseline["final_reply"]
        reply_b = baseline["final_reply"] if a_is_routed else ms_routed["final_reply"]

        quality_id = "msonlyqual_" + stable_hex(pair_id, "QUALITY")
        quality_messages = quality_prompt_messages(pair_id=quality_id, dialogue=dialogue, reply_a=reply_a, reply_b=reply_b)
        quality_items.append({
            "protocol": "pm-v1.5-paper1-ms-only-quality-blind-pair-v1",
            "blind_item_id": quality_id,
            "dialogue": dialogue,
            "response_A": reply_a,
            "response_B": reply_b,
        })
        quality_plan.append({
            "protocol": "pm-v1.5-paper1-ms-only-quality-call-v1",
            "logical_call_id": "msonlyqualcall_" + stable_hex(REVIEWER_ID, quality_id),
            "kind": "quality",
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "item_id": quality_id,
            "messages": quality_messages,
            "messages_sha256": sha256_text(canonical_json(quality_messages)),
            "schema_sha256": sha256_text(canonical_json(RSMSQualityBlindReview.model_json_schema())),
            "seed": 20260813 + int(stable_hex(REVIEWER_ID, quality_id, length=8), 16) % 100000,
            "temperature": 0.0,
            "max_output_tokens": 500,
        })

        risk_ids = {}
        for label, reply in (("baseline", baseline["final_reply"]), ("routed", ms_routed["final_reply"])):
            risk_id = "msonlyrisk_" + stable_hex(pair_id, label, "RISK")
            risk_ids[label] = risk_id
            risk_messages = risk_prompt_messages(item_id=risk_id, dialogue=dialogue, reply=reply)
            risk_items.append({
                "protocol": "pm-v1.5-paper1-ms-only-risk-blind-item-v1",
                "blind_item_id": risk_id,
                "dialogue": dialogue,
                "response": reply,
            })
            risk_plan.append({
                "protocol": "pm-v1.5-paper1-ms-only-risk-call-v1",
                "logical_call_id": "msonlyriskcall_" + stable_hex(REVIEWER_ID, risk_id),
                "kind": "risk",
                "reviewer_id": REVIEWER_ID,
                "endpoint_key": ENDPOINT_KEY,
                "item_id": risk_id,
                "messages": risk_messages,
                "messages_sha256": sha256_text(canonical_json(risk_messages)),
                "schema_sha256": sha256_text(canonical_json(RSMSRiskBlindReview.model_json_schema())),
                "seed": 20260813 + int(stable_hex(REVIEWER_ID, risk_id, length=8), 16) % 100000,
                "temperature": 0.0,
                "max_output_tokens": 500,
            })

        private_map.append({
            "pair_id": pair_id,
            "case_id": case_id,
            "quality_blind_item_id": quality_id,
            "quality_A_arm": "routed" if a_is_routed else "baseline",
            "quality_B_arm": "baseline" if a_is_routed else "routed",
            "risk_baseline_blind_item_id": risk_ids["baseline"],
            "risk_routed_blind_item_id": risk_ids["routed"],
            "ms_only_execution_status": ms_routed["execution_status"],
        })

    risk_items.sort(key=lambda row: stable_hex("RISK_ORDER", row["blind_item_id"]))
    risk_plan.sort(key=lambda row: stable_hex("RISK_ORDER", row["item_id"]))
    quality_items.sort(key=lambda row: stable_hex("Q_ORDER", row["blind_item_id"]))
    quality_plan.sort(key=lambda row: stable_hex("Q_ORDER", row["item_id"]))
    private_map.sort(key=lambda row: row["pair_id"])

    plan = quality_plan + risk_plan
    provider_text = canonical_json([row["messages"] for row in plan])
    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "call_plan": [row["logical_call_id"] for row in plan],
            "call_plan_messages_sha256": [row["messages_sha256"] for row in plan],
        })
    )
    release_manifest = read_json(RELEASE_MANIFEST)
    consumed_identities = {
        str(record.get("approval_identity") or record.get("run_identity") or "")
        for record in [
            *(release_manifest.get("stage_consumptions") or {}).values(),
            *(release_manifest.get("prior_stage_attempts_history") or []),
            *(release_manifest.get("stage_consumptions_history") or []),
        ]
        if isinstance(record, dict)
    }

    forbidden = ("generator_claimed", "used_evidence_ids", "execution_status", "requested_action_id")
    checks = {
        "eligible_pairs_present": len(private_map) == 19,
        "exact_quality_items_match_pairs": len(quality_items) == len(private_map),
        "exact_risk_items_double_pairs": len(risk_items) == 2 * len(private_map),
        "quality_position_randomized": 0 < sum(1 for row in private_map if row["quality_A_arm"] == "routed") < len(private_map),
        "condition_absent_from_blind_packets": not any(token in provider_text for token in forbidden),
        "one_schema_per_kind": len({row["schema_sha256"] for row in quality_plan}) == 1 and len({row["schema_sha256"] for row in risk_plan}) == 1,
        "same_instrument_module_as_prior_measurements": True,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_label_zero_fit_zero_reexecution": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"MS-only quality/risk measurement preflight failed: {checks}")

    OUT.mkdir(parents=True)
    write_jsonl(OUT / "quality_packet_blind.jsonl", quality_items)
    write_jsonl(OUT / "risk_packet_blind.jsonl", risk_items)
    write_jsonl(OUT / "call_plan_private.jsonl", plan)
    write_jsonl(OUT / "private_mapping.jsonl", private_map)

    total_prompt_chars = sum(len(canonical_json(row["messages"])) for row in plan)
    est_input_tokens = total_prompt_chars / 4
    est_output_tokens = len(plan) * 220
    est_cost = (est_input_tokens / 1_000_000) * 5.0 + (est_output_tokens / 1_000_000) * 30.0

    report = {
        "protocol": "pm-v1.5-paper1-ms-only-quality-risk-measurement-preflight-v1",
        "status": "PASS_MEASUREMENT_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "design": (
            "Same instrument as the EvoEmo and ESConv quality/risk measurements "
            "(v1_5_rs_ms_quality_risk_blind_review.py, unmodified): position-randomized blind A/B "
            "pairwise quality, absolute independent per-response risk scoring. Scope: all 19 real "
            "baseline-vs-MS-only pairs, RS forced off in the routed arm -- first clean, unconfounded "
            "measurement of MS's own same_stack_outcome criterion."
        ),
        "reviewer_id": REVIEWER_ID,
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": len(plan),
            "quality_calls": len(quality_plan),
            "risk_calls": len(risk_plan),
            "maximum_physical_attempts": len(plan) * 2,
            "proposed_absolute_usd_cap": USD_CAP,
            "estimated_cost_usd": round(est_cost, 4),
            "scope": f"{len(quality_plan)} blind pairwise quality calls + {len(risk_plan)} absolute risk calls judging baseline (M0+R0) vs MS-only routed replies.",
        },
        "artifacts": {
            "quality_packet": {"path": str((OUT / "quality_packet_blind.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "quality_packet_blind.jsonl")},
            "risk_packet": {"path": str((OUT / "risk_packet_blind.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "risk_packet_blind.jsonl")},
            "call_plan": {"path": str((OUT / "call_plan_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "call_plan_private.jsonl")},
            "private_mapping": {"path": str((OUT / "private_mapping.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "private_mapping.jsonl")},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "external_test_cases": sha256_file(EXTERNAL_TEST_CASES),
            "external_test_results": sha256_file(EXTERNAL_TEST_RESULTS),
            "ms_only_results": sha256_file(MS_ONLY_RESULTS),
            "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_rs_ms_quality_risk_blind_review.py"),
        },
        "api_calls": 0,
        "next": "HUMAN_MUST_EXPLICITLY_APPROVE_THIS_EXACT_STAGE_RUN_IDENTITY_AND_COST_CAP",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
