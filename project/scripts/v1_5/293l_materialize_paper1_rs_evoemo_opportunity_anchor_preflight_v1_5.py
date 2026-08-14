#!/usr/bin/env python3
"""Materialize (zero-API) a real EvoEmo RS-opportunity anchor set + review plan.

Diagnostic finding that motivates this round: 78.5% of the full 4689-state real
EvoEmo corpus collapses to the IDENTICAL feature vector (only "substantive"
fires) under the RS opportunity router's 17 ESConv-calibrated regex features --
no threshold choice can separate genuinely different real content within a
single collapsed feature bucket. This round gets independent reviewer judgment
(not the operator's own pattern-matching) on a real, diverse sample from that
exact bucket, to determine whether the router's near-universal ON rate on
EvoEmo reflects a genuine domain property or under-firing exclusion features
(pure_phatic / routine_closing / low_burden / explicit_stop), and to ground any
regex expansion in real disagreement cases rather than invented examples.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import joblib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_rs_opportunity_evoemo_review import RSOpportunityEvoEmoReview, prompt_messages  # noqa: E402
from metacom_pm.v1_5_strategy_rag_repair import repaired_observable_opportunity_flags  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
RS_CHECKPOINT = ROOT / "outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1/rs_opportunity_router.joblib"
RS_FEATURES_REPORT = ROOT / "outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1/fit_report.json"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_evoemo_opportunity_anchor_preflight_20260812"
STAGE = "paper1_rs_evoemo_opportunity_anchor_v1"
USD_CAP = 0.15

REVIEWER_ID = "RS_EVOEMO_OPPORTUNITY_INDEPENDENT_GPT56"
ENDPOINT_KEY = "openai_gpt_5_6_sol"
N_DOMINANT_BUCKET = 14
N_OTHER_BUCKETS = 4


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS EvoEmo opportunity anchor preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_MS_EVOEMO_EXECUTOR_PILOT_CLEAN_FORMAL_MEASUREMENT_AND_MP_ME_RESCUE_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS+MS EvoEmo pilot closeout phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    rs_model = joblib.load(RS_CHECKPOINT)
    rs_features = read_json(RS_FEATURES_REPORT)["feature_names"]
    states = read_jsonl(EVOEMO_STATES)

    dominant_bucket: list[dict[str, Any]] = []
    other_buckets: dict[str, list[dict[str, Any]]] = {}
    for s in states:
        flags = repaired_observable_opportunity_flags(current_user_text=s["current_user_text"], visible_dialogue=s["visible_current_session_dialogue"])
        active = tuple(sorted(k for k, v in flags.items() if v))
        vector = [[int(bool(flags[name])) for name in rs_features]]
        probability = float(rs_model.predict_proba(vector)[0][1])
        row = {"state": s, "flags": flags, "active_flags": active, "probability": probability}
        if active == ("substantive",):
            dominant_bucket.append(row)
        else:
            other_buckets.setdefault(active, []).append(row)

    dominant_bucket.sort(key=lambda row: stable_hex("RS_ANCHOR_DOMINANT", row["state"]["state_id"]))
    selected: list[dict[str, Any]] = []
    used_owners: set[str] = set()
    for row in dominant_bucket:
        owner = row["state"]["runtime_owner_key"]
        if owner in used_owners:
            continue
        selected.append(row)
        used_owners.add(owner)
        if len(selected) == N_DOMINANT_BUCKET:
            break

    other_flat = sorted(
        (row for rows in other_buckets.values() for row in rows),
        key=lambda row: stable_hex("RS_ANCHOR_OTHER", row["state"]["state_id"]),
    )
    for row in other_flat:
        owner = row["state"]["runtime_owner_key"]
        if owner in used_owners:
            continue
        selected.append(row)
        used_owners.add(owner)
        if len(selected) == N_DOMINANT_BUCKET + N_OTHER_BUCKETS:
            break

    plan: list[dict[str, Any]] = []
    anchors: list[dict[str, Any]] = []
    for row in selected:
        state = row["state"]
        messages = prompt_messages(state["state_id"], state["visible_current_session_dialogue"])
        anchors.append({
            "protocol": "pm-v1.5-paper1-rs-evoemo-opportunity-anchor-v1",
            "state_id": state["state_id"],
            "runtime_owner_key": state["runtime_owner_key"],
            "current_user_text": state["current_user_text"],
            "router_active_flags": list(row["active_flags"]),
            "router_probability": row["probability"],
            "router_decision_at_0_5": "ON" if row["probability"] >= 0.5 else "OFF",
        })
        plan.append({
            "protocol": "pm-v1.5-paper1-rs-evoemo-opportunity-anchor-call-v1",
            "logical_call_id": "rsevoemoanchorcall_" + stable_hex(REVIEWER_ID, state["state_id"]),
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "state_id": state["state_id"],
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "schema_sha256": sha256_text(canonical_json(RSOpportunityEvoEmoReview.model_json_schema())),
            "seed": 20260812 + int(stable_hex(REVIEWER_ID, state["state_id"], length=8), 16) % 100000,
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
        "exact_18_states_distinct_owners": len(anchors) == N_DOMINANT_BUCKET + N_OTHER_BUCKETS and len({a["runtime_owner_key"] for a in anchors}) == len(anchors),
        "dominant_bucket_all_router_on_at_0_5": all(a["router_decision_at_0_5"] == "ON" for a in anchors[:N_DOMINANT_BUCKET]) and all(a["router_active_flags"] == ["substantive"] for a in anchors[:N_DOMINANT_BUCKET]),
        "other_bucket_has_flag_diversity": len({tuple(a["router_active_flags"]) for a in anchors[N_DOMINANT_BUCKET:]}) >= 2,
        "router_probability_never_provider_visible": all(str(round(a["router_probability"], 4)) not in provider_text for a in anchors),
        "router_active_flags_never_provider_visible": all(
            flag not in provider_text
            for a in anchors
            for flag in a["router_active_flags"]
            if flag != "substantive"
        ),
        "one_strict_schema": len({row["schema_sha256"] for row in plan}) == 1,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_label_zero_fit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"RS EvoEmo opportunity anchor preflight failed: {checks}")

    OUT.mkdir(parents=True)
    anchors_path = OUT / "anchors_private.jsonl"
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(anchors_path, anchors)
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-rs-evoemo-opportunity-anchor-preflight-v1",
        "status": "PASS_ANCHOR_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "diagnostic_motivation": (
            "78.5% of the full 4689-state real EvoEmo corpus (3680 states) collapses to the "
            "identical feature vector under the RS opportunity router (only 'substantive' "
            "fires); no threshold can split a single feature bucket, so this anchor round gets "
            "independent reviewer judgment on a real diverse sample from that exact bucket "
            "(14 states) plus 4 states from other feature buckets for context, to determine "
            "whether the router's near-universal ON rate on EvoEmo is a genuine domain property "
            "or under-firing exclusion regexes, and to ground any fix in real evidence."
        ),
        "reviewer_id": REVIEWER_ID,
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": len(plan),
            "maximum_physical_attempts": len(plan) * 2,
            "proposed_absolute_usd_cap": USD_CAP,
            "scope": (
                "Exactly 18 independent reviewer calls judging RS opportunity presence on real "
                "EvoEmo dialogue turns (14 from the router's dominant 'substantive-only' feature "
                "bucket, 4 from other buckets), grounded in the router's own eligible_families "
                "construct. Zero labels created, zero fits, zero rubric changes -- diagnostic "
                "only."
            ),
        },
        "artifacts": {
            "anchors": {"path": str(anchors_path.relative_to(ROOT)), "sha256": sha256_file(anchors_path)},
            "call_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "evoemo_states": sha256_file(EVOEMO_STATES),
            "rs_checkpoint": sha256_file(RS_CHECKPOINT),
            "rs_features_report": sha256_file(RS_FEATURES_REPORT),
            "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_rs_opportunity_evoemo_review.py"),
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
