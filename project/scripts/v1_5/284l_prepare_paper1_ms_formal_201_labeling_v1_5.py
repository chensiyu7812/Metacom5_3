#!/usr/bin/env python3
"""Propose (zero-API) the formal 201-item x 2-reviewer dual-model source-aware
labeling pass, using the qualified pairing (GPT-5.6 primary + Claude Haiku 4.5
challenger, per paper1_ms_qualification_final_decision_v1.json). Reuses the
already-materialized public/private packet (260l) -- no new item authoring.

Fresh reviewer identities (not reused from any qualification round). Consensus
rule at audit time will be binary-collapsed exact agreement only (SEMANTIC_
ABSTAIN and NOT_SUITABLE both count as "do not use" for agreement purposes;
disagreement stays unlabeled), matching the qualification decision. This
script only builds the call plan and a calibrated real cost estimate; it makes
zero API calls, creates zero labels, and fits zero models.
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
from metacom_pm.v1_5_ms_source_annotated_suitability_review import (  # noqa: E402
    MSSourceAnnotatedSuitabilityReview,
    prompt_messages,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PACKET = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/ms_reannotation_packet_blind.jsonl"
PRIVATE_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812/ms_reannotation_private_key.jsonl"
QUALIFICATION_DECISION = ROOT / "data/pm_v1_5_contracts/paper1_ms_qualification_final_decision_v1.json"
ENDPOINTS = ROOT / "configs/paper1_ms_formal_201_labeling_endpoints_v1.json"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_formal_201_labeling_preflight_20260812"
STAGE = "paper1_ms_formal_201_labeling_v1"

PRIMARY_REVIEWER_ID = "MS_FORMAL_PRIMARY_GPT56"
CHALLENGER_REVIEWER_ID = "MS_FORMAL_CHALLENGER_CLAUDE_HAIKU"
PRIMARY_ENDPOINT_KEY = "openai_gpt_5_6_sol"
CHALLENGER_ENDPOINT_KEY = "anthropic_claude_haiku_4_5_challenger"

# Calibrated from this session's real completed calls against the same review
# instrument: GPT-5.6 round-3 (12 calls, 17467 prompt + 3489 completion tokens)
# and Claude Haiku round-5 (12 calls, 30772 prompt + 5689 completion tokens).
# Using per-call token counts directly (not a generic chars-per-token guess)
# scaled to real item text length ratios computed below.
REAL_CALIBRATION = {
    PRIMARY_ENDPOINT_KEY: {"prompt_tokens_per_call": 17467 / 12, "completion_tokens_per_call": 3489 / 12, "calibration_char_total": None},
    CHALLENGER_ENDPOINT_KEY: {"prompt_tokens_per_call": 30772 / 12, "completion_tokens_per_call": 5689 / 12, "calibration_char_total": None},
}


def _stable(*parts: str, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("formal labeling preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "MS_QUALIFIED_FORMAL_201_LABELING_DESIGN_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("qualified-formal-labeling-design phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    decision = read_json(QUALIFICATION_DECISION)
    if decision["status"] != "MS_QUALIFIED_PRIMARY_GPT56_CHALLENGER_CLAUDE_HAIKU_4_5":
        raise RuntimeError("qualification decision is not in the expected qualified state")

    packet = read_jsonl(PACKET)
    private = {row["repair_item_id"]: row for row in read_jsonl(PRIVATE_KEY)}
    if len(packet) != 201 or len(private) != 201:
        raise RuntimeError("exact 201-item packet required")
    if {row["repair_item_id"] for row in packet} != set(private.keys()):
        raise RuntimeError("packet and private key repair_item_id sets do not match exactly")

    endpoints = read_json(ENDPOINTS)
    request = endpoints["request_contract"]
    endpoint_records = endpoints["candidates"]

    plan: list[dict[str, Any]] = []
    reviewer_specs = [
        (PRIMARY_REVIEWER_ID, PRIMARY_ENDPOINT_KEY),
        (CHALLENGER_REVIEWER_ID, CHALLENGER_ENDPOINT_KEY),
    ]
    total_prompt_chars_by_endpoint: dict[str, int] = {key: 0 for _, key in reviewer_specs}
    for item in packet:
        for reviewer_id, endpoint_key in reviewer_specs:
            messages = prompt_messages(item, reviewer_id)
            messages_text = "".join(m["content"] for m in messages)
            total_prompt_chars_by_endpoint[endpoint_key] += len(messages_text)
            plan.append({
                "protocol": "pm-v1.5-paper1-ms-formal-201-labeling-call-v1",
                "logical_call_id": "msformalcall_" + _stable(reviewer_id, item["repair_item_id"]),
                "reviewer_id": reviewer_id,
                "endpoint_key": endpoint_key,
                "model": endpoint_records[endpoint_key]["model"],
                "repair_item_id": item["repair_item_id"],
                "messages": messages,
                "messages_sha256": sha256_text(canonical_json(messages)),
                "schema_sha256": sha256_text(canonical_json(MSSourceAnnotatedSuitabilityReview.model_json_schema())),
                "seed": int(request["seed"]) + int(_stable(reviewer_id, item["repair_item_id"], length=8), 16) % 100000,
                "temperature": request["temperature"],
                "max_output_tokens": request["max_output_tokens"],
            })
    plan.sort(key=lambda row: row["logical_call_id"])
    if len(plan) != 402 or len({row["logical_call_id"] for row in plan}) != 402:
        raise RuntimeError("exact 402 unique calls required")

    # Calibrate real token counts from this session's own completed calls against
    # this exact review instrument, scaled by this pack's real prompt char totals
    # relative to the 12-item qualification round's real prompt char totals, so
    # the estimate reflects the real 201-item text (not a generic char/token
    # assumption).
    qualification_prompt_chars = {
        PRIMARY_ENDPOINT_KEY: sum(
            len("".join(m["content"] for m in prompt_messages(row, PRIMARY_REVIEWER_ID)))
            for row in read_jsonl(ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_20260812/realistic_anchor_controls_blind.jsonl")
        ),
        CHALLENGER_ENDPOINT_KEY: sum(
            len("".join(m["content"] for m in prompt_messages(row, CHALLENGER_REVIEWER_ID)))
            for row in read_jsonl(ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_20260812/realistic_anchor_controls_blind.jsonl")
        ),
    }
    cost_by_endpoint: dict[str, dict[str, float]] = {}
    total_cost = 0.0
    for endpoint_key in (PRIMARY_ENDPOINT_KEY, CHALLENGER_ENDPOINT_KEY):
        calib = REAL_CALIBRATION[endpoint_key]
        avg_chars_per_call_201 = total_prompt_chars_by_endpoint[endpoint_key] / 201
        avg_chars_per_call_12 = qualification_prompt_chars[endpoint_key] / 12
        real_ratio = avg_chars_per_call_201 / avg_chars_per_call_12
        est_prompt_tokens_per_call = calib["prompt_tokens_per_call"] * real_ratio
        est_completion_tokens_per_call = calib["completion_tokens_per_call"]  # output length driven by schema, not input length
        n_calls = 201
        prompt_cost = est_prompt_tokens_per_call * n_calls / 1_000_000 * endpoint_records[endpoint_key]["input_usd_per_million_tokens"]
        completion_cost = est_completion_tokens_per_call * n_calls / 1_000_000 * endpoint_records[endpoint_key]["output_usd_per_million_tokens"]
        cost_by_endpoint[endpoint_key] = {
            "estimated_prompt_tokens_per_call": round(est_prompt_tokens_per_call, 1),
            "estimated_completion_tokens_per_call": round(est_completion_tokens_per_call, 1),
            "estimated_cost_usd": round(prompt_cost + completion_cost, 4),
        }
        total_cost += prompt_cost + completion_cost

    usd_cap = round(total_cost * 1.6 + 1.0, 2)  # generous safety margin over the calibrated estimate

    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "packet_sha256": sha256_file(PACKET),
            "private_key_sha256": sha256_file(PRIVATE_KEY),
            "endpoints_sha256": sha256_file(ENDPOINTS),
            "qualification_decision_sha256": sha256_file(QUALIFICATION_DECISION),
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

    provider_text = canonical_json([row["messages"] for row in plan])
    checks = {
        "unique_current_execution_pointer": alias.get("compatibility_alias_of") == "current_execution_phase",
        "qualification_decision_is_qualified": decision["status"] == "MS_QUALIFIED_PRIMARY_GPT56_CHALLENGER_CLAUDE_HAIKU_4_5",
        "exact_201_item_packet": len(packet) == 201,
        "exact_402_calls_two_reviewers": len(plan) == 402,
        "fresh_reviewer_identities_not_reused_from_qualification": {PRIMARY_REVIEWER_ID, CHALLENGER_REVIEWER_ID}.isdisjoint({"MS_ANCHOR_PRIMARY_GPT56", "MS_ANCHOR_CHALLENGER_GEMINI", "MS_ANCHOR_CHALLENGER_GEMINI_THINKING", "MS_ANCHOR_CHALLENGER_CLAUDE_HAIKU"}),
        "one_strict_schema": len({row["schema_sha256"] for row in plan}) == 1,
        "gold_never_provider_visible": all(
            term not in provider_text
            for term in ("teacher_decision", "binary_suitability_label", "actual_rank1_id", "gold_decision", "runtime_owner_key", "split_group_key")
        ),
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_label_zero_fit": True,
    }
    if not all(v is True for v in checks.values()):
        raise RuntimeError(f"formal labeling preflight failed: {checks}")

    OUT.mkdir(parents=True)
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-ms-formal-201-labeling-preflight-v1",
        "status": "PASS_EXACT_402_CALL_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "reviewers": {"primary": PRIMARY_REVIEWER_ID, "challenger": CHALLENGER_REVIEWER_ID},
        "consensus_rule_for_audit_time": "binary_collapsed_exact_agreement_only: SEMANTIC_ABSTAIN and NOT_SUITABLE both count as DO_NOT_USE for agreement; a primary label is only emitted when both reviewers' collapsed decisions match, otherwise the item stays unlabeled",
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": 402,
            "maximum_physical_attempts": 804,
            "proposed_absolute_usd_cap": usd_cap,
            "calibrated_cost_estimate_usd": round(total_cost, 4),
            "cost_by_endpoint": cost_by_endpoint,
            "scope": (
                "Exactly 402 calls (201 items x 2 qualified reviewers: GPT-5.6 primary, "
                "Claude Haiku 4.5 challenger) against the already-materialized 201-item public "
                "packet. No new item authoring, no rubric changes. Produces the formal MS "
                "training-label candidate set (exact-agreement-only, binary-collapsed)."
            ),
        },
        "artifacts": {
            "call_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "packet": sha256_file(PACKET),
            "private_key": sha256_file(PRIVATE_KEY),
            "endpoints": sha256_file(ENDPOINTS),
            "qualification_decision": sha256_file(QUALIFICATION_DECISION),
            "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_ms_source_annotated_suitability_review.py"),
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
