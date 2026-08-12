#!/usr/bin/env python3
"""Materialize (zero-API) the quality-only re-measurement of the 31 warm-
close-variant regenerated replies against the SAME original baseline
replies, reusing the same blind pairwise instrument (position-randomized
A/B) as the original measurement (305l/306l). Risk is not re-measured --
it was not the identified problem (both arms were already low and roughly
flat) and the RS guidance change here does not touch MS/personal-fact
content.
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
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import RSMSQualityBlindReview, quality_prompt_messages  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
EXTERNAL_TEST_CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl"
EXTERNAL_TEST_RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_live_20260812/generator_results_private.jsonl"
REGEN_RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_ms_restatement_warm_close_regeneration_live_20260812/generator_results_private.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_restatement_warm_close_requality_preflight_20260812"
STAGE = "paper1_rs_ms_restatement_warm_close_requality_v1"
USD_CAP = 0.5

REVIEWER_ID = "RS_MS_WARM_CLOSE_REQUALITY_INDEPENDENT_GPT56"
ENDPOINT_KEY = "openai_gpt_5_6_sol"


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("restatement warm-close requality preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    if current["id"] != "RS_MS_RESTATEMENT_WARM_CLOSE_REGENERATION_EXECUTION":
        raise RuntimeError("regeneration execution phase is not current")

    cases = {row["case_id"]: row for row in read_jsonl(EXTERNAL_TEST_CASES)}
    baselines = {row["case_id"]: row for row in read_jsonl(EXTERNAL_TEST_RESULTS) if row["is_baseline"]}
    regenerated = {row["case_id"]: row for row in read_jsonl(REGEN_RESULTS)}
    if len(regenerated) != 31:
        raise RuntimeError(f"expected 31 regenerated replies, found {len(regenerated)}")

    quality_items: list[dict[str, Any]] = []
    quality_plan: list[dict[str, Any]] = []
    private_map: list[dict[str, Any]] = []

    for case_id, new_routed in sorted(regenerated.items()):
        case = cases[case_id]
        baseline = baselines[case_id]
        dialogue = case["current_context"]

        pair_id = "rswarmqpair_" + stable_hex(case_id)
        a_is_routed = int(stable_hex("AB", pair_id, length=2), 16) % 2 == 0
        reply_a = new_routed["final_reply"] if a_is_routed else baseline["final_reply"]
        reply_b = baseline["final_reply"] if a_is_routed else new_routed["final_reply"]

        quality_id = "rswarmqual_" + stable_hex(pair_id, "QUALITY")
        messages = quality_prompt_messages(pair_id=quality_id, dialogue=dialogue, reply_a=reply_a, reply_b=reply_b)
        quality_items.append({
            "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-requality-blind-pair-v1",
            "blind_item_id": quality_id,
            "dialogue": dialogue,
            "response_A": reply_a,
            "response_B": reply_b,
        })
        quality_plan.append({
            "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-requality-call-v1",
            "logical_call_id": "rswarmqcall_" + stable_hex(REVIEWER_ID, quality_id),
            "kind": "quality",
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "item_id": quality_id,
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "schema_sha256": sha256_text(canonical_json(RSMSQualityBlindReview.model_json_schema())),
            "seed": 20260812 + int(stable_hex(REVIEWER_ID, quality_id, length=8), 16) % 100000,
            "temperature": 0.0,
            "max_output_tokens": 500,
        })
        private_map.append({
            "pair_id": pair_id,
            "case_id": case_id,
            "quality_blind_item_id": quality_id,
            "quality_A_arm": "new_routed" if a_is_routed else "baseline",
            "quality_B_arm": "baseline" if a_is_routed else "new_routed",
        })

    quality_items.sort(key=lambda row: stable_hex("Q_ORDER", row["blind_item_id"]))
    quality_plan.sort(key=lambda row: stable_hex("Q_ORDER", row["item_id"]))
    private_map.sort(key=lambda row: row["pair_id"])

    provider_text = canonical_json([row["messages"] for row in quality_plan])
    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "call_plan": [row["logical_call_id"] for row in quality_plan],
            "call_plan_messages_sha256": [row["messages_sha256"] for row in quality_plan],
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

    forbidden = ("generator_claimed", "used_evidence_ids", "execution_status", "TEACHER_", "requested_action_id")
    checks = {
        "exact_31_pairs": len(private_map) == 31,
        "exact_31_quality_items": len(quality_items) == 31,
        "quality_position_randomized": 8 < sum(1 for row in private_map if row["quality_A_arm"] == "new_routed") < 23,
        "condition_absent_from_blind_packets": not any(token in provider_text for token in forbidden),
        "one_schema": len({row["schema_sha256"] for row in quality_plan}) == 1,
        "strict_schema_constructs_cleanly": True,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_label_zero_fit_zero_reexecution": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"restatement warm-close requality preflight failed: {checks}")

    OUT.mkdir(parents=True)
    write_jsonl(OUT / "quality_packet_blind.jsonl", quality_items)
    write_jsonl(OUT / "call_plan_private.jsonl", quality_plan)
    write_jsonl(OUT / "private_mapping.jsonl", private_map)

    total_prompt_chars = sum(len(canonical_json(row["messages"])) for row in quality_plan)
    est_input_tokens = total_prompt_chars / 4
    est_output_tokens = len(quality_plan) * 220
    est_cost = (est_input_tokens / 1_000_000) * 5.0 + (est_output_tokens / 1_000_000) * 30.0

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-requality-preflight-v1",
        "status": "PASS_REQUALITY_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "design": (
            "Same blind pairwise instrument as the original measurement (305l/306l): "
            "position-randomized A/B, material-preference only. Scope: the 31 pairs where RS "
            "selected a Restatement-or-Paraphrasing card, comparing the NEW warm-close-variant "
            "routed reply against the SAME original baseline reply (baseline unaffected, not "
            "regenerated). Risk not re-measured (not the identified problem)."
        ),
        "reviewer_id": REVIEWER_ID,
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": len(quality_plan),
            "maximum_physical_attempts": len(quality_plan) * 2,
            "proposed_absolute_usd_cap": USD_CAP,
            "estimated_cost_usd": round(est_cost, 4),
            "scope": "31 blind pairwise quality calls comparing the warm-close-variant routed replies against the original baseline replies.",
        },
        "artifacts": {
            "quality_packet": {"path": str((OUT / "quality_packet_blind.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "quality_packet_blind.jsonl")},
            "call_plan": {"path": str((OUT / "call_plan_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "call_plan_private.jsonl")},
            "private_mapping": {"path": str((OUT / "private_mapping.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "private_mapping.jsonl")},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "external_test_cases": sha256_file(EXTERNAL_TEST_CASES),
            "external_test_results": sha256_file(EXTERNAL_TEST_RESULTS),
            "regen_results": sha256_file(REGEN_RESULTS),
        },
        "api_calls": 0,
        "next": "HUMAN_MUST_EXPLICITLY_APPROVE_THIS_EXACT_STAGE_RUN_IDENTITY_AND_COST_CAP",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
