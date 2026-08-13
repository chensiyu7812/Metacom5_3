#!/usr/bin/env python3
"""Zero-API RS/MS Panel V2, hand-curated per panel_v2_requirements in
paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json.

Replaces the withdrawn 324l panel's "most-recent-available" MS heuristic
(9/16 states there turned out to be content-free greetings) with direct
per-pair reading: every state below was selected by checking whether the
MS candidate's content is (a) genuinely absent from the current turn and
(b) topically substantive, using named-entity/proper-noun presence as a
concrete filter, not lexical_score rank alone -- lexical_score turned out
to rank generic "thanks for listening" boilerplate above genuine content
(0.6-0.8 range) precisely because such boilerplate is near-duplicated
phrasing, which is a redundancy signal, not a relevance signal. That
finding is reused here as the current_context_echo control category.

Strata (rationale per state in CURATION, outcome-blind -- written before
any prompt was compiled):
  CLEAR_USE (5, 5 owners), ASK (2, 2 owners), IGNORE (6, 6 owners) covering
  all six required_negative_controls except wrong_owner, which is verified
  structurally (see _verify_wrong_owner_gate), matching 325l's approach for
  MP. RS fires (status=retrieved_top1) on 12/13 states -- exactly meeting
  the >=12 four-arm-complete requirement; the 13th is the deliberate
  RS-structurally-ineligible control and correctly gets only two arms.

No generator call is made. This proposes a content-addressed execution
manifest for later human approval.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_jsonl, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402
from metacom_pm.v1_5_rs_v4_card_retrieval import retrieve as rs_retrieve  # noqa: E402

EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_20260813"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."

MS_MEANING_CUE = "Interpret the single strictly past user-owned source as a tentative continuity cue; do not treat it as current or quote it."
MS_ALLOWED_CHANGE = "USE only when the fact adds information not already available in the current dialogue; ASK when continuity is uncertain; IGNORE otherwise."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."

CURATION: dict[str, dict[str, Any]] = {
    "evo::p1::p1_conv_23::seeker_turn::5": {
        "stratum": "CLEAR_USE",
        "ms_candidate_id": "ms_b4396e7954c74a2a7a5dd689",
        "rationale": (
            "Current turn ('brought up a lot of past feelings and memories, I guess I'm a bit "
            "overwhelmed') never says what triggered it. The MS fact names the specific trigger "
            "(a weekend trip with Jack) -- genuinely absent from current context, not a restated echo."
        ),
    },
    "evo::p13::p13_conv_4::seeker_turn::6": {
        "stratum": "CLEAR_USE",
        "ms_candidate_id": "ms_e492eaeb21e9ff46e636d081",
        "rationale": (
            "Current turn names David and 'my issues' but not what the issues are. The MS fact "
            "specifies grief -- current context alone cannot recover that this is bereavement."
        ),
    },
    "evo::p14::p14_conv_12::seeker_turn::15": {
        "stratum": "CLEAR_USE",
        "ms_candidate_id": "ms_3271ea7f96bc6faf4d406487",
        "rationale": (
            "Current turn is 'trying to hold onto the calm from the weekend' with no coping method "
            "named. The MS fact names a specific already-tried resource (a podcast) not otherwise "
            "recoverable."
        ),
    },
    "evo::p18::p18_conv_8::seeker_turn::17": {
        "stratum": "CLEAR_USE",
        "ms_candidate_id": "ms_581d35891e2ac5a48ae2222f",
        "rationale": (
            "Current turn says only 'the job offer' and 'what-if'. The MS fact reveals the specific "
            "decision (turned down a California offer) that the what-if is about -- the current turn "
            "alone cannot recover what was decided or where."
        ),
    },
    "evo::p8::p8_conv_27::seeker_turn::13": {
        "stratum": "CLEAR_USE",
        "ms_candidate_id": "ms_2684d57ed236851df44a7c1f",
        "rationale": (
            "Current turn says only 'reassurance that I'm on the right path' with no referent. The "
            "MS fact names a specific person and unresolved intention (telling Emily about the "
            "connection) not recoverable from current context alone."
        ),
    },
    "evo::p9::p9_conv_11::seeker_turn::7": {
        "stratum": "ASK",
        "ms_candidate_id": "ms_33cd0451abeb450f10a60f38",
        "rationale": (
            "Current turn describes present loneliness with no stated cause. The MS fact references "
            "a specific past loss (a pet's euthanasia) that may or may not be what's driving the "
            "current feeling -- continuity is genuinely uncertain, so a tentative check fits better "
            "than a confident USE."
        ),
    },
    "evo::p2::esc150::seeker_turn::4": {
        "stratum": "ASK",
        "ms_candidate_id": "ms_a8cbdde690b33bfb0a2776af",
        "rationale": (
            "Current turn states present isolation with no named cause. The MS fact (fear of telling "
            "family, tied to academic pressure) is a plausible but unconfirmed antecedent -- whether "
            "it resolved or still applies is unknown, so ASK fits better than USE."
        ),
    },
    "evo::p3::p3_conv_13::seeker_turn::20": {
        "stratum": "IGNORE_current_context_echo",
        "ms_candidate_id": "ms_d24f6a15b0fe20cbdf37045f",
        "rationale": (
            "Lexical echo score 0.79 -- current turn ('Thanks so much for listening, it means a lot') "
            "and the MS fact are near-duplicate gratitude phrasing. Confirms the root-repair "
            "diagnosis: high lexical similarity here signals redundancy, not relevance."
        ),
    },
    "evo::p11::p11_conv_13::seeker_turn::18": {
        "stratum": "IGNORE_topical_mismatch",
        "ms_candidate_id": "ms_c5f95f0ae9abd0b6bc3a1d5a",
        "rationale": (
            "Lexical score 0.59 despite zero topical relevance: current turn is about trusting others "
            "with feelings; the MS fact is about trying banana chips. A clean false-positive example "
            "of the same lexical-overlap confound diagnosed for RS/MS all session."
        ),
    },
    "evo::p6::esc660::seeker_turn::15": {
        "stratum": "IGNORE_topical_mismatch",
        "ms_candidate_id": "ms_20d7a60899c0888caf9966c1",
        "rationale": (
            "Current turn asks who to approach at work about an opportunity; the MS fact is about "
            "being blindsided by a friend's infidelity temptation a year ago. Unrelated subject "
            "matter despite a 0.55 lexical score."
        ),
    },
    "evo::p10::p10_conv_10::seeker_turn::4": {
        "stratum": "IGNORE_stale_or_conflicting",
        "ms_candidate_id": "ms_4910dbe1a8bb7e0b3698dd5e",
        "rationale": (
            "The MS fact says Bob got a part-time job; the current turn already reports Bob just got "
            "a full-time job. The past fact is superseded by information the current turn already "
            "states -- using the old 'part-time' framing would be factually stale."
        ),
    },
    "evo::p1::p1_conv_6::seeker_turn::1": {
        "stratum": "IGNORE_low_information_greeting",
        "ms_candidate_id": "ms_7543a3b9c5d2da20323043ee",
        "rationale": (
            "The only prior-session MS candidate offered is 'Hey, do you have a moment to talk?' -- "
            "a content-free opener with nothing to use. Included deliberately (not filtered out, "
            "unlike the rest of this panel) to confirm the compiler resolves it to IGNORE rather than "
            "manufacturing a false USE, the exact failure mode the withdrawn 324l panel could not "
            "distinguish from its unintentional greeting contamination."
        ),
    },
    "evo::p5::p5_conv_9::seeker_turn::21": {
        "stratum": "IGNORE_rs_structurally_ineligible",
        "ms_candidate_id": "ms_454fb66c18fa934f3db60390",
        "rationale": (
            "rs_retrieve() returns status=off_no_eligible_family on this state's dialogue: no "
            "observable-flag family fires, so RS is structurally off regardless of MS. Only two arms "
            "(M0+R0, MS+R0) are realizable here; this state is excluded from the RS four-arm count by "
            "design, not by omission."
        ),
    },
}

WRONG_OWNER_NOTE = (
    "Wrong-owner is demonstrated structurally rather than compiled, matching 325l's approach: "
    "build_component_general_plan_v3 raises OWNER_INVALID whenever a candidate's owner_id != "
    "current_user_id. See structural_wrong_owner_check in the report."
)


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())


def main() -> None:
    states_by_id = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    ms_candidates = {row["candidate_id"]: row for row in read_jsonl(EVOEMO_CANDIDATES) if row["component"] == "MS"}
    qualified_cards = read_jsonl(QUALIFIED_CARDS)

    missing_states = set(CURATION) - set(states_by_id)
    if missing_states:
        raise RuntimeError(f"curated state_id not found: {sorted(missing_states)}")

    development_cases: list[dict[str, Any]] = []
    manifest_calls: list[dict[str, str]] = []
    strata_counts: dict[str, int] = {}
    four_arm_complete = 0

    for state_id, meta in CURATION.items():
        state = states_by_id[state_id]
        owner = state["runtime_owner_key"]
        stratum = meta["stratum"]
        strata_counts[stratum] = strata_counts.get(stratum, 0) + 1
        ms_row = ms_candidates[meta["ms_candidate_id"]]
        assert ms_row["runtime_owner_key"] == owner

        ms_candidate = V3Candidate(
            component="MS",
            evidence_id=ms_row["candidate_id"],
            meaning_cue=MS_MEANING_CUE,
            exact_source=ms_row["literal_text"],
            owner_id=owner,
            time_status="STRICTLY_PAST",
            allowed_response_change=MS_ALLOWED_CHANGE,
            forbidden_inference=MS_FORBIDDEN,
        )

        rs_decision = rs_retrieve(
            recent_dialogue=state["visible_current_session_dialogue"], qualified_cards=qualified_cards
        )
        rs_candidate = None
        if rs_decision.status == "retrieved_top1":
            card = rs_decision.selected_card
            rs_candidate = V3Candidate(
                component="RS",
                evidence_id=str(card["card_id"]),
                meaning_cue=f"strategy_family={card.get('strategy_family')}",
                exact_source=str(card.get("retrieval_text", "")),
                owner_id=None,
                time_status="CURRENT_CARD",
                allowed_response_change="Add or sharpen one bounded strategy move only when it improves the present reply.",
                forbidden_inference="Do not let the card replace current-turn grounding or the R0 foundation.",
            )

        current_context = _compact(state["current_user_text"])
        arms: dict[str, list[dict[str, str]]] = {}

        m0_plan = build_component_general_plan_v3(
            requested_action_id="M0+R0",
            current_user_id=owner,
            candidates={"MP": None, "MS": None, "ME": None, "RS": None},
        )
        arms["M0+R0"] = response_generation_messages_v4(
            current_context=current_context, current_goal=CURRENT_GOAL, plan=m0_plan
        )

        ms_plan = build_component_general_plan_v3(
            requested_action_id="MS+R0",
            current_user_id=owner,
            candidates={"MP": None, "MS": ms_candidate, "ME": None, "RS": None},
        )
        arms["MS+R0"] = response_generation_messages_v4(
            current_context=current_context, current_goal=CURRENT_GOAL, plan=ms_plan
        )

        if rs_candidate is not None:
            rs_plan = build_component_general_plan_v3(
                requested_action_id="M0+RS",
                current_user_id=owner,
                candidates={"MP": None, "MS": None, "ME": None, "RS": rs_candidate},
            )
            arms["M0+RS"] = response_generation_messages_v4(
                current_context=current_context, current_goal=CURRENT_GOAL, plan=rs_plan
            )
            joint_plan = build_component_general_plan_v3(
                requested_action_id="MS+RS",
                current_user_id=owner,
                candidates={"MP": None, "MS": ms_candidate, "ME": None, "RS": rs_candidate},
            )
            arms["MS+RS"] = response_generation_messages_v4(
                current_context=current_context, current_goal=CURRENT_GOAL, plan=joint_plan
            )
            four_arm_complete += 1

        case = {
            "case_id": f"rsmsv2dev_{hashlib.sha256(state_id.encode()).hexdigest()[:20]}",
            "state_id": state_id,
            "runtime_owner_key": owner,
            "stratum": stratum,
            "rationale": meta["rationale"],
            "ms_exact_source": ms_row["literal_text"],
            "rs_status": rs_decision.status,
            "rs_card_id": rs_decision.selected_card.get("card_id") if rs_decision.selected_card else None,
            "arms_present": sorted(arms),
        }
        development_cases.append(case)
        for arm_name, messages in arms.items():
            manifest_calls.append(
                {
                    "case_id": case["case_id"],
                    "arm": arm_name,
                    "prompt_sha256": hashlib.sha256(
                        json.dumps(messages, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                }
            )

    structural_wrong_owner_check = _verify_wrong_owner_gate(qualified_cards)

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "development_cases_private.jsonl", development_cases)

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-panel-v2",
        "status": "ZERO_API_HAND_CURATED_PANEL_V2_READY_NO_EXECUTION_AUTHORIZED",
        "curation_method": (
            "Every state was selected by directly reading the MS candidate against the current turn "
            "for genuine information addition or the specific negative-control property claimed, not "
            "by lexical_score rank or recency. lexical_score is retained only as a reported diagnostic, "
            "not a selection rule -- see IGNORE_current_context_echo and IGNORE_topical_mismatch "
            "rationales for concrete cases where high lexical_score indicated redundancy or a false "
            "positive rather than relevance."
        ),
        "minimum_strata_required": {
            "CLEAR_USE": "at least 4 states from 4 owners",
            "ASK": "at least 2 states from 2 owners",
            "IGNORE": "at least 4 states from 4 owners, incl. current-context echo, topical "
            "mismatch/low-information, wrong-owner, stale-or-conflicting",
        },
        "strata_counts": strata_counts,
        "distinct_owners_by_stratum": {
            stratum: sorted(
                {c["runtime_owner_key"] for c in development_cases if c["stratum"] == stratum}
            )
            for stratum in strata_counts
        },
        "required_negative_controls_covered": sorted(
            {c["stratum"] for c in development_cases if c["stratum"].startswith("IGNORE")}
        ) + ["wrong_owner (structural, see wrong_owner_control)"],
        "rs_coverage": {
            "requirement": "at least 12 states must have all four M0+R0/M0+RS/MS+R0/MS+RS arms",
            "four_arm_complete_states": four_arm_complete,
            "requirement_met": four_arm_complete >= 12,
        },
        "wrong_owner_control": {
            "note": WRONG_OWNER_NOTE,
            "structural_wrong_owner_check": structural_wrong_owner_check,
        },
        "states": len(development_cases),
        "total_calls": len(manifest_calls),
        "call_budget": "<=64 (paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json panel_v2_requirements.call_budget)",
        "estimated_cost_usd": 0.0,
        "generator": "meta/llama-3.1-8b-instruct (frozen, unchanged)",
        "manifest_calls": manifest_calls,
        "gate_reference": (
            "data/pm_v1_5_contracts/paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json"
            "#panel_v2_requirements"
        ),
        "next_action": (
            "Present this exact run identity, call count, and a cost cap for explicit human approval "
            "before any generator call. No live execution is authorized by this script."
        ),
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def _verify_wrong_owner_gate(qualified_cards: list[dict[str, Any]]) -> dict[str, Any]:
    mismatched = V3Candidate(
        component="MS",
        evidence_id="wrong-owner-probe",
        meaning_cue=MS_MEANING_CUE,
        exact_source="probe past fact",
        owner_id="owner-other-than-current",
        time_status="STRICTLY_PAST",
        allowed_response_change=MS_ALLOWED_CHANGE,
        forbidden_inference=MS_FORBIDDEN,
    )
    plan = build_component_general_plan_v3(
        requested_action_id="MS+R0",
        current_user_id="owner-current",
        candidates={"MP": None, "MS": mismatched, "ME": None, "RS": None},
    )
    fired = any(resource.component == "MS" for resource in plan.resources)
    return {
        "candidate_owner": "owner-other-than-current",
        "current_user_id": "owner-current",
        "ms_resource_fired": fired,
        "projection_reason": plan.projection_reasons.get("MS"),
        "gate_holds": fired is False and plan.projection_reasons.get("MS") == "OWNER_INVALID",
    }


if __name__ == "__main__":
    main()
