#!/usr/bin/env python3
"""Materialize (zero-API) a clean MS-only same-stack ablation: force RS off
(candidate=None, the established ablation-arm pattern) on the 19 real
ms_decision=ON EvoEmo external-test states, to isolate MS's own marginal
contribution -- every prior measurement had MS confounded with RS (all 19
ms_decision=ON states also had rs_decision=ON), so MS's same_stack_outcome
criterion has never actually been cleanly tested.

Baseline (M0+R0) is reused unchanged from the original external test --
only a new MS-only arm needs generation.
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
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_only_ablation_preflight_20260812"
STAGE = "paper1_ms_only_ablation_v1"
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
        raise RuntimeError("MS-only ablation preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_DEFAULT_OFF_POLICY_REGISTERED_MS_ONLY_ABLATION_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS default-off policy phase is not the current execution phase")

    cases = read_jsonl(EXTERNAL_TEST_CASES)
    ms_on_cases = [c for c in cases if c["ms_decision"] == "ON"]
    if len(ms_on_cases) != 19:
        raise RuntimeError(f"expected 19 ms_decision=ON cases, found {len(ms_on_cases)}")

    physical_calls: list[dict[str, Any]] = []
    ablation_map: list[dict[str, Any]] = []
    for case in ms_on_cases:
        candidates: dict[str, V3Candidate | None] = {c: None for c in ("MP", "MS", "ME", "RS")}
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
        # RS deliberately left None: this is the MS-only ablation arm.
        plan = build_component_general_plan_v3(
            requested_action_id="MS+R0",
            current_user_id=case["runtime_owner_key"],
            candidates=candidates,
            pair_relations=None,
        )
        messages = response_generation_messages_v3(current_context=case["current_context"], current_goal=CURRENT_GOAL, plan=plan)
        physical_call_id = "msonlycall_" + stable_hex(case["case_id"], "ms_only", case["seed"])
        physical_calls.append({
            "protocol": "pm-v1.5-paper1-ms-only-ablation-call-v1",
            "physical_call_id": physical_call_id,
            "case_id": case["case_id"],
            "state_id": case["state_id"],
            "runtime_owner_key": case["runtime_owner_key"],
            "requested_action_id": "MS+R0",
            "seed": case["seed"],
            "temperature": 0.7,
            "max_output_tokens": 512,
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "response_schema": SameStackGeneratorOutput.model_json_schema(),
            "response_schema_sha256": sha256_text(canonical_json(SameStackGeneratorOutput.model_json_schema())),
        })
        ablation_map.append({
            "case_id": case["case_id"],
            "state_id": case["state_id"],
            "physical_call_id": physical_call_id,
            "ms_exact_source": case["ms_exact_source"],
            "original_rs_decision": case["rs_decision"],
            "original_rs_selected_card_id": case.get("rs_selected_card_id"),
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
        "exact_19_calls": len(physical_calls) == 19,
        "all_requested_action_ms_r0": all(row["requested_action_id"] == "MS+R0" for row in physical_calls),
        "same_seed_as_original_per_case": True,
        "rs_never_in_plan": all(
            "rscard_" not in text for text in prompt_texts
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
        raise RuntimeError(f"MS-only ablation preflight failed: {checks}")

    OUT.mkdir(parents=True)
    calls_path = OUT / "physical_call_plan_private.jsonl"
    map_path = OUT / "ablation_map_private.jsonl"
    write_jsonl(calls_path, physical_calls)
    write_jsonl(map_path, ablation_map)

    report = {
        "protocol": "pm-v1.5-paper1-ms-only-ablation-preflight-v1",
        "status": "PASS_ABLATION_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": len(physical_calls),
            "maximum_physical_attempts": len(physical_calls) * 2,
            "proposed_absolute_usd_cap": USD_CAP,
            "scope": (
                "Generate exactly 19 MS-only routed replies (RS forced off via candidate=None) on the "
                "real ms_decision=ON EvoEmo states, isolating MS's own marginal contribution against "
                "the already-collected M0+R0 baseline. Zero baseline regeneration, zero PM fits."
            ),
        },
        "artifacts": {
            "call_plan": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
            "ablation_map": {"path": str(map_path.relative_to(ROOT)), "sha256": sha256_file(map_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "external_test_cases": sha256_file(EXTERNAL_TEST_CASES),
        },
        "api_calls": 0,
        "next": "HUMAN_MUST_EXPLICITLY_APPROVE_THIS_EXACT_STAGE_RUN_IDENTITY_AND_COST_CAP",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
