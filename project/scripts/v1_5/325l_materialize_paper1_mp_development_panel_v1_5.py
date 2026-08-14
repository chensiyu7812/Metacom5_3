#!/usr/bin/env python3
"""Zero-API MP development panel, curated by hand review of real text.

Every state below was selected by reading the actual current_user_text
against the field's MP_PROFILE_SCOPE_V1 scope and the field's realization
template in v1_5_mp_profile_delta_templates_v1.py -- not by a proxy
heuristic such as "most recent candidate" (the mistake found in the
withdrawn 324l RS/MS panel: 9/16 of its MS candidates were content-free
greetings because recency was never checked against real relevance).　The
review below is disclosed per state so it can be second-guessed.

Two arms per CONSTRAIN_eligible state (M0+R0, MP+R0); one arm for each
IGNORE control that has no MP candidate at all (M0+R0 only, since there is
nothing to withhold); IGNORE controls that do carry a scope-matched MP
candidate still get both arms, because their value as a control is in
showing the compiler resolves them to IGNORE, not in withholding the
candidate. Per paper1_mp_rule_based_step1_v1.json panel_v1_requirements.

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
from metacom_pm.v1_5_mp_profile_delta_templates_v1 import mp_realization_template  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402

EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_mp_development_panel_20260813"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."

# state_id -> (stratum, rationale). Rationale is written from a direct read
# of current_user_text and the MP candidate's literal_text, before any
# compiled prompt or generation exists (outcome-blind).
CURATION: dict[str, dict[str, str]] = {
    "evo::p2::esc955::seeker_turn::8": {
        "stratum": "CONSTRAIN_eligible",
        "field": "age",
        "rationale": (
            "'I'm just starting my adult life I want to enjoy it' is a direct, non-idiomatic "
            "life-stage statement -- the age=20 profile fact genuinely intersects the age "
            "template's 'age-linked practical detail' scope, unlike an idiom such as 'ages'."
        ),
    },
    "evo::p8::p8_conv_14::seeker_turn::2": {
        "stratum": "CONSTRAIN_eligible",
        "field": "age",
        "rationale": (
            "'My birthday made me reflect on things' directly invokes the seeker's own age "
            "milestone, not a generic word overlap."
        ),
    },
    "evo::p2::esc1091::seeker_turn::1": {
        "stratum": "CONSTRAIN_eligible",
        "field": "education",
        "rationale": (
            "'I wanted to talk about my academic pressures' is squarely on-topic for the "
            "education template's 'academic pressures / next step' scope, not an incidental "
            "mention of a third party's school."
        ),
    },
    "evo::p3::esc207::seeker_turn::10": {
        "stratum": "CONSTRAIN_eligible",
        "field": "location",
        "rationale": (
            "'staying with them for the holidays and then going back home in January' is real "
            "travel/logistics content the location template's scope names explicitly, not a "
            "metaphorical use of a location word."
        ),
    },
    "evo::p1::esc1024::seeker_turn::5": {
        "stratum": "CONSTRAIN_eligible",
        "field": "job",
        "rationale": (
            "'i did a lot of work going to bed i just slept like 1 hour only' is a genuine "
            "work/sleep logistics complaint the job template's timing/feasibility scope covers."
        ),
    },
    "evo::p7::esc75::seeker_turn::13": {
        "stratum": "CONSTRAIN_eligible",
        "field": "gender",
        "rationale": (
            "'I could say I am a female that is one of those left out' is the seeker "
            "foregrounding their own gender identity in the immediate complaint, not an "
            "incidental mention of someone else's gender."
        ),
    },
    "evo::p9::esc88::seeker_turn::9": {
        "stratum": "IGNORE_current_context_redundant",
        "field": "gender",
        "rationale": (
            "current_user_text is literally 'Male. Why do you ask?' -- the MP candidate "
            "'gender: male' states nothing the current turn does not already say verbatim. "
            "Confirmed via source metadata: candidate available_after_session_index=0 "
            "(ONBOARDING_BASIC_INFO), state source_session_index=2."
        ),
    },
    "evo::p13::p13_conv_10::seeker_turn::8": {
        "stratum": "IGNORE_topical_mismatch",
        "field": "nationality",
        "rationale": (
            "'we're speaking different languages on this topic' is the idiom for "
            "miscommunication, not a literal reference to language/nationality -- it only "
            "scope-matched on the literal word 'language'. Same failure class as the RS/MS "
            "root-repair's diagnosed false positives."
        ),
    },
    "evo::p9::p9_conv_4::seeker_turn::16": {
        "stratum": "IGNORE_topical_mismatch",
        "field": "age",
        "rationale": (
            "'it feels like ages since I picked it up' is the idiom for a long time, not a "
            "reference to the seeker's actual age -- only scope-matched on the literal word "
            "'ages'."
        ),
    },
    "evo::p4::esc837::seeker_turn::5": {
        "stratum": "IGNORE_natural_off",
        "field": None,
        "rationale": (
            "'It is the thought of getting nervous in front of people and forgetting what I "
            "want to say' -- real, substantive current-turn content (not a greeting), and "
            "rank_mp() returns candidate_present=False: no field's scope matches. A genuine "
            "natural-off control, not a content-free opener."
        ),
    },
}

WRONG_OWNER_NOTE = (
    "Wrong-owner is demonstrated structurally rather than compiled: "
    "build_component_general_plan_v3 raises OWNER_INVALID whenever a candidate's owner_id != "
    "current_user_id (v1_5_component_general_v3.py). Feeding the compiler a real cross-owner "
    "pair would require bypassing that hard gate, which this panel will not do. See "
    "structural_wrong_owner_check below for the direct verification instead."
)


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())


def main() -> None:
    states_by_id = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    candidates = read_jsonl(EVOEMO_CANDIDATES)
    mp_by_owner_field: dict[tuple[str, str], dict[str, Any]] = {}
    for row in candidates:
        if row["component"] == "MP":
            mp_by_owner_field[(row["runtime_owner_key"], row["profile_field"])] = row

    missing = set(CURATION) - set(states_by_id)
    if missing:
        raise RuntimeError(f"curated state_id not found in EvoEmo states: {sorted(missing)}")

    development_cases: list[dict[str, Any]] = []
    manifest_calls: list[dict[str, str]] = []
    strata_counts: dict[str, int] = {}

    for state_id, meta in CURATION.items():
        state = states_by_id[state_id]
        owner = state["runtime_owner_key"]
        field = meta["field"]
        stratum = meta["stratum"]
        strata_counts[stratum] = strata_counts.get(stratum, 0) + 1

        candidate_row = mp_by_owner_field.get((owner, field)) if field else None
        candidates_map: dict[str, V3Candidate | None] = {"MP": None, "MS": None, "ME": None, "RS": None}
        if candidate_row is not None:
            template = mp_realization_template(field)
            candidates_map["MP"] = V3Candidate(
                component="MP",
                evidence_id=candidate_row["candidate_id"],
                meaning_cue=template.meaning_cue,
                exact_source=candidate_row["literal_text"],
                owner_id=owner,
                time_status="STRICTLY_PAST",
                allowed_response_change=template.allowed_response_change,
                forbidden_inference=template.forbidden_inference,
            )

        m0_plan = build_component_general_plan_v3(
            requested_action_id="M0+R0",
            current_user_id=owner,
            candidates={"MP": None, "MS": None, "ME": None, "RS": None},
        )
        m0_prompt = response_generation_messages_v4(
            current_context=_compact(state["current_user_text"]),
            current_goal=CURRENT_GOAL,
            plan=m0_plan,
        )

        arms = {"M0+R0": m0_prompt}
        if candidate_row is not None:
            mp_plan = build_component_general_plan_v3(
                requested_action_id="MP+R0",
                current_user_id=owner,
                candidates=candidates_map,
            )
            mp_prompt = response_generation_messages_v4(
                current_context=_compact(state["current_user_text"]),
                current_goal=CURRENT_GOAL,
                plan=mp_plan,
            )
            arms["MP+R0"] = mp_prompt

        case = {
            "case_id": f"mpdev_{hashlib.sha256(state_id.encode()).hexdigest()[:20]}",
            "state_id": state_id,
            "runtime_owner_key": owner,
            "stratum": stratum,
            "profile_field": field,
            "rationale": meta["rationale"],
            "ms_exact_source": candidate_row["literal_text"] if candidate_row else None,
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

    structural_wrong_owner_check = _verify_wrong_owner_gate()

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "development_cases_private.jsonl", development_cases)

    report = {
        "protocol": "pm-v1.5-paper1-mp-development-panel-v1",
        "status": "ZERO_API_HAND_CURATED_PANEL_READY_NO_EXECUTION_AUTHORIZED",
        "curation_method": (
            "Every state was selected by reading current_user_text against the field's "
            "MP_PROFILE_SCOPE_V1 scope and its realization template before any prompt was "
            "compiled -- not by a proxy heuristic. Per-state rationale is in "
            "development_cases_private.jsonl and this report."
        ),
        "minimum_strata_required": {
            "CONSTRAIN_eligible": "at least 4 states, at least 3 distinct field types",
            "IGNORE_controls": "at least 4 states covering current-context-redundant, topical "
            "mismatch, wrong-owner (structural), and natural-off",
        },
        "strata_counts": strata_counts,
        "distinct_constrain_field_types": sorted(
            {c["profile_field"] for c in development_cases if c["stratum"] == "CONSTRAIN_eligible"}
        ),
        "wrong_owner_control": {
            "note": WRONG_OWNER_NOTE,
            "structural_wrong_owner_check": structural_wrong_owner_check,
        },
        "states": len(development_cases),
        "total_calls": len(manifest_calls),
        "estimated_cost_usd": 0.0,
        "generator": "meta/llama-3.1-8b-instruct (frozen, unchanged)",
        "manifest_calls": manifest_calls,
        "gate_reference": "data/pm_v1_5_contracts/paper1_mp_rule_based_step1_v1.json#panel_v1_requirements",
        "next_action": (
            "Present this exact run identity, call count, and a cost cap for explicit human "
            "approval before any generator call. No live execution is authorized by this script."
        ),
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


def _verify_wrong_owner_gate() -> dict[str, Any]:
    template = mp_realization_template("job")
    mismatched_candidate = V3Candidate(
        component="MP",
        evidence_id="wrong-owner-probe",
        meaning_cue=template.meaning_cue,
        exact_source="job: probe",
        owner_id="owner-other-than-current",
        time_status="STRICTLY_PAST",
        allowed_response_change=template.allowed_response_change,
        forbidden_inference=template.forbidden_inference,
    )
    plan = build_component_general_plan_v3(
        requested_action_id="MP+R0",
        current_user_id="owner-current",
        candidates={"MP": mismatched_candidate, "MS": None, "ME": None, "RS": None},
    )
    fired = any(resource.component == "MP" for resource in plan.resources)
    return {
        "candidate_owner": "owner-other-than-current",
        "current_user_id": "owner-current",
        "mp_resource_fired": fired,
        "projection_reason": plan.projection_reasons.get("MP"),
        "gate_holds": fired is False and plan.projection_reasons.get("MP") == "OWNER_INVALID",
    }


if __name__ == "__main__":
    main()
