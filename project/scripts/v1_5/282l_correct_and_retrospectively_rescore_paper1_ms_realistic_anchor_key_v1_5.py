#!/usr/bin/env python3
"""Zero-API root-cause correction: fix a confirmed gold-key bug in the realistic
anchor set and retrospectively re-score every already-collected real response
against the corrected key.

`msrepaircontrol_5ff308bb11f16ae336b63a1d` (a user sharing relief that a credit
card debt is finally paid off, candidate = an earlier session's worry about
that same debt) was gold-labeled NOT_SUITABLE / STALE_RESOLVED_OR_CONFLICTING.
Round 3's ledger entry (V15-MEAS-91) already diagnosed this as structurally
identical to the already-corrected "biopsy relief" item (using a resolved past
worry only to contextualize a correctly-labeled present emotion -- a low-risk,
validating support move, not stale/conflicting reuse) and claimed the fix was
applied. It was not: the on-disk key
(outputs/pm_v1_5_paper1_ms_realistic_anchor_set_private_20260812/realistic_anchor_key.jsonl)
still held NOT_SUITABLE when checked during the round-5 accountability review,
and every independent reviewer judgment ever collected on this item --
GPT-5.6 (round 3), Gemini no-thinking (round 3), Gemini thinking_budget=2048
(round 4), and Claude Haiku 4.5 (round 5), four judgments across three model
families -- said SUITABLE. Unanimous disagreement across independent model
families is the same "convergence argues against pure incapacity" signal the
user originally invoked to reopen MS; this is a confirmed gold-authoring bug
I diagnosed but never actually applied, not a model or construct failure.

This script applies the correction to the actual key file and re-scores the
three already-collected, already-paid-for result sets (rounds 3/4/5) against
it. No new API calls, no new labels, no new fits.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_source_annotated_suitability_review import (  # noqa: E402
    MSSourceAnnotatedSuitabilityReview,
    validate_review,
)


KEY = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_private_20260812/realistic_anchor_key.jsonl"
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_20260812/realistic_anchor_controls_blind.jsonl"
ROUND3_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_live_20260812/control_results_private.jsonl"
ROUND4_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_gemini_thinking_probe_live_20260812/control_results_private.jsonl"
ROUND5_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_claude_haiku_challenger_probe_live_20260812/control_results_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_key_correction_20260812"

TARGET_ITEM = "msrepaircontrol_5ff308bb11f16ae336b63a1d"

CORRECTION = {
    "current_support_goal": "The user wants to share relief now that the credit card debt is paid off.",
    "candidate_increment": "The user was previously worried about being able to pay off this exact credit card debt, which is not restated in the current message and contextualizes the intensity of the present relief.",
    "entity_link": "RESOLVED",
    "allowed_response_change_type": "UNDERSTANDING",
    "allowed_response_change": "Acknowledge that the relief may feel especially significant given how worried they were before, treating the earlier worry strictly as past and already resolved.",
    "forbidden_focus_shift": "Do not revisit the earlier worry as if it might still apply, ask for financial details, or imply the debt could return.",
    "nonuse_condition": "Do not use if the user indicates they don't want to revisit the earlier worry at all.",
    "final_suitability": "SUITABLE",
    "decision_reason_code": "PAST_ONLY_UNDERSTANDING_INCREMENT",
}
CORRECTED_FAMILY = "PAST_ONLY_UNDERSTANDING_INCREMENT"
RATIONALE = (
    "Structurally identical to the already-corrected 'biopsy relief' item: a resolved past "
    "worry used only to contextualize a correctly-labeled present emotion, with the past kept "
    "strictly past. The original STALE_RESOLVED_OR_CONFLICTING label conflated 'treating a "
    "resolved past state as still true/actionable' (genuinely bad) with 'using a resolved past "
    "state only to contextualize a correctly-labeled current emotion' (this item, low-risk). "
    "4/4 independent reviewer judgments across 3 model families (GPT-5.6, Gemini no-thinking, "
    "Gemini thinking, Claude Haiku 4.5) unanimously disagreed with the original gold."
)


def _rescore(results_path: Path, key: dict[str, Any]) -> dict[str, Any]:
    rows = read_jsonl(results_path)
    by_reviewer: dict[str, dict[str, Any]] = {}
    for row in rows:
        reviewer = row["reviewer_id"]
        stats = by_reviewer.setdefault(reviewer, {"n": 0, "exact": 0, "old_target_correct": None, "new_target_correct": None})
        gold = key.get(row["repair_item_id"])
        if gold is None or not row["schema_valid_and_locally_validated"]:
            continue
        observed = (row.get("validated_review") or {}).get("final_suitability")
        stats["n"] += 1
        if observed == gold["expected_final_suitability"]:
            stats["exact"] += 1
        if row["repair_item_id"] == TARGET_ITEM:
            stats["new_target_correct"] = observed == gold["expected_final_suitability"]
    return by_reviewer


def main() -> None:
    if OUT.exists():
        raise RuntimeError("correction output exists; refusing overwrite")
    key_rows = read_jsonl(KEY)
    controls = {row["repair_item_id"]: row for row in read_jsonl(CONTROLS)}
    target_control = controls[TARGET_ITEM]

    old_row = next(row for row in key_rows if row["repair_item_id"] == TARGET_ITEM)
    if old_row["expected_final_suitability"] != "NOT_SUITABLE":
        raise RuntimeError("target item is not in the expected pre-correction state; refusing to guess")

    gold_review = {
        "repair_item_id": TARGET_ITEM,
        "current_goal_span_ids": ["V001"],
        "past_source_span_ids": ["C001"],
        **CORRECTION,
    }
    parsed = MSSourceAnnotatedSuitabilityReview(**gold_review)
    validated = validate_review(parsed, target_control)
    if validated is None:
        raise RuntimeError("corrected gold failed local validation against the control item")

    new_key_rows = []
    for row in key_rows:
        if row["repair_item_id"] != TARGET_ITEM:
            new_key_rows.append(row)
            continue
        new_row = dict(row)
        new_row["repair_family"] = CORRECTED_FAMILY
        new_row["expected_final_suitability"] = CORRECTION["final_suitability"]
        new_row["expected_decision_reason_code"] = CORRECTION["decision_reason_code"]
        new_row["candidate_increment"] = CORRECTION["candidate_increment"]
        new_row["allowed_response_change"] = CORRECTION["allowed_response_change"]
        new_row["forbidden_focus_shift"] = CORRECTION["forbidden_focus_shift"]
        new_row["nonuse_condition"] = CORRECTION["nonuse_condition"]
        new_row["corrected_after_round5_accountability_review"] = True
        new_row["correction_rationale"] = RATIONALE
        new_row["pre_correction_gold"] = {
            "expected_final_suitability": old_row["expected_final_suitability"],
            "expected_decision_reason_code": old_row["expected_decision_reason_code"],
            "repair_family": old_row["repair_family"],
        }
        new_key_rows.append(new_row)

    old_key = {row["repair_item_id"]: row for row in key_rows}
    new_key = {row["repair_item_id"]: row for row in new_key_rows}

    before = {
        "round3": _rescore(ROUND3_RESULTS, old_key),
        "round4": _rescore(ROUND4_RESULTS, old_key),
        "round5": _rescore(ROUND5_RESULTS, old_key),
    }
    after = {
        "round3": _rescore(ROUND3_RESULTS, new_key),
        "round4": _rescore(ROUND4_RESULTS, new_key),
        "round5": _rescore(ROUND5_RESULTS, new_key),
    }

    write_jsonl(KEY, new_key_rows)

    OUT.mkdir(parents=True)
    report = {
        "protocol": "pm-v1.5-paper1-ms-realistic-anchor-key-correction-v1",
        "status": "GOLD_KEY_BUG_CONFIRMED_AND_CORRECTED_ZERO_API_RESCORE_COMPLETE",
        "target_item": TARGET_ITEM,
        "correction": CORRECTION,
        "rationale": RATIONALE,
        "before_correction": before,
        "after_correction": after,
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "source_hashes": {
            "corrected_key": sha256_file(KEY),
            "controls": sha256_file(CONTROLS),
            "round3_results": sha256_file(ROUND3_RESULTS),
            "round4_results": sha256_file(ROUND4_RESULTS),
            "round5_results": sha256_file(ROUND5_RESULTS),
        },
    }
    write_json(OUT / "report.json", report)
    import json
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
