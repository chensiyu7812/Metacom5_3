#!/usr/bin/env python3
"""MS Panel V1.1: root-fixes the two bugs found in the 101-call blind review
closeout (paper1_rs_ms_panel_v2_blind_review_v2_closeout_v1.json):

1. Context truncation: every CLEAR_USE candidate here was verified against
   the FULL visible_current_session_dialogue (via text.dialogue_text), not
   current_user_text alone -- the cited content must not appear anywhere in
   the full session, not just be absent from the latest turn. All compiled
   prompts also use the full dialogue as current_context.
2. MS+RS composition leak (evo::p6): every MS candidate here is pre-decided
   USE/ASK/IGNORE BEFORE compilation via v1_5_ms_pre_decision.ms_candidate_
   or_none. IGNORE-decided candidates are never constructed into a
   V3Candidate, so their exact_source is physically absent from every arm's
   compiled prompt -- including MS+RS. This panel deliberately reuses the
   exact evo::p6 MS source (verbatim) on a FRESH state as a regression
   probe: if the pre-decision fix works, this dangerous, topically
   irrelevant source must never appear in any compiled arm.

Owner-unique across the WHOLE panel (not just per stratum) -- the other bug
already corrected in paper1_panel_v2_owner_cluster_correction_and_roadmap_v1
.json. No generator call is made here.
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
from metacom_pm.text import dialogue_text  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_ms_pre_decision import assert_source_absent_from_compiled_text, ms_candidate_or_none  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402
from metacom_pm.v1_5_rs_v4_card_retrieval import retrieve as rs_retrieve  # noqa: E402

EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_v1_1_panel_20260813"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."

MS_MEANING_CUE = "Interpret the single strictly past user-owned source as a tentative continuity cue; do not treat it as current or quote it."
MS_ALLOWED_CHANGE = "USE only when the fact adds information not already available in the current dialogue; ASK when continuity is uncertain; IGNORE otherwise."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."

# case_id -> (stratum, pre_decision, ms_candidate_id, rationale). pre_decision
# is fixed before generation, per the root-fix; IGNORE candidates are still
# curated (with a real source) so the physical-absence guarantee can be
# tested against a real, previously-dangerous source.
CURATION: dict[str, dict[str, Any]] = {
    "evo::p2::p2_conv_5::seeker_turn::7": {
        "stratum": "CLEAR_USE", "pre_decision": "USE", "ms_candidate_id": "ms_1e0345474cb315c49037ad4a",
        "rationale": "Current turn says only 'a big argument with my ex'; MS reveals the ex's name (Nate) -- verified absent from the full session, not just the latest turn.",
    },
    "evo::p11::p11_conv_17::seeker_turn::20": {
        "stratum": "CLEAR_USE", "pre_decision": "USE", "ms_candidate_id": "ms_cc08fcb2a28a2ce9c8771286",
        "rationale": "Current turn is fully generic ('needed to hear it today'); MS reveals a specific person and event (John broke up with me) -- verified absent from the full session.",
    },
    "evo::p10::p10_conv_14::seeker_turn::15": {
        "stratum": "CLEAR_USE", "pre_decision": "USE", "ms_candidate_id": "ms_10066e883ada14621b4b8768",
        "rationale": "Current turn says only 'wondering what I could have done differently'; MS reveals the specific context (picking up George, distracted) -- verified absent from the full session.",
    },
    "evo::p1::p1_conv_24::seeker_turn::15": {
        "stratum": "CLEAR_USE", "pre_decision": "USE", "ms_candidate_id": "ms_31d696e8730d1cfb98596207",
        "rationale": "Current turn refers only to 'them'; MS names a specific person (Mark) -- verified absent from the full session.",
    },
    "evo::p14::p14_conv_5::seeker_turn::20": {
        "stratum": "CLEAR_USE", "pre_decision": "USE", "ms_candidate_id": "ms_b654f8a84c327d6e193c8ed8",
        "rationale": "Current turn is generic ('hard to find someone who understands'); MS names a specific person (Ann) and a relationship detail -- verified absent from the full session.",
    },
    "evo::p9::p9_conv_15::seeker_turn::11": {
        "stratum": "ASK", "pre_decision": "ASK", "ms_candidate_id": "ms_33cd0451abeb450f10a60f38",
        "rationale": "Current turn ('this job was supposed to be a fresh start') is unrelated on its face to the MS fact (a past pet loss); continuity is genuinely uncertain rather than clearly relevant -- ASK fits better than a confident USE.",
    },
    "evo::p3::p3_conv_24::seeker_turn::20": {
        "stratum": "IGNORE_current_context_echo", "pre_decision": "IGNORE", "ms_candidate_id": "ms_beb29673ea005a5feaeb4a00",
        "rationale": "Lexical echo score 0.76 -- current turn and MS source are near-duplicate gratitude/closing phrasing, no new information.",
    },
    "evo::p6::p6_conv_18::seeker_turn::12": {
        "stratum": "IGNORE_topical_mismatch_regression_probe", "pre_decision": "IGNORE", "ms_candidate_id": "ms_20d7a60899c0888caf9966c1",
        "rationale": "REGRESSION PROBE: the exact MS source that leaked in the 101-call round (infidelity-temptation content) reused verbatim on a fresh state (a different current turn about telling someone 'she' something). Topically unrelated; pre-decided IGNORE to verify the source-removal fix holds under real conditions.",
    },
    "evo::p4::esc837::seeker_turn::3": {
        "stratum": "IGNORE_natural_off", "pre_decision": "IGNORE", "ms_candidate_id": None,
        "rationale": "'I have to give a presentation at work on a stage. This is causing me a lot of stress' -- real, substantive content, no prior MS candidate exists for this owner at this point (natural off).",
    },
}

WRONG_OWNER_NOTE = (
    "Wrong-owner is demonstrated structurally: build_component_general_plan_v3 raises "
    "OWNER_INVALID whenever a candidate's owner_id != current_user_id."
)


def _verify_owner_unique(curation: dict[str, dict[str, Any]], states_by_id: dict[str, Any]) -> None:
    owners = [states_by_id[sid]["runtime_owner_key"] for sid in curation]
    if len(owners) != len(set(owners)):
        raise RuntimeError(f"owner-uniqueness violated: {owners}")


def main() -> None:
    states_by_id = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    ms_candidates = {row["candidate_id"]: row for row in read_jsonl(EVOEMO_CANDIDATES) if row["component"] == "MS"}
    qualified_cards = read_jsonl(QUALIFIED_CARDS)

    missing = set(CURATION) - set(states_by_id)
    if missing:
        raise RuntimeError(f"curated state_id not found: {sorted(missing)}")
    _verify_owner_unique(CURATION, states_by_id)

    development_cases: list[dict[str, Any]] = []
    manifest_calls: list[dict[str, str]] = []
    strata_counts: dict[str, int] = {}

    for state_id, meta in CURATION.items():
        state = states_by_id[state_id]
        owner = state["runtime_owner_key"]
        stratum = meta["stratum"]
        pre_decision = meta["pre_decision"]
        strata_counts[stratum] = strata_counts.get(stratum, 0) + 1
        full_context = dialogue_text(state["visible_current_session_dialogue"])

        ms_row = ms_candidates[meta["ms_candidate_id"]] if meta["ms_candidate_id"] else None
        ms_candidate = None
        if ms_row is not None:
            ms_candidate = ms_candidate_or_none(
                pre_decision=pre_decision, evidence_id=ms_row["candidate_id"],
                meaning_cue=MS_MEANING_CUE, exact_source=ms_row["literal_text"], owner_id=owner,
                allowed_response_change=MS_ALLOWED_CHANGE, forbidden_inference=MS_FORBIDDEN,
            )
        # IGNORE must produce a physically absent candidate, confirming the root fix at build time.
        if pre_decision == "IGNORE" and ms_row is not None:
            assert ms_candidate is None, "pre-decision IGNORE must not construct a candidate"

        rs_decision = rs_retrieve(recent_dialogue=state["visible_current_session_dialogue"], qualified_cards=qualified_cards)
        rs_candidate = None
        if rs_decision.status == "retrieved_top1":
            card = rs_decision.selected_card
            rs_candidate = V3Candidate(
                component="RS", evidence_id=str(card["card_id"]), meaning_cue=f"strategy_family={card.get('strategy_family')}",
                exact_source=str(card.get("retrieval_text", "")), owner_id=None, time_status="CURRENT_CARD",
                allowed_response_change="Add or sharpen one bounded strategy move only when it improves the present reply.",
                forbidden_inference="Do not let the card replace current-turn grounding or the R0 foundation.",
            )

        arms: dict[str, list[dict[str, str]]] = {}
        m0_plan = build_component_general_plan_v3(requested_action_id="M0+R0", current_user_id=owner, candidates={"MP": None, "MS": None, "ME": None, "RS": None})
        arms["M0+R0"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=m0_plan)

        if ms_candidate is not None:
            ms_plan = build_component_general_plan_v3(requested_action_id="MS+R0", current_user_id=owner, candidates={"MP": None, "MS": ms_candidate, "ME": None, "RS": None})
            arms["MS+R0"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=ms_plan)

        if rs_candidate is not None:
            rs_plan = build_component_general_plan_v3(requested_action_id="M0+RS", current_user_id=owner, candidates={"MP": None, "MS": None, "ME": None, "RS": rs_candidate})
            arms["M0+RS"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=rs_plan)
            if ms_candidate is not None:
                joint_plan = build_component_general_plan_v3(requested_action_id="MS+RS", current_user_id=owner, candidates={"MP": None, "MS": ms_candidate, "ME": None, "RS": rs_candidate})
                arms["MS+RS"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=joint_plan)
            elif ms_row is not None:
                # IGNORE case with RS also active: this IS the regression-probe condition
                # (MS pre-decided IGNORE, RS also compiled). Compiling it separately would
                # be byte-identical to M0+RS (MS is physically absent either way), so it is
                # not added as a second physical call -- the assertion below verifies the
                # already-compiled M0+RS arm directly instead of duplicating the call.
                pass

        if ms_row is not None and pre_decision == "IGNORE":
            for arm_name, messages in arms.items():
                assert_source_absent_from_compiled_text(exact_source=ms_row["literal_text"], compiled_messages=messages)

        case = {
            "case_id": f"msv11_{hashlib.sha256(state_id.encode()).hexdigest()[:20]}",
            "state_id": state_id, "runtime_owner_key": owner, "stratum": stratum, "pre_decision": pre_decision,
            "rationale": meta["rationale"], "ms_exact_source": ms_row["literal_text"] if ms_row else None,
            "rs_status": rs_decision.status, "arms_present": sorted(arms), "used_full_context": True,
        }
        development_cases.append(case)
        for arm_name, messages in arms.items():
            manifest_calls.append({
                "case_id": case["case_id"], "arm": arm_name,
                "prompt_sha256": sha256_text(canonical_json(messages)),
            })

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "development_cases_private.jsonl", development_cases)

    report = {
        "protocol": "pm-v1.5-paper1-ms-v1-1-panel",
        "status": "ZERO_API_OWNER_UNIQUE_FULL_CONTEXT_PRE_DECIDED_PANEL_READY_NO_EXECUTION_AUTHORIZED",
        "root_fixes_applied": [
            "full visible_current_session_dialogue used for both curation verification and compiled prompts (text.dialogue_text)",
            "MS USE/ASK/IGNORE pre-decided before compilation (v1_5_ms_pre_decision.ms_candidate_or_none); IGNORE candidates never constructed, physically absent from every arm including MS+RS",
            "evo::p6's exact leaked source reused verbatim on a fresh state as a live regression probe -- assert_source_absent_from_compiled_text checked at build time for every IGNORE case",
        ],
        "owner_uniqueness": "verified: one state per owner across the WHOLE panel",
        "strata_counts": strata_counts,
        "distinct_owners": len({c["runtime_owner_key"] for c in development_cases}),
        "honest_scope": "1 ASK case (short of a 2-owner target), no dedicated stale/conflict case found this pass -- disclosed, not fabricated.",
        "wrong_owner_control": {"note": WRONG_OWNER_NOTE},
        "states": len(development_cases),
        "total_calls": len(manifest_calls),
        "estimated_cost_usd": 0.0,
        "generator": "meta/llama-3.1-8b-instruct (frozen, unchanged)",
        "manifest_calls": manifest_calls,
        "next_action": "Present this exact run identity, call count, and cost cap for explicit human approval before any generator call.",
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
