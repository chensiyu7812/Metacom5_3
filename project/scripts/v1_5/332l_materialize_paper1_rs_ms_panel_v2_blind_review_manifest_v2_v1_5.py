#!/usr/bin/env python3
"""V2 blind-review manifest for the RS/MS Panel V2, superseding 331l's
89-call plan per explicit user direction (2026-08-13):

  - +12 MS+RS absolute Risk calls (was only M0+R0/M0+RS/MS+R0).
  - The 7 single-point "MS+RS alone" Function judgments are replaced by 7
    blind PAIRWISE MS+R0-vs-MS+RS comparisons (PRESERVED/STRENGTHENED/
    WEAKENED/NONE_IN_EITHER/UNCERTAIN), position-randomized A/B, instead of
    inferring a change from two separately-judged single-point labels.
  - Total: 25 Quality + 50 Risk + 26 Function/interaction = 101 calls.

Every call carries a `public_call` projection containing ONLY the fields a
provider-safe runner is allowed to see (messages, schema identity,
temperature, max_output_tokens, seed) -- case_id/arm/owner_cluster/kind
never appear in `public_call` and must never reach client.chat(). See
333l's PROVIDER_SAFE_KEYS allowlist and its enforcement check.

Still zero-API: reuses the 50 real replies from 329l, no new generation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_function_observability_v2_blind_review import (  # noqa: E402
    FunctionObservabilityV2BlindReview,
    function_prompt_messages,
)
from metacom_pm.v1_5_ms_rs_interaction_blind_review import (  # noqa: E402
    MSRSInteractionBlindReview,
    interaction_prompt_messages,
)
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import (  # noqa: E402
    RSMSQualityBlindReview,
    RSMSRiskBlindReview,
    quality_prompt_messages,
    risk_prompt_messages,
)

CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_20260813/development_cases_private.jsonl"
STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_live_20260813/generator_results_private.jsonl"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_manifest_v2_20260813"
STAGE = "paper1_rs_ms_panel_v2_blind_review_v2"
REVIEWER_ID = "RS_MS_PANEL_V2_BLIND_REVIEW_V2_GPT56"
ENDPOINT_KEY = "openai_gpt_5_6_sol"
FUNCTION_STATES = {"CLEAR_USE", "ASK"}
QUALITY_RISK_USD_PER_CALL = 0.0101
FUNCTION_USD_PER_CALL = 0.016
PROVIDER_SAFE_KEYS = frozenset({"messages", "temperature", "max_output_tokens", "seed", "schema_sha256"})


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _public_call(messages: list[dict[str, str]], schema_sha256: str, seed: int, max_output_tokens: int = 500, temperature: float = 0.0) -> dict[str, Any]:
    call = {
        "messages": messages,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "seed": seed,
        "schema_sha256": schema_sha256,
    }
    assert set(call) == PROVIDER_SAFE_KEYS
    return call


def main() -> None:
    if OUT.exists():
        raise RuntimeError("V2 blind review manifest already materialized; refusing overwrite")

    cases = {row["case_id"]: row for row in read_jsonl(CASES)}
    states = {row["state_id"]: row for row in read_jsonl(STATES)}
    results = {(row["case_id"], row["arm"]): row for row in read_jsonl(RESULTS)}
    cards = {row["card_id"]: row for row in read_jsonl(QUALIFIED_CARDS)}
    if len(results) != 50:
        raise RuntimeError(f"expected 50 real replies, found {len(results)}")

    quality_calls: list[dict[str, Any]] = []
    risk_calls: list[dict[str, Any]] = []
    function_calls: list[dict[str, Any]] = []
    risk_call_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    private_map: list[dict[str, Any]] = []

    def get_risk_call(case_id: str, arm: str, owner: str, dialogue: str) -> str:
        key = (case_id, arm)
        if key in risk_call_by_key:
            return risk_call_by_key[key]["item_id"]
        reply = results[key]["reply"]
        item_id = "rsmsv2riskb_" + stable_hex(case_id, arm, "RISK")
        messages = risk_prompt_messages(item_id=item_id, dialogue=dialogue, reply=reply)
        schema_sha256 = sha256_text(canonical_json(RSMSRiskBlindReview.model_json_schema()))
        seed = 20260813 + int(stable_hex(REVIEWER_ID, item_id, length=8), 16) % 100000
        call = {
            "logical_call_id": "rsmsv2riskcallb_" + stable_hex(REVIEWER_ID, item_id),
            "kind": "risk",
            "case_id": case_id,
            "arm": arm,
            "owner_cluster": owner,
            "item_id": item_id,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "schema_sha256": schema_sha256,
            "public_call": _public_call(messages, schema_sha256, seed),
        }
        risk_call_by_key[key] = call
        risk_calls.append(call)
        return item_id

    for case_id, case in sorted(cases.items()):
        owner = case["runtime_owner_key"]
        state = states[case["state_id"]]
        dialogue = _compact(state["current_user_text"])
        arms = set(case["arms_present"])

        # --- Risk: M0+R0 (always), M0+RS, MS+R0, MS+RS (all now included) ---
        risk_m0r0 = get_risk_call(case_id, "M0+R0", owner, dialogue)
        risk_m0rs = get_risk_call(case_id, "M0+RS", owner, dialogue) if "M0+RS" in arms else None
        risk_msr0 = get_risk_call(case_id, "MS+R0", owner, dialogue) if "MS+R0" in arms else None
        risk_msrs = get_risk_call(case_id, "MS+RS", owner, dialogue) if "MS+RS" in arms else None

        # --- RS: Quality (M0+R0 vs M0+RS) + strategy realization ---
        rs_quality_id = None
        rs_function_id = None
        if "M0+RS" in arms:
            reply_m0r0 = results[(case_id, "M0+R0")]["reply"]
            reply_m0rs = results[(case_id, "M0+RS")]["reply"]
            pair_id = "rsv2pairb_" + stable_hex(case_id, "RS_QUALITY")
            a_is_rs = int(stable_hex("AB", pair_id, length=2), 16) % 2 == 0
            reply_a = reply_m0rs if a_is_rs else reply_m0r0
            reply_b = reply_m0r0 if a_is_rs else reply_m0rs
            messages = quality_prompt_messages(pair_id=pair_id, dialogue=dialogue, reply_a=reply_a, reply_b=reply_b)
            schema_sha256 = sha256_text(canonical_json(RSMSQualityBlindReview.model_json_schema()))
            seed = 20260813 + int(stable_hex(REVIEWER_ID, pair_id, length=8), 16) % 100000
            quality_calls.append({
                "logical_call_id": "rsv2qualcallb_" + stable_hex(REVIEWER_ID, pair_id),
                "kind": "rs_quality",
                "case_id": case_id,
                "owner_cluster": owner,
                "pair_id": pair_id,
                "a_arm": "M0+RS" if a_is_rs else "M0+R0",
                "b_arm": "M0+R0" if a_is_rs else "M0+RS",
                "messages_sha256": sha256_text(canonical_json(messages)),
                "schema_sha256": schema_sha256,
                "public_call": _public_call(messages, schema_sha256, seed),
            })
            rs_quality_id = pair_id

            card = cards[case["rs_card_id"]]
            fn_id = "rsv2strategyb_" + stable_hex(case_id, "RS_STRATEGY")
            fn_messages = function_prompt_messages(
                blind_item_id=fn_id,
                current_context=dialogue,
                authorized_resource_label=f"RS strategy card ({card.get('strategy_family')})",
                authorized_resource_text=str(card.get("retrieval_text", "")),
                reply=reply_m0rs,
            )
            fn_schema_sha256 = sha256_text(canonical_json(FunctionObservabilityV2BlindReview.model_json_schema()))
            fn_seed = 20260813 + int(stable_hex(REVIEWER_ID, fn_id, length=8), 16) % 100000
            function_calls.append({
                "logical_call_id": "rsv2strategycallb_" + stable_hex(REVIEWER_ID, fn_id),
                "kind": "rs_strategy_realization",
                "case_id": case_id,
                "owner_cluster": owner,
                "arm_judged": "M0+RS",
                "blind_item_id": fn_id,
                "messages_sha256": sha256_text(canonical_json(fn_messages)),
                "schema_sha256": fn_schema_sha256,
                "public_call": _public_call(fn_messages, fn_schema_sha256, fn_seed),
            })
            rs_function_id = fn_id

        # --- MS: Quality (M0+R0 vs MS+R0) ---
        ms_quality_id = None
        if "MS+R0" in arms:
            reply_m0r0 = results[(case_id, "M0+R0")]["reply"]
            reply_msr0 = results[(case_id, "MS+R0")]["reply"]
            pair_id = "rsv2pairb_" + stable_hex(case_id, "MS_QUALITY")
            a_is_ms = int(stable_hex("AB", pair_id, length=2), 16) % 2 == 0
            reply_a = reply_msr0 if a_is_ms else reply_m0r0
            reply_b = reply_m0r0 if a_is_ms else reply_msr0
            messages = quality_prompt_messages(pair_id=pair_id, dialogue=dialogue, reply_a=reply_a, reply_b=reply_b)
            schema_sha256 = sha256_text(canonical_json(RSMSQualityBlindReview.model_json_schema()))
            seed = 20260813 + int(stable_hex(REVIEWER_ID, pair_id, length=8), 16) % 100000
            quality_calls.append({
                "logical_call_id": "rsv2qualcallb_" + stable_hex(REVIEWER_ID, pair_id),
                "kind": "ms_quality",
                "case_id": case_id,
                "owner_cluster": owner,
                "pair_id": pair_id,
                "a_arm": "MS+R0" if a_is_ms else "M0+R0",
                "b_arm": "M0+R0" if a_is_ms else "MS+R0",
                "messages_sha256": sha256_text(canonical_json(messages)),
                "schema_sha256": schema_sha256,
                "public_call": _public_call(messages, schema_sha256, seed),
            })
            ms_quality_id = pair_id

        # --- MS Function independent re-verification (single-point, on MS+R0) ---
        ms_function_id = None
        interaction_id = None
        interaction_ms_rs_position = None
        if case["stratum"] in FUNCTION_STATES:
            ms_source = case["ms_exact_source"]
            reply_msr0 = results[(case_id, "MS+R0")]["reply"]
            fn_id = "rsv2msfunctionb_" + stable_hex(case_id, "MS_FUNCTION")
            fn_messages = function_prompt_messages(
                blind_item_id=fn_id,
                current_context=dialogue,
                authorized_resource_label="strictly past user-owned MS source",
                authorized_resource_text=ms_source,
                reply=reply_msr0,
            )
            fn_schema_sha256 = sha256_text(canonical_json(FunctionObservabilityV2BlindReview.model_json_schema()))
            fn_seed = 20260813 + int(stable_hex(REVIEWER_ID, fn_id, length=8), 16) % 100000
            function_calls.append({
                "logical_call_id": "rsv2msfunctioncallb_" + stable_hex(REVIEWER_ID, fn_id),
                "kind": "ms_function_independent",
                "case_id": case_id,
                "owner_cluster": owner,
                "arm_judged": "MS+R0",
                "blind_item_id": fn_id,
                "messages_sha256": sha256_text(canonical_json(fn_messages)),
                "schema_sha256": fn_schema_sha256,
                "public_call": _public_call(fn_messages, fn_schema_sha256, fn_seed),
            })
            ms_function_id = fn_id

            # --- Interaction: blind pairwise MS+R0 vs MS+RS ---
            if "MS+RS" in arms:
                reply_msrs = results[(case_id, "MS+RS")]["reply"]
                pair_id = "rsv2interactionb_" + stable_hex(case_id, "MS_RS_INTERACTION")
                ms_rs_is_a = int(stable_hex("AB", pair_id, length=2), 16) % 2 == 0
                reply_a = reply_msrs if ms_rs_is_a else reply_msr0
                reply_b = reply_msr0 if ms_rs_is_a else reply_msrs
                int_messages = interaction_prompt_messages(
                    pair_id=pair_id,
                    current_context=dialogue,
                    authorized_resource_text=ms_source,
                    reply_a=reply_a,
                    reply_b=reply_b,
                )
                int_schema_sha256 = sha256_text(canonical_json(MSRSInteractionBlindReview.model_json_schema()))
                int_seed = 20260813 + int(stable_hex(REVIEWER_ID, pair_id, length=8), 16) % 100000
                function_calls.append({
                    "logical_call_id": "rsv2interactioncallb_" + stable_hex(REVIEWER_ID, pair_id),
                    "kind": "ms_rs_interaction_pairwise",
                    "case_id": case_id,
                    "owner_cluster": owner,
                    "pair_id": pair_id,
                    "ms_rs_position": "A" if ms_rs_is_a else "B",
                    "a_arm": "MS+RS" if ms_rs_is_a else "MS+R0",
                    "b_arm": "MS+R0" if ms_rs_is_a else "MS+RS",
                    "messages_sha256": sha256_text(canonical_json(int_messages)),
                    "schema_sha256": int_schema_sha256,
                    "public_call": _public_call(int_messages, int_schema_sha256, int_seed),
                })
                interaction_id = pair_id
                interaction_ms_rs_position = "A" if ms_rs_is_a else "B"

        private_map.append({
            "case_id": case_id,
            "owner_cluster": owner,
            "stratum": case["stratum"],
            "risk_m0r0_item_id": risk_m0r0,
            "risk_m0rs_item_id": risk_m0rs,
            "risk_msr0_item_id": risk_msr0,
            "risk_msrs_item_id": risk_msrs,
            "rs_quality_pair_id": rs_quality_id,
            "rs_strategy_function_id": rs_function_id,
            "ms_quality_pair_id": ms_quality_id,
            "ms_function_independent_id": ms_function_id,
            "ms_rs_interaction_pair_id": interaction_id,
            "ms_rs_interaction_ms_rs_position": interaction_ms_rs_position,
        })

    quality_calls.sort(key=lambda row: stable_hex("Q_ORDER", row["logical_call_id"]))
    risk_calls.sort(key=lambda row: stable_hex("R_ORDER", row["logical_call_id"]))
    function_calls.sort(key=lambda row: stable_hex("F_ORDER", row["logical_call_id"]))
    private_map.sort(key=lambda row: row["case_id"])

    all_calls = quality_calls + risk_calls + function_calls
    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "call_plan": [row["logical_call_id"] for row in all_calls],
            "call_plan_messages_sha256": [row["messages_sha256"] for row in all_calls],
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
    stale_identities = {
        str(record.get("run_identity") or "")
        for record in (release_manifest.get("stale_unapproved_dry_runs") or {}).values()
        if isinstance(record, dict)
    }
    if "4ee5607d47e9285860464fb8e47b933a22289a90d1f72482386155d332b6a600" not in stale_identities:
        raise RuntimeError("superseded V1 manifest identity is not registered as stale")

    owner_clusters = sorted({row["owner_cluster"] for row in private_map})
    estimated_usd = round(
        len(quality_calls + risk_calls) * QUALITY_RISK_USD_PER_CALL
        + len(function_calls) * FUNCTION_USD_PER_CALL,
        4,
    )

    forbidden = ("generator_claimed", "used_evidence_ids", "requested_action_id", "MS+RS", "MS+R0", "M0+RS", "M0+R0")
    provider_text = canonical_json([row["public_call"]["messages"] for row in all_calls])
    public_call_keys_ok = all(set(row["public_call"]) == PROVIDER_SAFE_KEYS for row in all_calls)
    checks = {
        "no_new_generation_all_replies_reused": True,
        "thirteen_states_present": len(private_map) == 13,
        "risk_calls_deduped_per_case_arm": len(risk_calls) == len({(c["case_id"], c["arm"]) for c in risk_calls}),
        "risk_covers_all_four_arms": len(risk_calls) == 50,
        "quality_position_randomized": (
            0 < sum(1 for row in quality_calls if row["kind"] == "rs_quality" and row["a_arm"] == "M0+RS") < len([r for r in quality_calls if r["kind"] == "rs_quality"])
        ),
        "interaction_position_randomized": (
            0 < sum(1 for row in function_calls if row["kind"] == "ms_rs_interaction_pairwise" and row["ms_rs_position"] == "A") < 7
        ),
        "interaction_is_pairwise_not_single_point": sum(1 for row in function_calls if row["kind"] == "ms_rs_interaction_pairwise") == 7,
        "function_independent_still_single_point": sum(1 for row in function_calls if row["kind"] == "ms_function_independent") == 7,
        "call_totals_match_101": len(quality_calls) == 25 and len(risk_calls) == 50 and len(function_calls) == 26 and len(all_calls) == 101,
        "one_schema_per_kind": (
            len({row["schema_sha256"] for row in quality_calls}) == 1
            and len({row["schema_sha256"] for row in risk_calls}) == 1
            and len({row["schema_sha256"] for row in function_calls if row["kind"] != "ms_rs_interaction_pairwise"}) == 1
            and len({row["schema_sha256"] for row in function_calls if row["kind"] == "ms_rs_interaction_pairwise"}) == 1
        ),
        "condition_and_arm_labels_absent_from_provider_text": not any(token in provider_text for token in forbidden),
        "public_call_contains_only_provider_safe_keys": public_call_keys_ok,
        "owner_cluster_present_on_every_private_call_record": all("owner_cluster" in row for row in all_calls),
        "old_v1_identity_registered_stale": True,
        "run_identity_not_previously_consumed_or_pending": run_identity not in consumed_identities,
        "run_identity_differs_from_superseded_v1": run_identity != "4ee5607d47e9285860464fb8e47b933a22289a90d1f72482386155d332b6a600",
    }
    if not all(checks.values()):
        raise RuntimeError(f"manifest self-check failed: {checks}")

    write_jsonl(OUT / "quality_calls_private.jsonl", quality_calls)
    write_jsonl(OUT / "risk_calls_private.jsonl", risk_calls)
    write_jsonl(OUT / "function_calls_private.jsonl", function_calls)
    write_jsonl(OUT / "private_map.jsonl", private_map)

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-panel-v2-blind-review-manifest-v2",
        "status": "PREFLIGHT_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_JUDGE_CALL",
        "supersedes": {
            "stage": "paper1_rs_ms_panel_v2_blind_review_v1",
            "run_identity": "4ee5607d47e9285860464fb8e47b933a22289a90d1f72482386155d332b6a600",
            "status": "SUPERSEDED_UNUSED",
        },
        "source": "outputs/pm_v1_5_paper1_rs_ms_panel_v2_live_20260813/generator_results_private.jsonl (50/50 real replies, no new generation)",
        "instrument": {
            "quality_and_risk": "v1_5_rs_ms_quality_risk_blind_review.py (unmodified)",
            "function_single_point": "v1_5_function_observability_v2_blind_review.py (CLEAR/PLAUSIBLE/NONE/UNCERTAIN)",
            "interaction_pairwise": "v1_5_ms_rs_interaction_blind_review.py (new: PRESERVED/STRENGTHENED/WEAKENED/NONE_IN_EITHER/UNCERTAIN, position-randomized A/B)",
        },
        "reviewer_id": REVIEWER_ID,
        "endpoint_key": ENDPOINT_KEY,
        "judge_model": "gpt-5.6-sol",
        "call_counts": {
            "rs_quality": sum(1 for r in quality_calls if r["kind"] == "rs_quality"),
            "ms_quality": sum(1 for r in quality_calls if r["kind"] == "ms_quality"),
            "risk_absolute": len(risk_calls),
            "rs_strategy_realization": sum(1 for r in function_calls if r["kind"] == "rs_strategy_realization"),
            "ms_function_independent": sum(1 for r in function_calls if r["kind"] == "ms_function_independent"),
            "ms_rs_interaction_pairwise": sum(1 for r in function_calls if r["kind"] == "ms_rs_interaction_pairwise"),
            "quality_total": len(quality_calls),
            "risk_total": len(risk_calls),
            "function_total": len(function_calls),
            "total": len(all_calls),
        },
        "owner_clusters": {
            "count": len(owner_clusters),
            "members": owner_clusters,
        },
        "estimated_usd": estimated_usd,
        "estimated_usd_basis": f"{QUALITY_RISK_USD_PER_CALL}/call for quality+risk; {FUNCTION_USD_PER_CALL}/call for Function/interaction calls",
        "run_identity": run_identity,
        "checks": checks,
        "next_action": "Present this exact run identity, 101-call plan, and cost cap for explicit human approval before any judge call. No live execution is authorized by this script.",
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
