#!/usr/bin/env python3
"""Zero-API root-cause correction: retrospectively re-score the already-collected
24 fresh-identity qualification responses against a corrected gold key.

Round 2's qualification failed its pre-registered gate. Adversarial re-reading of
all 5 mismatched items found that 4 of the 5 "hard negative/abstain" gold labels
encoded an overly strict *referential* test (same entity? still literally true?
any disambiguating question forbidden?) instead of the *functional* test that
actually matters (does using the candidate risk misattribution/invalidation, or
does it plausibly help without misleading). This script does not call any API --
it only re-applies a corrected key to data already paid for and stored, so the
retrospective evidence is falsifiable and auditable, not narrative.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_source_annotated_suitability_review import (  # noqa: E402
    MSSourceAnnotatedSuitabilityReview,
    validate_review,
)


ORIGINAL_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_private_20260812/final_control_repair_key.jsonl"
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_20260812/final_control_repair_controls_blind.jsonl"
RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_live_20260812/control_results_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_retrospective_rescore_20260812"

# item_suffix -> (new final_suitability, new decision_reason_code, new repair_family,
#                 corrected candidate_increment, allowed_response_change_type,
#                 allowed_response_change, forbidden_focus_shift, nonuse_condition, rationale)
CORRECTIONS = {
    "b1a75ec12ee7ae5857f36fba": {  # brother-vs-sister retirement stress
        "final_suitability": "SUITABLE",
        "decision_reason_code": "PAST_ONLY_UNDERSTANDING_INCREMENT",
        "repair_family": "PAST_ONLY_UNDERSTANDING_INCREMENT",
        "candidate_increment": "The user's brother was very supportive about their retirement savings plan in an earlier session -- a distinct, correctly-labeled data point about a different person, not a claim about the sister.",
        "allowed_response_change_type": "UNDERSTANDING",
        "allowed_response_change": "Acknowledge that not everyone in the user's family responds the same way, without implying the sister's criticism is therefore less valid or that the user should feel differently about it.",
        "forbidden_focus_shift": "Do not shift the reply into a discussion of the brother or use his past support to minimize, relativize, or argue away the user's current frustration with the sister.",
        "nonuse_condition": "Do not use if surfacing the contrast would read as dismissing or arguing against the user's current complaint about their sister.",
        "rationale": (
            "The original WRONG_ENTITY_OR_EVENT framing treated any cross-person reference as "
            "categorically unsuitable. Both independent reviewers correctly identified the "
            "candidate as being about a different, clearly-labeled person (no misattribution "
            "risk) and both spontaneously wrote a guard against minimizing the current "
            "complaint into their own answers -- i.e. they were already applying the real "
            "functional risk test, not failing to notice the entity difference. The real boundary "
            "is misattribution/invalidation risk, not entity identity per se."
        ),
    },
    "da5db5718f967f51c222a053": {  # biopsy relief after prior terror
        "final_suitability": "SUITABLE",
        "decision_reason_code": "PAST_ONLY_UNDERSTANDING_INCREMENT",
        "repair_family": "PAST_ONLY_UNDERSTANDING_INCREMENT",
        "candidate_increment": "The user was previously terrified about what the biopsy might show, which is not stated in the current message and contextualizes the intensity of the present relief.",
        "allowed_response_change_type": "UNDERSTANDING",
        "allowed_response_change": "Acknowledge that the relief may feel especially strong given how frightened they were before, treating the earlier fear strictly as past and already resolved.",
        "forbidden_focus_shift": "Do not revisit the earlier fear as if it might still apply, ask for details about it, or imply any ongoing medical concern.",
        "nonuse_condition": "Do not use if the user indicates they do not want to revisit the pre-result anxiety at all.",
        "rationale": (
            "The original STALE_RESOLVED_OR_CONFLICTING framing conflated two different things: "
            "(a) treating a resolved past state as if it were still true/actionable (genuinely "
            "bad), and (b) using a resolved past state only to contextualize a correctly-labeled "
            "current emotion (a common, low-risk, validating support move). This item is case "
            "(b). Both reviewers' answers explicitly kept the past framed as past."
        ),
    },
    "528b8ed5529985eb1cb14640": {  # Priya/Marcus disambiguating question
        "final_suitability": "SUITABLE",
        "decision_reason_code": "PAST_ONLY_QUESTION_INCREMENT",
        "repair_family": "PAST_ONLY_QUESTION_INCREMENT_WITH_RESOLVED_EVENT",
        "candidate_increment": "There are exactly two previously-known roommate conflicts (Priya/dishes, Marcus/groceries) that a new 'kitchen situation' could plausibly be a continuation of.",
        "allowed_response_change_type": "ONE_QUESTION",
        "allowed_response_change": "Ask specifically whether this is the same dishes-in-the-sink issue with Priya, since that is one of exactly two known candidates and naming it demonstrates real continuity rather than generic curiosity.",
        "forbidden_focus_shift": "Do not guess Marcus/groceries instead, and do not ask a fully generic question that names no candidate content ('is this related to something before?').",
        "nonuse_condition": "Do not use if there are more than a small, enumerable number of plausible candidates, or if naming a specific candidate risks being wrong in a way that would derail the conversation.",
        "rationale": (
            "Round 1 diagnosed a real defect: asking whether an *unresolved, unnamed* candidate "
            "is relevant is empty meta-clarification. Round 2's fix over-generalized that into "
            "banning every disambiguating question, including ones that name specific, "
            "already-known candidate content among a small enumerable set -- which is a "
            "legitimate, content-bearing use of memory, not meta-clarification. The boundary is "
            "content-bearing-and-bounded vs. content-free-and-open-ended, not "
            "question-vs-no-question."
        ),
    },
    "217f9d931ca53d8969b62a7a": {  # meeting agenda preference
        "final_suitability": "SUITABLE",
        "decision_reason_code": "PAST_ONLY_RESPONSE_CONSTRAINT",
        "repair_family": "PAST_ONLY_RESPONSE_CONSTRAINT",
        "candidate_increment": "The user generally prefers sending a written agenda before meetings rather than deciding the structure live -- a stable general preference not restated in the current message.",
        "allowed_response_change_type": "RESPONSE_CONSTRAINT",
        "allowed_response_change": "Suggest structuring tomorrow's meeting around a written agenda sent beforehand, consistent with the user's known preference, offered as a suggestion rather than an assumption.",
        "forbidden_focus_shift": "Do not claim this is definitely what the user wants for this specific meeting or ask about the unrelated general preference's origin.",
        "nonuse_condition": "Do not use if the user states a different preference for this specific meeting.",
        "rationale": (
            "The original MATERIAL_CHANGE_UNRESOLVED framing invented an ambiguity (does raising "
            "the habit add a new option or restate a default?) that does not correspond to real "
            "risk: applying a known stable general preference to a live, low-stakes planning "
            "decision is exactly what MP_PROFILE-style stable-fact use is supposed to do, and "
            "carries no material downside if wrong (the user can simply decline)."
        ),
    },
}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("retrospective rescore output exists; refusing overwrite")
    original_key = {row["repair_item_id"]: row for row in read_jsonl(ORIGINAL_KEY)}
    controls = {row["repair_item_id"]: row for row in read_jsonl(CONTROLS)}
    results = read_jsonl(RESULTS)

    corrected_key: dict[str, dict] = {}
    for suffix, key_row in original_key.items():
        pass
    corrected_rows = []
    for repair_item_id, row in original_key.items():
        suffix = repair_item_id.removeprefix("msrepaircontrol_")
        new_row = dict(row)
        if suffix in CORRECTIONS:
            fix = CORRECTIONS[suffix]
            # Self-validate the corrected gold through the real production contract,
            # exactly like the original materialization did -- a corrected label is
            # not accepted unless it is itself internally consistent.
            gold_review = {
                "repair_item_id": repair_item_id,
                "current_goal_span_ids": ["V001"],
                "past_source_span_ids": ["C001"],
                "current_support_goal": controls[repair_item_id]["visible_current_spans"][0]["content"],
                "entity_link": "RESOLVED",
                "candidate_increment": fix["candidate_increment"],
                "allowed_response_change_type": fix["allowed_response_change_type"],
                "allowed_response_change": fix["allowed_response_change"],
                "forbidden_focus_shift": fix["forbidden_focus_shift"],
                "nonuse_condition": fix["nonuse_condition"],
                "final_suitability": fix["final_suitability"],
                "decision_reason_code": fix["decision_reason_code"],
            }
            parsed = MSSourceAnnotatedSuitabilityReview(**gold_review)
            validated = validate_review(parsed, controls[repair_item_id])
            new_row.update({
                "expected_final_suitability": validated["final_suitability"],
                "expected_decision_reason_code": validated["decision_reason_code"],
                "repair_family": fix["repair_family"],
                "candidate_increment": validated["candidate_increment"],
                "allowed_response_change": validated["allowed_response_change"],
                "forbidden_focus_shift": validated["forbidden_focus_shift"],
                "nonuse_condition": validated["nonuse_condition"],
                "correction_rationale": fix["rationale"],
                "superseded_original_expected_final_suitability": row["expected_final_suitability"],
                "corrected": True,
            })
        else:
            new_row["corrected"] = False
        corrected_rows.append(new_row)
    corrected_rows.sort(key=lambda r: r["repair_item_id"])
    new_distribution = Counter(row["expected_final_suitability"] for row in corrected_rows)

    by_reviewer: dict[str, dict] = {}
    for reviewer in sorted({row["reviewer_id"] for row in results}):
        rows = [row for row in results if row["reviewer_id"] == reviewer]
        old_exact = 0
        new_exact = 0
        scored = 0
        transport_failures = 0
        flips = []
        for row in rows:
            gold_row = next(r for r in corrected_rows if r["repair_item_id"] == row["repair_item_id"])
            old_gold = original_key[row["repair_item_id"]]["expected_final_suitability"]
            new_gold = gold_row["expected_final_suitability"]
            if not row["schema_valid_and_locally_validated"]:
                transport_failures += 1
                continue
            observed = row["validated_review"]["final_suitability"]
            scored += 1
            was_correct = observed == old_gold
            now_correct = observed == new_gold
            old_exact += was_correct
            new_exact += now_correct
            if was_correct != now_correct:
                flips.append({
                    "repair_item_id": row["repair_item_id"],
                    "observed": observed,
                    "old_gold": old_gold,
                    "new_gold": new_gold,
                    "was_correct": was_correct,
                    "now_correct": now_correct,
                })
        by_reviewer[reviewer] = {
            "scored": scored,
            "transport_failures": transport_failures,
            "old_exact": old_exact,
            "new_exact": new_exact,
            "old_exact_rate": round(old_exact / scored, 4) if scored else None,
            "new_exact_rate": round(new_exact / scored, 4) if scored else None,
            "flips": flips,
        }

    report = {
        "protocol": "pm-v1.5-paper1-ms-final-control-repair-retrospective-rescore-v1",
        "status": "ZERO_API_RETROSPECTIVE_RESCORE_COMPLETE",
        "claim_boundary": (
            "This re-applies a corrected gold key to the exact same 24 already-collected "
            "responses; it spends nothing and calls no API. It is evidence the round-2 failure "
            "was substantially construct-driven, not proof the corrected construct itself is "
            "fully validated -- the corrected 12-item set is no longer balanced (see "
            "corrected_distribution) and must not be re-reported as a formal qualification pass."
        ),
        "corrected_distribution": dict(new_distribution),
        "distribution_warning": (
            "Original was 5 SUITABLE / 5 NOT_SUITABLE / 2 SEMANTIC_ABSTAIN. After correction it "
            "is heavily SUITABLE-skewed and has zero SEMANTIC_ABSTAIN exemplars left -- this set "
            "can no longer serve as a balanced qualification gate on its own."
        ),
        "corrections_applied": {
            suffix: {"rationale": fix["rationale"], "new_final_suitability": fix["final_suitability"]}
            for suffix, fix in CORRECTIONS.items()
        },
        "by_reviewer": by_reviewer,
        "recommendation": (
            "Do not declare round 2 retroactively PASS on this specific unbalanced set. Instead: "
            "(1) rewrite the review rubric with the corrected functional-risk criteria now that "
            "they are concretely identified; (2) author a small, fresh, genuinely balanced anchor "
            "set that actually instantiates real misattribution/invalidation risk for the negative "
            "and abstain families (this round's items for those families did not); (3) decide "
            "whether one more small zero-cost self-check is worth it before committing to the "
            "much larger paid 201-item x 2-reviewer formal labeling pass."
        ),
        "api_calls": 0,
        "source_hashes": {
            "original_key": sha256_file(ORIGINAL_KEY),
            "controls": sha256_file(CONTROLS),
            "results": sha256_file(RESULTS),
        },
    }
    OUT.mkdir(parents=True)
    write_jsonl(OUT / "corrected_key.jsonl", corrected_rows)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
