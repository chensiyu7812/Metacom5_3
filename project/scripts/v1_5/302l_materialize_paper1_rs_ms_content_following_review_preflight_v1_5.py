#!/usr/bin/env python3
"""Materialize (zero-API) an independent content-following review of the
70-call RS+MS EvoEmo external test (300l).

Motivation: `generator_claimed` is derived purely from whether the weak 8B
generator echoed the exact internal evidence_id string in its structured
`used_evidence_ids` output -- a brittle citation mechanic. A direct read of
several routed replies where RS was "not claimed" showed content that
clearly followed the RS card's support_move (e.g. a real restatement of an
explicitly-described change), suggesting the claimed rate under-counts real
function. This round gets an independent reviewer (blind to
generator_claimed) to judge content-following directly, for every valid
routed call in the external test -- not just the disagreement cases, so the
result is a real correction factor, not cherry-picked confirmation.
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
from metacom_pm.v1_5_rs_ms_content_following_review import RSMSContentFollowingReview, prompt_messages  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
EXTERNAL_TEST_CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl"
EXTERNAL_TEST_RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_live_20260812/generator_results_private.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_content_following_review_preflight_20260812"
STAGE = "paper1_rs_ms_content_following_review_v1"
USD_CAP = 0.30

REVIEWER_ID = "RS_MS_CONTENT_FOLLOWING_INDEPENDENT_GPT56"
ENDPOINT_KEY = "openai_gpt_5_6_sol"

MS_MEANING_CUE = (
    "Interpret the single strictly past user-owned source supplied below as a "
    "tentative continuity cue; do not treat it as current or quote it."
)
MS_ALLOWED_CHANGE = "If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question."


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS+MS content-following review preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_MS_EVOEMO_EXTERNAL_TEST_COMPLETE_MECHANISM_CLEAN_LOW_UPTAKE_ON_WEAK_GENERATOR" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS+MS EvoEmo external test complete phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    cases = {row["case_id"]: row for row in read_jsonl(EXTERNAL_TEST_CASES)}
    results = read_jsonl(EXTERNAL_TEST_RESULTS)
    by_case: dict[str, dict[str, dict]] = {}
    for row in results:
        by_case.setdefault(row["case_id"], {})["baseline" if row["is_baseline"] else "routed"] = row

    eligible_case_ids = sorted(
        case_id
        for case_id, kinds in by_case.items()
        if "routed" in kinds
        and "baseline" in kinds
        and kinds["routed"]["execution_status"] in ("clean", "clean_safe_personal_nonuse")
    )

    plan: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    for case_id in eligible_case_ids:
        case = cases[case_id]
        routed = by_case[case_id]["routed"]
        baseline = by_case[case_id]["baseline"]
        ms_offered = case["ms_decision"] == "ON"
        rs_offered = case["rs_decision"] == "ON" and bool(case.get("rs_selected_card_id"))
        ms_guidance = (
            {
                "meaning_cue": MS_MEANING_CUE,
                "past_source_text": case["ms_exact_source"],
                "allowed_response_change": MS_ALLOWED_CHANGE,
            }
            if ms_offered
            else None
        )
        rs_guidance = (
            {
                "strategy_family": case["rs_selected_family"],
                "support_move": case["rs_support_move"],
                "prompt_guidance": case["rs_prompt_guidance"],
            }
            if rs_offered
            else None
        )
        messages = prompt_messages(
            case_id=case_id,
            baseline_reply=baseline["final_reply"],
            routed_reply=routed["final_reply"],
            ms_offered=ms_offered,
            ms_guidance=ms_guidance,
            rs_offered=rs_offered,
            rs_guidance=rs_guidance,
        )
        anchors.append({
            "protocol": "pm-v1.5-paper1-rs-ms-content-following-anchor-v1",
            "case_id": case_id,
            "ms_offered": ms_offered,
            "rs_offered": rs_offered,
            "generator_claimed": routed["generator_claimed"],
            "baseline_reply": baseline["final_reply"],
            "routed_reply": routed["final_reply"],
        })
        plan.append({
            "protocol": "pm-v1.5-paper1-rs-ms-content-following-call-v1",
            "logical_call_id": "rsmscfcall_" + stable_hex(REVIEWER_ID, case_id),
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "case_id": case_id,
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "schema_sha256": sha256_text(canonical_json(RSMSContentFollowingReview.model_json_schema())),
            "seed": 20260812 + int(stable_hex(REVIEWER_ID, case_id, length=8), 16) % 100000,
            "temperature": 0.0,
            "max_output_tokens": 500,
        })

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

    checks = {
        "unique_current_execution_pointer": alias.get("compatibility_alias_of") == "current_execution_phase",
        "exact_23_eligible_calls": len(plan) == 23,
        "every_call_has_baseline_and_routed_reply": all(a["baseline_reply"] and a["routed_reply"] for a in anchors),
        "at_least_one_offered_per_call": all(a["ms_offered"] or a["rs_offered"] for a in anchors),
        "generator_claimed_not_shown_to_reviewer": all(
            "claimed" not in text.lower() and "generator_claimed" not in text
            for text in (canonical_json(row["messages"]) for row in plan)
        ),
        "one_strict_schema": len({row["schema_sha256"] for row in plan}) == 1,
        "strict_schema_constructs_cleanly": True,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_label_zero_fit_zero_pm_refit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"RS+MS content-following review preflight failed: {checks}")

    OUT.mkdir(parents=True)
    anchors_path = OUT / "anchors_private.jsonl"
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(anchors_path, anchors)
    write_jsonl(plan_path, plan)

    # Rough cost estimate from actual prompt char counts (no API call).
    total_prompt_chars = sum(len(canonical_json(row["messages"])) for row in plan)
    est_input_tokens = total_prompt_chars / 4
    est_output_tokens = len(plan) * 220
    est_cost = (est_input_tokens / 1_000_000) * 5.0 + (est_output_tokens / 1_000_000) * 30.0

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-content-following-review-preflight-v1",
        "status": "PASS_REVIEW_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "diagnostic_motivation": (
            "generator_claimed only reflects whether the weak 8B generator echoed the exact "
            "internal evidence_id string into used_evidence_ids -- a brittle citation mechanic, "
            "not a semantic judgment. Direct reading of several 'RS not claimed' routed replies "
            "showed clear content-level following of the RS card's support_move. This round "
            "reviews content-following directly and independently (blind to generator_claimed) "
            "for all 23 valid-structured-output routed calls in the external test, in both "
            "directions (claimed=True and claimed=False), to produce a real correction factor "
            "rather than cherry-picked confirmation."
        ),
        "reviewer_id": REVIEWER_ID,
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": len(plan),
            "maximum_physical_attempts": len(plan) * 2,
            "proposed_absolute_usd_cap": USD_CAP,
            "estimated_cost_usd": round(est_cost, 4),
            "scope": (
                "Exactly 23 independent reviewer calls judging RS/MS content-following on real "
                "routed-vs-baseline reply pairs from the completed RS+MS EvoEmo external test "
                "(300l). Zero labels created, zero PM fits, zero re-execution of the external "
                "test -- diagnostic/measurement-correction only."
            ),
        },
        "artifacts": {
            "anchors": {"path": str(anchors_path.relative_to(ROOT)), "sha256": sha256_file(anchors_path)},
            "call_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "external_test_cases": sha256_file(EXTERNAL_TEST_CASES),
            "external_test_results": sha256_file(EXTERNAL_TEST_RESULTS),
            "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_rs_ms_content_following_review.py"),
        },
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "next": "HUMAN_MUST_EXPLICITLY_APPROVE_THIS_EXACT_STAGE_RUN_IDENTITY_AND_COST_CAP_IN_THE_CENTRAL_RELEASE_MANIFEST",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
