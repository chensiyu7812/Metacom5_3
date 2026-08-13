#!/usr/bin/env python3
"""First-party Function Observability V2 review of the 50 real RS/MS Panel
V2 results (329l), applying the CLEAR/PLAUSIBLE/NONE/UNCERTAIN taxonomy from
paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json.

Review unit: M0+R0 vs MS+R0 reply pair per state (the MS main-effect
comparison the panel was built to answer). RS/interaction arms (M0+RS,
MS+RS) are read for a qualitative composition check, not scored against the
CLEAR/PLAUSIBLE/NONE/UNCERTAIN taxonomy -- that requires its own dedicated
review, out of scope here.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_live_20260813"
CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_20260813/development_cases_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_function_review_20260813"

MS_REVIEW: dict[str, dict[str, str]] = {
    "rsmsv2dev_ec683fee6550e869fdf7": {
        "verdict": "CLEAR",
        "rationale": (
            "M0+R0 says only 'this conversation has stirred up strong emotions and memories'. "
            "MS+R0 names the specific trigger: 'this TRIP is stirring up a mix of emotions' -- "
            "'trip' does not appear anywhere in current_user_text and is not derivable from current "
            "context alone; it is the MS fact's content (Jack's weekend trip) surfacing concretely."
        ),
    },
    "rsmsv2dev_c7ea7f443a30aa1c4079": {
        "verdict": "NONE",
        "rationale": (
            "Both replies discuss guilt/gratitude toward David generically; neither mentions grief "
            "or any content specific to the MS fact beyond what current context ('mentioned it to "
            "David... burden him with my issues') already supplies."
        ),
    },
    "rsmsv2dev_c83df3b458e411c8967b": {
        "verdict": "NONE",
        "rationale": "Both replies are near-identical generic 'holding onto calm from the weekend' framing; neither mentions the podcast or any concrete coping method.",
    },
    "rsmsv2dev_4d41ab4699893879841f": {
        "verdict": "NONE",
        "rationale": (
            "Both replies stay at the same level of generality already supported by current_user_text "
            "('the job offer', 'what-if'); MS+R0's 'your decision' phrasing is too weak to count as "
            "specific attribution to the California/turned-down fact -- not clearly distinguishable "
            "from a lucky generic paraphrase."
        ),
    },
    "rsmsv2dev_8b84438410c171f16d98": {
        "verdict": "CLEAR",
        "rationale": (
            "M0+R0 is fully generic ('need reassurance ... navigating challenging situations'). "
            "MS+R0 explicitly names 'the connection you felt with Emily' -- neither the name nor the "
            "referent appears anywhere in current_user_text ('reassurance that I'm on the right "
            "path'); this is concrete, source-attributable content."
        ),
    },
}

ASK_REVIEW: dict[str, dict[str, str]] = {
    "rsmsv2dev_f93e8ff6415e40016d4d": {
        "verdict": "UNCERTAIN",
        "rationale": (
            "MS+R0 adds 'especially when you're used to having someone to talk to' -- a plausible "
            "faint echo of the past pet-loss chat, but it never names the past event or asks a "
            "tentative check-in question; too weak to confidently attribute, not confidently NONE "
            "either."
        ),
    },
    "rsmsv2dev_2c4e956399b940a8f788": {
        "verdict": "NONE",
        "rationale": "Both replies are generic isolation/support language; neither references family or academic pressure content from the MS fact.",
    },
}

IGNORE_CHECK: dict[str, str] = {
    "rsmsv2dev_b6a8f7815b17c462eb2b": "current_context_echo: MS+R0 stays generic gratitude language, no forced content.",
    "rsmsv2dev_f0706b128ef3e2165702": "topical_mismatch: MS+R0 stays on the current protect-others topic; no leak of the unrelated infidelity-temptation fact.",
    "rsmsv2dev_cebea31eb849ee2d32be": "topical_mismatch: MS+R0 stays on the current work-opportunity topic; no leak of the unrelated banana-chips fact.",
    "rsmsv2dev_48097cb6b5296d31c0d1": "stale_or_conflicting: MS+R0 correctly says 'full-time job', matching the current-turn update, not the stale part-time MS fact -- current context correctly wins.",
    "rsmsv2dev_3cacbd91bd06099ec6e5": "low_information_greeting: MS+R0 stays generic; the content-free greeting candidate produces no fabricated content.",
    "rsmsv2dev_3fc266bde1c92797c673": "rs_structurally_ineligible: only M0+R0/MS+R0 arms exist as designed; no RS content appears.",
}

INTERACTION_NOTE = (
    "Qualitative check on the two CLEAR cases' RS/MS+RS arms: for rsmsv2dev_ec683fee6550e869fdf7 "
    "(Jack/trip), MS+RS keeps 'weekend trip' when RS is added -- MS content survives composition. "
    "For rsmsv2dev_8b84438410c171f16d98 (Emily), MS+RS DROPS the 'Emily' mention that MS+R0 produced -- "
    "the RS delta appears to have crowded out the MS delta in this one case. This is a real, disclosed "
    "mixed finding on n=2, not a resolved question: RS-MS composition does not always preserve MS "
    "content when both fire together, and this needs a larger, dedicated interaction check before any "
    "claim about joint RS+MS behavior, separate from the MS main-effect finding below."
)


def main() -> None:
    cases = {row["case_id"]: row for row in (json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l)}
    ms_targets = [cid for cid, c in cases.items() if c["stratum"] == "CLEAR_USE"]
    ask_targets = [cid for cid, c in cases.items() if c["stratum"] == "ASK"]
    missing = (set(ms_targets) - set(MS_REVIEW)) | (set(ask_targets) - set(ASK_REVIEW))
    if missing:
        raise RuntimeError(f"unreviewed cases: {sorted(missing)}")

    clear = [cid for cid in ms_targets if MS_REVIEW[cid]["verdict"] == "CLEAR"]
    plausible = [cid for cid in ms_targets if MS_REVIEW[cid]["verdict"] == "PLAUSIBLE"]
    none_ = [cid for cid in ms_targets if MS_REVIEW[cid]["verdict"] == "NONE"]
    owners_clear_or_plausible = {cases[cid]["runtime_owner_key"] for cid in clear + plausible}

    development_promotion = {
        "requirement": (
            "promote_repaired_treatment_when: at least one CLEAR or at least two CLEAR-or-PLAUSIBLE "
            "cases across at least two owners "
            "(paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json#function_observability_v2"
            ".development_decision_rule)"
        ),
        "observed": {
            "CLEAR": len(clear),
            "PLAUSIBLE": len(plausible),
            "NONE": len(none_),
            "UNCERTAIN": len([cid for cid in ask_targets if ASK_REVIEW[cid]["verdict"] == "UNCERTAIN"]),
        },
        "clear_case_ids": clear,
        "distinct_owners_clear_or_plausible": len(owners_clear_or_plausible),
        "requirement_met": len(clear) >= 1 or (len(clear) + len(plausible) >= 2 and len(owners_clear_or_plausible) >= 2),
    }

    report = {
        "protocol": "pm-v1.5-rs-ms-panel-v2-function-review-v1",
        "status": "MS_DEVELOPMENT_PROMOTION_MET_ON_MAIN_EFFECT" if development_promotion["requirement_met"] else "MS_DEVELOPMENT_BLOCKED",
        "method": (
            "First-party (not independent/blind) direct comparison of the real M0+R0 vs MS+R0 reply "
            "pair for each of the 5 CLEAR_USE and 2 ASK states. used_evidence_ids was empty ([]) on "
            "every one of the 50 calls -- self-citation telemetry remains uninformative on this "
            "generator; only reply-text comparison was used."
        ),
        "clear_use_review": {cid: MS_REVIEW[cid] for cid in ms_targets},
        "ask_review": {cid: ASK_REVIEW[cid] for cid in ask_targets},
        "ignore_control_check": IGNORE_CHECK,
        "rs_ms_interaction_note": INTERACTION_NOTE,
        "development_promotion": development_promotion,
        "interpretation": (
            "Unlike MP, MS's repaired R0-delta treatment shows two clean CLEAR cases from two "
            "distinct owners (Jack/weekend-trip and Emily-connection), each naming specific, "
            "current-context-unrecoverable content -- meeting the development_promotion bar on this "
            "small panel. This is directional development evidence, not a formal MS_pass: n=5 "
            "CLEAR_USE opportunities, first-party non-blind review, one generator, one panel. The "
            "RS-MS interaction finding (Emily case losing its MS content once RS also fires) is a "
            "real caution that must be checked at scale before any joint-arm claim."
        ),
        "next_action": (
            "MS development is not blocked; proceed toward MS's formal external closure (EvoEmo + "
            "ES-MemEval) under the repaired V4 compiler, per paper1_rs_ms_r0_delta_measurement_and_"
            "panel_revision_v2.json#formal_first_pm_ms_closure. RS's own delta-level Function was not "
            "separately scored here (out of scope for this review) and needs its own pass before RS_pass."
        ),
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
