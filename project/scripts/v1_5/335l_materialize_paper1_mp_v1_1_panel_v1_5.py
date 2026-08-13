#!/usr/bin/env python3
"""MP Panel V1.1: owner-unique (across the WHOLE panel, not just per
stratum -- the exact bug found and corrected in paper1_panel_v2_owner_
cluster_correction_and_roadmap_v1.json), and CONSTRAIN candidates are
curated for states where the query itself plausibly warrants a concrete,
modifiable suggestion/logistics/timing element -- not just any state where
MP_PROFILE_SCOPE_V1 happens to word-match. This operationalizes step_3_root_
fix_mp's 'R0 plan must already contain a concrete slot' requirement for
zero-API panel curation: a state only qualifies if its query text plausibly
invites a concrete suggestion (decision/logistics/scheduling language), not
merely emotional reflection.

Honest corpus disclosure: only job and education fields yielded genuine
concrete-slot candidates on manual review; location-field MP facts almost
never co-occur with a genuine suggestion-slot query in this corpus (most
location-scope matches are 'moving forward'/'moving on' idioms, the same
false-positive class already diagnosed for RS/MS). gender/nationality are
excluded per the root-fix decision (default IGNORE). age is excluded from
this panel version pending a genuine objective life-stage-constraint
example (none found on this pass).

No generator call is made here.
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
from metacom_pm.text import dialogue_text  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_mp_profile_delta_templates_v1 import mp_realization_template  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402

EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_mp_v1_1_panel_20260813"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."

CURATION: dict[str, dict[str, Any]] = {
    "evo::p1::esc1172::seeker_turn::2": {
        "stratum": "CONSTRAIN_eligible", "field": "job",
        "rationale": "'What can I do to make it stop?' (a boss harassing a coworker) directly invites a concrete suggestion (who to approach, e.g. HR vs. informal channel) that an office-worker job context could plausibly shape.",
    },
    "evo::p13::p13_conv_5::seeker_turn::16": {
        "stratum": "CONSTRAIN_eligible", "field": "job",
        "rationale": "'Considering having a talk with my manager about my workload... hopeful he'll support a more manageable schedule' is directly about job scheduling -- a concrete slot a job fact could shape (e.g. timing feasibility).",
    },
    "evo::p16::p16_conv_4::seeker_turn::18": {
        "stratum": "CONSTRAIN_eligible", "field": "job",
        "rationale": "'Between work stress and personal life, it's been challenging to find time for myself' invites a concrete timing suggestion that job context (schedule type) could shape.",
    },
    "evo::p18::esc552::seeker_turn::13": {
        "stratum": "CONSTRAIN_eligible", "field": "job",
        "rationale": "'Some colleagues are given an option to log out early, whereas some of us have to slog' invites a concrete suggestion about raising a scheduling-fairness issue at work.",
    },
    "evo::p15::esc119::seeker_turn::6": {
        "stratum": "CONSTRAIN_eligible", "field": "education",
        "rationale": "Difficult class, unresponsive professor, grades suffering despite TA help -- invites a concrete suggestion (e.g. an academic-support resource) a student/education context could shape.",
    },
    "evo::p8::esc995::seeker_turn::18": {
        "stratum": "IGNORE_current_context_redundant", "field": "job",
        "rationale": "Current turn already states 'My employer is a well known organization that employees over 3,000 people' -- the job=employee fact is already visible, correctly redundant.",
    },
    "evo::p9::p9_conv_14::seeker_turn::1": {
        "stratum": "IGNORE_current_context_redundant", "field": "education",
        "rationale": "Current turn already says 'reconnected with an old high school friend' -- the education=high school fact is already visible, correctly redundant.",
    },
    "evo::p2::esc1091::seeker_turn::4": {
        "stratum": "IGNORE_natural_off", "field": None,
        "rationale": "'Needed someone to talk to about my stress and workload. I don't know what to do with these horrible group members.' -- real, substantive content, no MP field scope matches (rank_mp candidate_present=False).",
    },
}

WRONG_OWNER_NOTE = (
    "Wrong-owner is demonstrated structurally (build_component_general_plan_v3 raises "
    "OWNER_INVALID whenever a candidate's owner_id != current_user_id), matching the pattern "
    "already used for the MP development panel (325l) and RS/MS Panel V2 (326l)."
)


def _verify_owner_unique(curation: dict[str, dict[str, Any]], states_by_id: dict[str, Any]) -> None:
    owners = [states_by_id[sid]["runtime_owner_key"] for sid in curation]
    if len(owners) != len(set(owners)):
        raise RuntimeError(f"owner-uniqueness violated: {owners}")


def main() -> None:
    states_by_id = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    candidates = read_jsonl(EVOEMO_CANDIDATES)
    mp_by_owner_field: dict[tuple[str, str], dict[str, Any]] = {}
    for row in candidates:
        if row["component"] == "MP":
            mp_by_owner_field[(row["runtime_owner_key"], row["profile_field"])] = row

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
        field = meta["field"]
        stratum = meta["stratum"]
        strata_counts[stratum] = strata_counts.get(stratum, 0) + 1
        full_context = dialogue_text(state["visible_current_session_dialogue"])

        candidate_row = mp_by_owner_field.get((owner, field)) if field else None
        candidates_map: dict[str, V3Candidate | None] = {"MP": None, "MS": None, "ME": None, "RS": None}
        if candidate_row is not None:
            template = mp_realization_template(field)
            candidates_map["MP"] = V3Candidate(
                component="MP", evidence_id=candidate_row["candidate_id"],
                meaning_cue=template.meaning_cue, exact_source=candidate_row["literal_text"],
                owner_id=owner, time_status="STRICTLY_PAST",
                allowed_response_change=template.allowed_response_change,
                forbidden_inference=template.forbidden_inference,
            )

        m0_plan = build_component_general_plan_v3(
            requested_action_id="M0+R0", current_user_id=owner,
            candidates={"MP": None, "MS": None, "ME": None, "RS": None},
        )
        m0_prompt = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=m0_plan)
        arms = {"M0+R0": m0_prompt}
        if candidate_row is not None:
            mp_plan = build_component_general_plan_v3(requested_action_id="MP+R0", current_user_id=owner, candidates=candidates_map)
            arms["MP+R0"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=mp_plan)

        case = {
            "case_id": f"mpv11_{hashlib.sha256(state_id.encode()).hexdigest()[:20]}",
            "state_id": state_id, "runtime_owner_key": owner, "stratum": stratum,
            "profile_field": field, "rationale": meta["rationale"],
            "mp_exact_source": candidate_row["literal_text"] if candidate_row else None,
            "arms_present": sorted(arms), "used_full_context": True,
        }
        development_cases.append(case)
        for arm_name, messages in arms.items():
            manifest_calls.append({
                "case_id": case["case_id"], "arm": arm_name,
                "prompt_sha256": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
            })

    structural_wrong_owner_check = _verify_wrong_owner_gate()

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "development_cases_private.jsonl", development_cases)

    report = {
        "protocol": "pm-v1.5-paper1-mp-v1-1-panel",
        "status": "ZERO_API_OWNER_UNIQUE_FULL_CONTEXT_PANEL_READY_NO_EXECUTION_AUTHORIZED",
        "curation_method": (
            "CONSTRAIN candidates selected only where the query text plausibly invites a concrete "
            "suggestion/logistics/scheduling response (operationalizing step_3_root_fix_mp's "
            "'R0 must already have a modifiable slot' requirement for zero-API curation). All "
            "prompts compiled with the FULL visible_current_session_dialogue via text.dialogue_text, "
            "not current_user_text alone."
        ),
        "owner_uniqueness": "verified: one state per owner across the WHOLE panel, not just per stratum",
        "corpus_disclosure": (
            "Only job and education fields yielded genuine concrete-slot CONSTRAIN candidates on "
            "manual review of this corpus; location-field candidates were almost all 'moving "
            "forward/on' idiom false positives. This panel has 5 CONSTRAIN states (short of the "
            "original >=6 target), 2 field types, not 3. gender/nationality excluded (default "
            "IGNORE per root-fix decision); age excluded (no genuine life-stage-constraint example found)."
        ),
        "strata_counts": strata_counts,
        "distinct_owners": len({c["runtime_owner_key"] for c in development_cases}),
        "wrong_owner_control": {"note": WRONG_OWNER_NOTE, "structural_wrong_owner_check": structural_wrong_owner_check},
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


def _verify_wrong_owner_gate() -> dict[str, Any]:
    template = mp_realization_template("job")
    mismatched = V3Candidate(
        component="MP", evidence_id="wrong-owner-probe", meaning_cue=template.meaning_cue,
        exact_source="job: probe", owner_id="owner-other-than-current", time_status="STRICTLY_PAST",
        allowed_response_change=template.allowed_response_change, forbidden_inference=template.forbidden_inference,
    )
    plan = build_component_general_plan_v3(
        requested_action_id="MP+R0", current_user_id="owner-current",
        candidates={"MP": mismatched, "MS": None, "ME": None, "RS": None},
    )
    fired = any(resource.component == "MP" for resource in plan.resources)
    return {
        "mp_resource_fired": fired, "projection_reason": plan.projection_reasons.get("MP"),
        "gate_holds": fired is False and plan.projection_reasons.get("MP") == "OWNER_INVALID",
    }


if __name__ == "__main__":
    main()
