#!/usr/bin/env python3
"""Materialize (zero-API) a regeneration of the 31 external-test routed
calls that selected a 'Restatement or Paraphrasing' card, swapping only the
RS candidate's meaning_cue for the warm-close variant text (308l) -- MS
candidate (if any), seed, dialogue, and requested_action_id are byte-
identical to the original external test, so this isolates exactly one
variable: the RS instruction text.

Baseline replies are NOT regenerated (baseline never depends on RS content)
-- the original 34 baseline replies are reused directly for the quality
re-measurement.
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
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v3 import response_generation_messages_v3  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
EXTERNAL_TEST_CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl"
VARIANTS = ROOT / "outputs/pm_v1_5_restatement_family_warm_close_variant_20260812/restatement_warm_close_variants.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_restatement_warm_close_regeneration_preflight_20260812"
STAGE = "paper1_rs_ms_restatement_warm_close_regeneration_v1"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."
USD_CAP = 0.15

MS_MEANING_CUE = (
    "Interpret the single strictly past user-owned source supplied below as a "
    "tentative continuity cue; do not treat it as current or quote it."
)
MS_ALLOWED_CHANGE = "If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("restatement warm-close regeneration preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_MS_QUALITY_RISK_COST_MEASURED_CLAIM_NOT_SUPPORTED_RESTATEMENT_FAMILY_ROOT_CAUSE_MP_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("quality/risk/cost-measured phase is not current")

    cases = read_jsonl(EXTERNAL_TEST_CASES)
    variant_by_card = {row["card_id"]: row for row in read_jsonl(VARIANTS)}

    affected = [c for c in cases if c.get("rs_selected_card_id") in variant_by_card]
    if len(affected) != 31:
        raise RuntimeError(f"expected 31 Restatement-affected cases, found {len(affected)}")

    physical_calls: list[dict[str, Any]] = []
    regen_map: list[dict[str, Any]] = []
    for case in affected:
        variant = variant_by_card[case["rs_selected_card_id"]]
        candidates: dict[str, V3Candidate | None] = {c: None for c in ("MP", "MS", "ME", "RS")}
        if case["ms_decision"] == "ON":
            candidates["MS"] = V3Candidate(
                component="MS",
                evidence_id=case["ms_evidence_id"],
                meaning_cue=MS_MEANING_CUE,
                exact_source=case["ms_exact_source"],
                owner_id=case["runtime_owner_key"],
                time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT",
                allowed_response_change=MS_ALLOWED_CHANGE,
                forbidden_inference=MS_FORBIDDEN,
                burden_units=1,
            )
        candidates["RS"] = V3Candidate(
            component="RS",
            evidence_id=case["rs_evidence_id"],
            meaning_cue=variant["variant_prompt_guidance"],
            exact_source=f"Strategy card ({case['rs_selected_family']}): {case['rs_support_move']}",
            owner_id=None,
            time_status="CURRENT_STRATEGY_CARD",
            allowed_response_change=f"Make the reply's primary act reflect this technique: {case['rs_support_move']}",
            forbidden_inference=case["rs_when_not_to_use"],
            burden_units=1,
        )
        plan = build_component_general_plan_v3(
            requested_action_id=case["routed_action_id"],
            current_user_id=case["runtime_owner_key"],
            candidates=candidates,
            pair_relations={"MS-RS": "COMPLEMENTARY"} if case["ms_decision"] == "ON" else None,
        )
        messages = response_generation_messages_v3(
            current_context=case["current_context"],
            current_goal=CURRENT_GOAL,
            plan=plan,
        )
        physical_call_id = "rswarmcall_" + stable_hex(case["case_id"], "warm_close", case["seed"])
        physical_calls.append({
            "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-regeneration-call-v1",
            "physical_call_id": physical_call_id,
            "case_id": case["case_id"],
            "state_id": case["state_id"],
            "runtime_owner_key": case["runtime_owner_key"],
            "requested_action_id": case["routed_action_id"],
            "seed": case["seed"],
            "temperature": 0.7,
            "max_output_tokens": 512,
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "response_schema": SameStackGeneratorOutput.model_json_schema(),
            "response_schema_sha256": sha256_text(canonical_json(SameStackGeneratorOutput.model_json_schema())),
        })
        regen_map.append({
            "case_id": case["case_id"],
            "state_id": case["state_id"],
            "physical_call_id": physical_call_id,
            "rs_selected_card_id": case["rs_selected_card_id"],
            "rs_selected_family": case["rs_selected_family"],
            "original_prompt_guidance": variant["original_prompt_guidance"],
            "variant_prompt_guidance": variant["variant_prompt_guidance"],
        })

    prompt_texts = [canonical_json(row["messages"]) for row in physical_calls]
    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "call_plan": [row["physical_call_id"] for row in physical_calls],
            "call_plan_messages_sha256": [row["messages_sha256"] for row in physical_calls],
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

    checks = {
        "exact_31_calls": len(physical_calls) == 31,
        "same_seed_as_original_per_case": all(
            row["seed"] == next(c["seed"] for c in cases if c["case_id"] == row["case_id"])
            for row in physical_calls
        ),
        "same_requested_action_as_original": all(
            row["requested_action_id"] == next(c["routed_action_id"] for c in cases if c["case_id"] == row["case_id"])
            for row in physical_calls
        ),
        "warm_close_text_present_in_prompt": all(
            "brief warm acknowledgment of continued presence" in text for text in prompt_texts
        ),
        "old_minimal_dialogic_clause_absent": all(
            "Execute only this support move in one concise sentence" not in text
            and "leave room for correction only when ambiguity matters" not in text
            for text in prompt_texts
        ),
        "response_schema_frozen": len({row["response_schema_sha256"] for row in physical_calls}) == 1,
        "no_api_calls": True,
        "no_pm_refit": True,
        "no_baseline_regeneration": True,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"restatement warm-close regeneration preflight failed: {checks}")

    OUT.mkdir(parents=True)
    calls_path = OUT / "physical_call_plan_private.jsonl"
    map_path = OUT / "regeneration_map_private.jsonl"
    write_jsonl(calls_path, physical_calls)
    write_jsonl(map_path, regen_map)

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-regeneration-preflight-v1",
        "status": "PASS_REGENERATION_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": len(physical_calls),
            "maximum_physical_attempts": len(physical_calls) * 2,
            "proposed_absolute_usd_cap": USD_CAP,
            "scope": (
                "Regenerate exactly 31 routed replies (the Restatement-or-Paraphrasing-family "
                "subset of the external test's 34 pairs) with the RS guidance text swapped to the "
                "warm-close variant (308l) -- everything else (MS candidate, seed, dialogue, "
                "requested_action_id) byte-identical to the original external test. Zero baseline "
                "regeneration, zero PM fits, zero label changes."
            ),
        },
        "artifacts": {
            "call_plan": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
            "regeneration_map": {"path": str(map_path.relative_to(ROOT)), "sha256": sha256_file(map_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "external_test_cases": sha256_file(EXTERNAL_TEST_CASES),
            "variants": sha256_file(VARIANTS),
        },
        "api_calls": 0,
        "next": "HUMAN_MUST_EXPLICITLY_APPROVE_THIS_EXACT_STAGE_RUN_IDENTITY_AND_COST_CAP",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
