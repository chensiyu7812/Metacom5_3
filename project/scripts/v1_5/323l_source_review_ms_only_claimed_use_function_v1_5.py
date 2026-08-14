#!/usr/bin/env python3
"""Zero-API independent source review of the 6 MS-only claimed-use rows plus
all 13 matched safe-nonuse controls, per execution_order[0] of
paper1_rs_ms_r0_delta_root_repair_v1.json.

This is a first-party (not a paid judge) review: each case is read directly
against the MS_delta USE/ASK/IGNORE definition ("A specific, strictly past,
user-owned, relevant, non-conflicting fact contributes information not
recoverable from current context alone") and judged by hand, with the exact
textual evidence cited for every verdict. No generator or judge calls are
made -- this only reads already-collected outputs.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/pm_v1_5_ms_only_claimed_use_source_review_20260813"

# Each entry: case_id, verdict (CONFIRMED_FUNCTION / NOT_CONFIRMED), and the
# specific textual evidence the verdict rests on. Written by direct reading
# of current_context vs ms_exact_source vs final_reply for all 6 claimed-use
# rows -- see outputs/pm_v1_5_paper1_ms_only_ablation_live_20260812/ and
# outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/.
CLAIMED_USE_REVIEW = [
    {
        "case_id": "rsmsext_02f756fb7cf2c8519020d524",
        "verdict": "NOT_CONFIRMED",
        "rationale": (
            "Past source is about bouncing between classes and wanting to do one class at a time. "
            "The reply only answers the current turn's literal question ('what types of skill can I "
            "gain online?') with platform names (Coursera, LinkedIn Learning, edX) and a career-interest "
            "question. Nothing in the reply reflects the class-bouncing/one-at-a-time content. "
            "self-citation is a false positive: fully explainable from current context alone."
        ),
    },
    {
        "case_id": "rsmsext_0cefe2d6249593d3d57ed295",
        "verdict": "NOT_CONFIRMED",
        "rationale": (
            "Past source is about exercising more since a check-up to ease stress. The reply only "
            "references the hike already stated in the current turn and asks about work stress -- both "
            "fully recoverable from current context. No trace of the exercise/check-up content. "
            "self-citation is a false positive."
        ),
    },
    {
        "case_id": "rsmsext_2023159648c38a2490707f91",
        "verdict": "NOT_CONFIRMED",
        "rationale": (
            "Past source is about a workplace boss situation -- topically unrelated to the current "
            "conversation about resentment toward husband and son. The reply is entirely about the "
            "family conflict already visible in current context; nothing reflects the boss content. "
            "self-citation is a false positive, and the retrieved source itself looks topically "
            "mismatched to this state -- worth flagging as a possible candidate-retrieval quality issue, "
            "separate from the Function question."
        ),
    },
    {
        "case_id": "rsmsext_2e646da7a8b9e4649d12a759",
        "verdict": "CONFIRMED_FUNCTION",
        "rationale": (
            "Past source: the seeker had already concluded '...I probably will never know what I did "
            "wrong for things to end like that... I am not going to delve into it.' Current context alone "
            "only shows the seeker actively wondering whether she should have asked her ex more "
            "questions -- it does NOT establish that she had already arrived at self-acceptance of never "
            "knowing why. The reply's specific framing -- 'you might never fully understand why things "
            "ended the way they did... focus on what you can control... rather than trying to change the "
            "past' -- echoes that earlier resignation/acceptance in a way not deducible from the current "
            "turns alone. This is the clearest, most defensible confirmed case among the six."
        ),
    },
    {
        "case_id": "rsmsext_31689ed5523f2acf26b7824b",
        "verdict": "NOT_CONFIRMED",
        "rationale": (
            "Past source describes the parents' newly-surfaced traditional beliefs pressuring "
            "compliance. The reply only reflects what current context already states (torn between "
            "parents' plan and Matthew's family trip) and asks a generic forward question. No reference "
            "to the traditional-beliefs/pressure content. self-citation is a false positive."
        ),
    },
    {
        "case_id": "rsmsext_38496273b175872b8753e7e7",
        "verdict": "NOT_CONFIRMED",
        "rationale": (
            "Past source: 'I feel alone... no one to talk to about my emotions.' The reply suggests "
            "'talking to your friend about how you're feeling' -- a generic supportive suggestion that a "
            "weak model could produce without any knowledge of the specific isolation statement, and "
            "current context (friend already actively involved in the situation) makes this suggestion "
            "naturally reachable on its own. Too weak/ambiguous to count as confirmed; classified as not "
            "confirmed."
        ),
    },
]

# All 13 safe-nonuse rows, checked for any UNCREDITED genuine use (a false
# negative mirroring the pattern already found for RS this session). None
# were found; several of the offered past facts are themselves redundant
# with information already stated in current context, which is why IGNORE
# was the structurally correct outcome, not just a safe default.
SAFE_NONUSE_REVIEW = [
    {"case_id": "rsmsext_0322ced9a54647f005f8a865", "hidden_use": False, "note": "Reply is a plain current-turn question; no trace of the past fact (parents apologizing)."},
    {"case_id": "rsmsext_06a93f36fe6c2cf4b60eec7a", "hidden_use": False, "note": "Past fact (falling out with colleague) is already restated verbatim in current context -- correctly redundant/IGNORE, not a missed USE."},
    {"case_id": "rsmsext_087cd3c94530866ff704d0c3", "hidden_use": False, "note": "'Lisa' is already named in current context -- correctly redundant/IGNORE."},
    {"case_id": "rsmsext_150f7047d61b1dcc96cd0424", "hidden_use": False, "note": "Reply addresses the new job from current turn only; no trace of the past fact about Margaret's job."},
    {"case_id": "rsmsext_157dc5907df986cf05bd9d8f", "hidden_use": False, "note": "Past fact is already restated in current context ('focus more on my creative writing skills') -- correctly redundant/IGNORE."},
    {"case_id": "rsmsext_1738884567e5a74b7fa51061", "hidden_use": False, "note": "Same past source text as the (unconfirmed) claimed-use twin rsmsext_02f7; reply here also shows no trace of it -- consistent null result across both arms."},
    {"case_id": "rsmsext_1df969bb7fd15ffeb2eb25d8", "hidden_use": False, "note": "'sort through' phrase originates in the current turn itself, not uniquely from the past source -- correctly redundant."},
    {"case_id": "rsmsext_2bc57f0c647116ecd0a71a90", "hidden_use": False, "note": "Reply reflects the seeker's own immediately-preceding statement about talking to the supervisor, not the older January past fact."},
    {"case_id": "rsmsext_2d87e530db3f99826b1cba22", "hidden_use": False, "note": "Father's passing is already stated in current context -- correctly redundant/IGNORE."},
    {"case_id": "rsmsext_41f36f0e70e760fd6d6814b4", "hidden_use": False, "note": "No trace of the past fact; the reply's warmth/engagement here is R0-quality, not memory Function -- exactly the confound the root-repair contract identifies."},
    {"case_id": "rsmsext_ade68c4918a42c2b789883b5", "hidden_use": False, "note": "No trace of the past fact; reply is a current-turn-grounded question."},
    {"case_id": "rsmsext_c22b7205c70ce7eac4d634bc", "hidden_use": False, "note": "Reply builds only on the seeker's immediately-preceding current-turn statement, not the older past fact about Dan's work hours."},
    {"case_id": "rsmsext_d4e51f470d5a127e5e03a895", "hidden_use": False, "note": "No trace of the past fact about research interest worry."},
]


def main() -> None:
    confirmed = [r for r in CLAIMED_USE_REVIEW if r["verdict"] == "CONFIRMED_FUNCTION"]
    not_confirmed = [r for r in CLAIMED_USE_REVIEW if r["verdict"] == "NOT_CONFIRMED"]
    hidden_uses = [r for r in SAFE_NONUSE_REVIEW if r["hidden_use"]]

    report = {
        "protocol": "pm-v1.5-ms-only-claimed-use-source-review-v1",
        "status": "ZERO_API_FIRST_PARTY_REVIEW_COMPLETE",
        "method": (
            "First-party (not paid-judge) source review of all 6 MS-only rows where the generator "
            "self-cited MS=True, plus all 13 safe-nonuse rows (full census, not a matched sample), "
            "against the MS_delta USE definition: a specific past fact contributing information not "
            "recoverable from current context alone. Each verdict cites the exact textual evidence."
        ),
        "claimed_use_rows": {
            "n": len(CLAIMED_USE_REVIEW),
            "confirmed_function": len(confirmed),
            "not_confirmed": len(not_confirmed),
            "confirmed_case_ids": [r["case_id"] for r in confirmed],
            "detail": CLAIMED_USE_REVIEW,
        },
        "safe_nonuse_rows": {
            "n": len(SAFE_NONUSE_REVIEW),
            "hidden_uncredited_use_found": len(hidden_uses),
            "note": (
                "No hidden/uncredited genuine use found in any of the 13 safe-nonuse rows (unlike RS's "
                "pattern this session, where self-citation undercounted real use). Several offered past "
                "facts are themselves redundant with information already stated in current context, "
                "meaning IGNORE was the structurally correct decision, not merely a safe default."
            ),
            "detail": SAFE_NONUSE_REVIEW,
        },
        "gate_check": {
            "requirement": "development_promotion requires >= 2 independently reviewed ON cases with confirmed source-aware Function (paper1_rs_ms_r0_delta_root_repair_v1.json, stage_gates.development_promotion.required)",
            "observed": len(confirmed),
            "requirement_met": len(confirmed) >= 2,
            "consequence": (
                "NOT MET. Only 1/6 self-cited rows show independently confirmed, source-attributable "
                "Function under rigorous review; the other 5 are self-citation false positives -- the "
                "reply content is fully explainable from current context alone despite the model citing "
                "the MS evidence_id. This is a materially different, more critical finding than the "
                "'self-citation is unreliable' pattern already established for RS this session: for RS, "
                "self-citation had perfect precision (never falsely claimed) but low recall; for MS here, "
                "self-citation shows LOW PRECISION (5/6 claimed uses do not hold up under review) on this "
                "specific sample. The development_promotion Function sub-criterion is not yet satisfied by "
                "the current evidence and should not be reported as met."
            ),
        },
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
