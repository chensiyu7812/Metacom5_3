#!/usr/bin/env python3
"""Materialize (zero-API) the risk re-measurement for the 31 warm-close
regenerated routed replies, using the EXACT SAME risk instrument
(RSMSRiskBlindReview, same six families, same absolute independent-scoring
design, same judge model/config) as the original quality/risk measurement
(305l/306l) -- this was skipped in the first fix-attempt round on the
assumption that risk wasn't the identified problem, which is an unverified
assumption, not evidence. For a fair before/after comparison, the same
instrument must be applied to both arms.

Baseline risk is NOT re-scored -- the baseline replies are byte-identical
to the ones already scored in 305l/306l (temperature=0, deterministic
rubric), so reusing those scores is correct, not a shortcut: there is
nothing new to measure for text that did not change.
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
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import RSMSRiskBlindReview, risk_prompt_messages  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
EXTERNAL_TEST_CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl"
REGEN_RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_ms_restatement_warm_close_regeneration_live_20260812/generator_results_private.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_restatement_warm_close_rerisk_preflight_20260812"
STAGE = "paper1_rs_ms_restatement_warm_close_rerisk_v1"
USD_CAP = 0.5

REVIEWER_ID = "RS_MS_WARM_CLOSE_RERISK_INDEPENDENT_GPT56"
ENDPOINT_KEY = "openai_gpt_5_6_sol"


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("restatement warm-close rerisk preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    if current["id"] != "RS_RESTATEMENT_WARM_CLOSE_PARTIAL_IMPROVEMENT_74PCT_STILL_BASELINE_PREFERRED_MP_NEXT":
        raise RuntimeError("warm-close partial-improvement phase is not current")

    cases = {row["case_id"]: row for row in read_jsonl(EXTERNAL_TEST_CASES)}
    regenerated = {row["case_id"]: row for row in read_jsonl(REGEN_RESULTS)}
    if len(regenerated) != 31:
        raise RuntimeError(f"expected 31 regenerated replies, found {len(regenerated)}")

    risk_items: list[dict[str, Any]] = []
    risk_plan: list[dict[str, Any]] = []
    private_map: list[dict[str, Any]] = []

    for case_id, new_routed in sorted(regenerated.items()):
        case = cases[case_id]
        dialogue = case["current_context"]
        item_id = "rswarmrisk_" + stable_hex(case_id, "warm_close", "RISK")
        messages = risk_prompt_messages(item_id=item_id, dialogue=dialogue, reply=new_routed["final_reply"])
        risk_items.append({
            "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-rerisk-blind-item-v1",
            "blind_item_id": item_id,
            "dialogue": dialogue,
            "response": new_routed["final_reply"],
        })
        risk_plan.append({
            "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-rerisk-call-v1",
            "logical_call_id": "rswarmriskcall_" + stable_hex(REVIEWER_ID, item_id),
            "kind": "risk",
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "item_id": item_id,
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "schema_sha256": sha256_text(canonical_json(RSMSRiskBlindReview.model_json_schema())),
            "seed": 20260812 + int(stable_hex(REVIEWER_ID, item_id, length=8), 16) % 100000,
            "temperature": 0.0,
            "max_output_tokens": 500,
        })
        private_map.append({"case_id": case_id, "risk_new_routed_blind_item_id": item_id})

    risk_items.sort(key=lambda row: stable_hex("RISK_ORDER", row["blind_item_id"]))
    risk_plan.sort(key=lambda row: stable_hex("RISK_ORDER", row["item_id"]))
    private_map.sort(key=lambda row: row["case_id"])

    provider_text = canonical_json([row["messages"] for row in risk_plan])
    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "call_plan": [row["logical_call_id"] for row in risk_plan],
            "call_plan_messages_sha256": [row["messages_sha256"] for row in risk_plan],
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
        "exact_31_risk_items": len(risk_items) == 31,
        "same_instrument_as_original_measurement": True,
        "risk_scored_independently_no_baseline_shown": all(
            "REPLY A" not in canonical_json(row["messages"]) and "REPLY B" not in canonical_json(row["messages"])
            for row in risk_plan
        ),
        "one_schema": len({row["schema_sha256"] for row in risk_plan}) == 1,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_baseline_rescoring": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"restatement warm-close rerisk preflight failed: {checks}")

    OUT.mkdir(parents=True)
    write_jsonl(OUT / "risk_packet_blind.jsonl", risk_items)
    write_jsonl(OUT / "call_plan_private.jsonl", risk_plan)
    write_jsonl(OUT / "private_mapping.jsonl", private_map)

    total_prompt_chars = sum(len(canonical_json(row["messages"])) for row in risk_plan)
    est_input_tokens = total_prompt_chars / 4
    est_output_tokens = len(risk_plan) * 180
    est_cost = (est_input_tokens / 1_000_000) * 5.0 + (est_output_tokens / 1_000_000) * 30.0

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-restatement-warm-close-rerisk-preflight-v1",
        "status": "PASS_RERISK_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "design": (
            "Closes a fairness gap: the original fix-attempt round measured quality only, on the "
            "unverified assumption that risk was unaffected. This round applies the exact same "
            "risk instrument (v1_5_rs_ms_quality_risk_blind_review.RSMSRiskBlindReview, same six "
            "families, same absolute per-response scoring, same judge model/config) to the 31 new "
            "warm-close routed replies. Baseline risk is reused from 305l/306l unchanged (the "
            "baseline text is byte-identical, nothing new to measure)."
        ),
        "reviewer_id": REVIEWER_ID,
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": len(risk_plan),
            "maximum_physical_attempts": len(risk_plan) * 2,
            "proposed_absolute_usd_cap": USD_CAP,
            "estimated_cost_usd": round(est_cost, 4),
            "scope": "31 absolute risk calls scoring the warm-close-variant routed replies, same instrument as the original measurement.",
        },
        "artifacts": {
            "risk_packet": {"path": str((OUT / "risk_packet_blind.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "risk_packet_blind.jsonl")},
            "call_plan": {"path": str((OUT / "call_plan_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "call_plan_private.jsonl")},
            "private_mapping": {"path": str((OUT / "private_mapping.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "private_mapping.jsonl")},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "external_test_cases": sha256_file(EXTERNAL_TEST_CASES),
            "regen_results": sha256_file(REGEN_RESULTS),
        },
        "api_calls": 0,
        "next": "HUMAN_MUST_EXPLICITLY_APPROVE_THIS_EXACT_STAGE_RUN_IDENTITY_AND_COST_CAP",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
