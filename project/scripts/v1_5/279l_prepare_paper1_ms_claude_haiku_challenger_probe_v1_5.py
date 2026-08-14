#!/usr/bin/env python3
"""Propose (zero-API) a 12-call Claude Haiku 4.5 challenger-model-swap probe.

Only the challenger side is re-tested. GPT-5.6 primary already passed
(10/12) in the realistic-anchor round (paper1_ms_realistic_anchor_qualification_v1,
outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_live_20260812/) against the
exact same 12-item control set with an unchanged config -- re-spending money to
reproduce an already-real, already-verified result would not test anything new.
This probe isolates the one real variable under test: does a genuinely
independent challenger model family (Anthropic Claude Haiku 4.5, vs the
Google Gemini 2.5 Flash family used in every prior round) fix the systematic
bias toward inventing an UNDERSTANDING framing? The gemini-thinking probe
(paper1_ms_gemini_thinking_probe_v1) already ruled out insufficient thinking
budget as the cause (7/12 -> 7/12, delta=0, despite 9290 real thinking
tokens spent), so this is the next candidate fix. Uses a fresh reviewer
identity and a dedicated endpoint config that does not touch the hash-bound
paper1_ms_source_annotated_review_endpoints_v1.json.
"""

from __future__ import annotations

from collections import Counter
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
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_20260812/realistic_anchor_controls_blind.jsonl"
CONTROL_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_private_20260812/realistic_anchor_key.jsonl"
PRIOR_AUDIT = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_audit_20260812/report.json"
ENDPOINTS = ROOT / "configs/paper1_ms_claude_haiku_challenger_endpoints_v1.json"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_claude_haiku_challenger_probe_preflight_20260812"
STAGE = "paper1_ms_claude_haiku_challenger_probe_v1"
USD_CAP = 0.75

REVIEWER_ID = "MS_ANCHOR_CHALLENGER_CLAUDE_HAIKU"
ENDPOINT_KEY = "anthropic_claude_haiku_4_5_challenger"


def _stable(*parts: str, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("probe preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "MS_CHALLENGER_MODEL_SWAP_RECOMMENDED_USER_DECISION_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("challenger-model-swap-recommended phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    prior_audit = read_json(PRIOR_AUDIT)
    if prior_audit["gates"]["primary_all_12_schema_and_local_valid"] is not True:
        raise RuntimeError("prior round's GPT-5.6 primary result is not a complete, transport-valid 12/12 -- cannot reuse it")

    controls = read_jsonl(CONTROLS)
    key = {row["repair_item_id"]: row for row in read_jsonl(CONTROL_KEY)}
    if not (len(controls) == len(key) == 12):
        raise RuntimeError("exact 12 controls required")

    endpoints = read_json(ENDPOINTS)
    request = endpoints["request_contract"]
    endpoint = endpoints["candidates"][ENDPOINT_KEY]
    plan: list[dict[str, Any]] = []
    for item in controls:
        messages = prompt_messages(item, REVIEWER_ID)
        plan.append({
            "protocol": "pm-v1.5-paper1-ms-claude-haiku-challenger-probe-call-v1",
            "logical_call_id": "msclaudehaikuchallengercall_" + _stable(REVIEWER_ID, item["repair_item_id"]),
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "model": endpoint["model"],
            "repair_item_id": item["repair_item_id"],
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "schema_sha256": sha256_text(canonical_json(MSSourceAnnotatedSuitabilityReview.model_json_schema())),
            "seed": int(request["seed"]) + int(_stable(REVIEWER_ID, item["repair_item_id"], length=8), 16) % 100000,
            "temperature": request["temperature"],
            "max_output_tokens": request["max_output_tokens"],
        })
    plan.sort(key=lambda row: row["logical_call_id"])
    provider_text = canonical_json([row["messages"] for row in plan])
    gold_counts = Counter(row["expected_final_suitability"] for row in key.values())

    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "controls_sha256": sha256_file(CONTROLS),
            "control_key_sha256": sha256_file(CONTROL_KEY),
            "endpoints_sha256": sha256_file(ENDPOINTS),
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
        "exact_12_blind_controls": len(controls) == 12,
        "exact_12_single_family_calls": len(plan) == 12 and len({row["logical_call_id"] for row in plan}) == 12,
        "single_reviewer_fresh_identity": REVIEWER_ID == "MS_ANCHOR_CHALLENGER_CLAUDE_HAIKU",
        "control_distribution_5_5_2": gold_counts == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2},
        "gold_never_provider_visible": all(
            term not in provider_text
            for term in ("expected_final_suitability", "expected_decision_reason_code", "not_training", "repair_family", "grounded_in_real_label")
        ),
        "one_strict_schema": len({row["schema_sha256"] for row in plan}) == 1,
        "challenger_model_family_is_anthropic_not_google": endpoint["family"].startswith("anthropic_"),
        "prior_primary_result_reused_not_respent": prior_audit["gates"]["primary_all_12_schema_and_local_valid"] is True,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_label_zero_fit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"probe preflight failed: {checks}")

    OUT.mkdir(parents=True)
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-ms-claude-haiku-challenger-probe-preflight-v1",
        "status": "PASS_EXACT_12_CALL_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "reviewer_id": REVIEWER_ID,
        "reused_gpt56_result_from": {
            "path": str(PRIOR_AUDIT.relative_to(ROOT)),
            "sha256": sha256_file(PRIOR_AUDIT),
            "primary_exact": prior_audit["reviewers"]["MS_ANCHOR_PRIMARY_GPT56"]["exact_decisions"],
            "primary_denominator": 12,
        },
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": 12,
            "maximum_physical_attempts": 24,
            "proposed_absolute_usd_cap": USD_CAP,
            "scope": (
                "Exactly 12 Claude Haiku 4.5 (anthropic_messages, strict tool use) calls "
                "against the same 12-item realistic anchor set, fresh reviewer identity. "
                "Tests whether a genuinely independent challenger model family (Anthropic "
                "vs the Google Gemini family used in every prior round) fixes the "
                "systematic bias found in the last 3 rounds. GPT-5.6 primary side is not "
                "re-called; its already-real 10/12 result from the realistic-anchor round "
                "is reused for the combined gate."
            ),
        },
        "artifacts": {
            "call_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "controls": sha256_file(CONTROLS),
            "control_key_private": sha256_file(CONTROL_KEY),
            "endpoints": sha256_file(ENDPOINTS),
            "prior_audit": sha256_file(PRIOR_AUDIT),
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
