#!/usr/bin/env python3
"""First-party Function Observability V2 review of the 19 real MP panel
results (327l), applying the CLEAR/PLAUSIBLE/NONE/UNCERTAIN taxonomy from
paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json generalized to
MP, per paper1_mp_rule_based_step1_v1.json#measurement_reuse.

Review unit: blind* same-state M0+R0 vs MP+R0 reply pair (*not blinded to
arm identity here since this is a first-party diagnostic read, same caveat
already logged for the 323l MS review -- not independent human/judge Function
evidence, only a development-panel diagnostic).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "outputs/pm_v1_5_paper1_mp_development_panel_live_20260813"
CASES = ROOT / "outputs/pm_v1_5_paper1_mp_development_panel_20260813/development_cases_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_mp_development_panel_function_review_20260813"

# Verdict + rationale written from direct comparison of the two real replies
# for each CONSTRAIN_eligible case; see live/generator_results_private.jsonl
# for the source text.
REVIEW: dict[str, dict[str, str]] = {
    "mpdev_894698741e3be2b55a8d": {
        "verdict": "NONE",
        "rationale": (
            "Current turn already says 'I'm just starting my adult life' verbatim -- both arms "
            "independently produce the same life-stage framing from current context alone. No "
            "content attributable to the stored age=20 fact beyond what current context supplies."
        ),
    },
    "mpdev_3c8a5e1a4b4d1c77bf76": {
        "verdict": "NONE",
        "rationale": (
            "Both replies are generic birthday/reflection framing; neither shows an age-conditioned "
            "adjustment (no life-stage-specific wording, no age=29-consistent framing beyond what "
            "'my birthday' already implies)."
        ),
    },
    "mpdev_08996f5e142349d4cbda": {
        "verdict": "NONE",
        "rationale": (
            "The two replies are near-identical with only synonym-level rewording ('feeling "
            "better'->'feeling less overwhelmed'). No education-specific content (no campus/academic "
            "resource framing) appears in the MP+R0 arm."
        ),
    },
    "mpdev_f15c1f4b4407ba2c62e1": {
        "verdict": "NONE",
        "rationale": (
            "MP+R0 references 'transition back home in January', but that detail is already stated "
            "verbatim in current_user_text -- this is R0 current-context attentiveness, not use of "
            "the stored location=London fact. No content that could only come from the profile fact "
            "appears."
        ),
    },
    "mpdev_1f1980353a56ab908b64": {
        "verdict": "NONE",
        "rationale": (
            "Neither reply proposes any timing/logistics suggestion at all (the job template's "
            "allowed_response_change scope) -- both are generic acknowledgements of exhaustion. No "
            "job-context-conditioned content to observe."
        ),
    },
    "mpdev_1c32475aed3381250bd0": {
        "verdict": "NONE",
        "rationale": (
            "MP+R0 is more validating in tone ('takes a lot of courage to acknowledge...') than "
            "M0+R0, but this is generic warmth/affect, not a gender-specific content difference (no "
            "pronoun-consistency change, no gendered framing) -- explicitly excluded from CLEAR by "
            "the Function Observability V2 definition."
        ),
    },
}

IGNORE_CHECK: dict[str, dict[str, str]] = {
    "mpdev_7b98b1d596ce3447e678": {
        "finding": "NO_FORCED_USE",
        "note": (
            "MP+R0 adds pronoun-consistency language ('use the correct pronouns'), but the gender "
            "fact is already stated verbatim in current_user_text ('Male. Why do you ask?'), so this "
            "is not evidence of using withheld past information -- correctly explained by current "
            "context, matching the control's design."
        ),
    },
    "mpdev_d377ac27928c4917b2fe": {
        "finding": "NO_FORCED_USE",
        "note": "Neither arm introduces nationality-specific content; both stay on the miscommunication topic.",
    },
    "mpdev_92a158d318694a631bd6": {
        "finding": "NO_FORCED_USE",
        "note": "Neither arm introduces age-specific content; both stay on the guitar/time topic.",
    },
}


def main() -> None:
    cases = {row["case_id"]: row for row in (json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l)}
    results = {
        (row["case_id"], row["arm"]): row
        for row in (json.loads(l) for l in (LIVE / "generator_results_private.jsonl").read_text(encoding="utf-8").splitlines() if l)
    }

    constrain_cases = [cid for cid, c in cases.items() if c["stratum"] == "CONSTRAIN_eligible"]
    missing = set(constrain_cases) - set(REVIEW)
    if missing:
        raise RuntimeError(f"unreviewed CONSTRAIN_eligible cases: {sorted(missing)}")

    clear = [cid for cid in constrain_cases if REVIEW[cid]["verdict"] == "CLEAR"]
    plausible = [cid for cid in constrain_cases if REVIEW[cid]["verdict"] == "PLAUSIBLE"]
    none_ = [cid for cid in constrain_cases if REVIEW[cid]["verdict"] == "NONE"]
    uncertain = [cid for cid in constrain_cases if REVIEW[cid]["verdict"] == "UNCERTAIN"]
    distinct_owners_clear_or_plausible = {
        cases[cid]["stratum"] and results[(cid, "MP+R0")]["state_id"].split("::")[1]
        for cid in clear + plausible
    }

    development_promotion = {
        "requirement": (
            "promote_repaired_treatment_when: at least one CLEAR or at least two CLEAR-or-PLAUSIBLE "
            "cases across at least two owners (paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2"
            ".json#function_observability_v2.development_decision_rule, generalized to MP per "
            "paper1_mp_rule_based_step1_v1.json#measurement_reuse)"
        ),
        "observed": {"CLEAR": len(clear), "PLAUSIBLE": len(plausible), "NONE": len(none_), "UNCERTAIN": len(uncertain)},
        "distinct_owners_clear_or_plausible": len(distinct_owners_clear_or_plausible),
        "requirement_met": len(clear) >= 1 or (len(clear) + len(plausible) >= 2 and len(distinct_owners_clear_or_plausible) >= 2),
    }

    block_condition = {
        "condition": "all prospectively defined clear-use opportunities are NONE/UNCERTAIN with no observable source-conditioned contribution",
        "met": len(clear) == 0 and len(plausible) == 0,
    }

    report = {
        "protocol": "pm-v1.5-mp-development-panel-function-review-v1",
        "status": "MP_DEVELOPMENT_BLOCKED_ZERO_OBSERVABLE_CONTRIBUTION" if block_condition["met"] else "MP_DEVELOPMENT_REVIEW_COMPLETE",
        "method": (
            "First-party (not independent/blind) direct comparison of the real M0+R0 vs MP+R0 reply "
            "pair for each of the 6 CONSTRAIN_eligible states, using the CLEAR/PLAUSIBLE/NONE/"
            "UNCERTAIN taxonomy. used_evidence_ids was empty ([]) on every single call across all 19 -- "
            "self-citation telemetry is uninformative here, consistent with the unreliable self-citation "
            "pattern already found for RS and MS this session on this same generator."
        ),
        "constrain_eligible_review": {cid: REVIEW[cid] for cid in constrain_cases},
        "ignore_control_check": IGNORE_CHECK,
        "development_promotion": development_promotion,
        "block_condition": block_condition,
        "interpretation": (
            "The code-level repair (real Step2 realization content, forced CONSTRAIN/IGNORE decision) "
            "was necessary but not sufficient: 0/6 CONSTRAIN_eligible cases show any observable, "
            "source-conditioned reply difference on this frozen Llama 3.1 8B generator at this sample "
            "size. All differences between M0+R0 and MP+R0 are generic paraphrase/warmth variation, "
            "explicitly excluded from CLEAR by the Function Observability V2 definition. Negative "
            "controls held (no forced/hallucinated MP content on mismatch/redundant states). This does "
            "not prove MP cannot work -- it is one small, disclosed panel on a weak generator -- but it "
            "does not meet the development_promotion bar and must not be reported as a pass."
        ),
        "next_action": (
            "Do not promote MP development on this evidence. Two honest paths forward: (a) test "
            "whether a stronger, outcome-blind-qualified generator (deferred by standing policy until "
            "current-generator qualification) can realize the same CONSTRAIN decisions concretely, or "
            "(b) redesign the panel with states where a concrete suggestion/logistics slot is already "
            "present in the R0 reply, since none of these 6 replies proposed any concrete suggestion "
            "for the profile fact to visibly modify."
        ),
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
