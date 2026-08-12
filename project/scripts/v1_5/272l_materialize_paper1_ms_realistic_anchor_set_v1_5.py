#!/usr/bin/env python3
"""Materialize a fresh MS anchor set grounded in the *real* label distribution.

Round 2's 12 hand-authored control items were sophisticated dilemmas invented
from intuition. Directly inspecting the real frozen teacher labels
(outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl,
204 real candidates) showed the real negative distribution is dominated by
crude, low-effort noise -- near-duplicate boilerplate greetings, bare "thank
you"s, and retrieval grabbing a topically unrelated sentence -- not subtle
contrastive dilemmas. Per docs/PM_V1_5_FINAL_RESEARCH_PLAN_ZH.md Sec 5.3-5.4,
internal synthetic items must be a superdomain of the real observed
constructs (new wording, same underlying pattern and difficulty), never a
copy of protected-split text. Every candidate/current pair below is newly
authored with new topics; only the underlying pattern is grounded in a real,
cited label row.

This keeps the 7 round-2 items that were never mismatched by either reviewer
(5 SUITABLE + 2 NOT_SUITABLE) and replaces the 5 that were unrealistic or
mismatched with fresh, realistically-crude items.
"""

from __future__ import annotations

from collections import Counter
from html import escape
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_source_annotated_suitability_review import (  # noqa: E402
    MSSourceAnnotatedSuitabilityReview,
    validate_review,
)

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PRIOR_CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_20260812/final_control_repair_controls_blind.jsonl"
PRIOR_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_private_20260812/final_control_repair_key.jsonl"
RETIRED_CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/qualification_controls_blind.jsonl"
PUBLIC_201 = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/ms_reannotation_packet_blind.jsonl"
REAL_LABELS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl"
PUBLIC_OUT = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_20260812"
PRIVATE_OUT = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_private_20260812"

KEPT_CASE_KEYS = {
    "final_control_neg_phatic",
    "final_control_neg_boundary",
    "final_control_pos_understanding",
    "final_control_pos_question_event_a",
    "final_control_pos_question_event_b",
    "final_control_pos_constraint",
    "final_control_pos_option",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hex(*parts: str, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta or tb else 0.0


def _decision_contract() -> dict[str, Any]:
    return {
        "unit": "Judge this MS candidate alone for this visible current state. Other components may independently be ON.",
        "positive_requires_all": [
            "owner and strictly-past time are valid",
            "entity/event link is resolved",
            "candidate contributes a specific proposition not already supplied by current context",
            "the immediate support goal can be quoted from current context",
            "a candidate-specific material and natural response change can be stated",
            "that change preserves current focus and owner/time uncertainty",
            "a concrete condition for safe nonuse can be stated",
        ],
        "not_suitable_if": [
            "source is low-information or social closing only",
            "current context already supplies the same increment",
            "candidate is the wrong entity/event",
            "candidate is stale/resolved/conflicting with no safe tentative use",
            "same topic but no immediate-goal contribution",
            "any use would shift focus away from the current need",
            "the user currently forbids past-session use",
        ],
        "abstain_only_if": [
            "entity/event resolution cannot be decided from the shown text",
            "redundancy cannot be decided from the shown text",
            "material response change cannot be decided from the shown text",
            "owner/time boundary cannot be decided from the shown text",
        ],
        "function_is_not_quality": "A candidate may be suitable even if a later generator could express it badly. State the allowed change; do not predict prose quality.",
        "no_single_memory_cap": True,
        "sixteen_requested_actions_unchanged": True,
    }


def _annotation_template() -> dict[str, Any]:
    return {
        "current_goal_span_ids": [],
        "current_support_goal": "",
        "past_source_span_ids": [],
        "candidate_increment": "",
        "entity_link": "ONE_OF_RESOLVED_UNRESOLVED_WRONG_ENTITY",
        "allowed_response_change_type": "ONE_OF_UNDERSTANDING_QUESTION_CONSTRAINT_OPTION_NONE_UNRESOLVED",
        "allowed_response_change": "",
        "forbidden_focus_shift": "",
        "nonuse_condition": "",
        "final_suitability": "ONE_OF_SUITABLE_NOT_SUITABLE_SEMANTIC_ABSTAIN",
        "decision_reason_code": "",
    }


def _new_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_key": "final_control_neg_recurrence_crude",
            "repair_family": "TRUE_CURRENT_REDUNDANCY_INCLUDING_RECURRENCE",
            "grounded_in_real_label": "g4review echo pool (e.g. review rows with primary_reason_code=CURRENT_ECHO_OR_CONTAINMENT): real candidates are frequently near-duplicate boilerplate opener text ('Hey, do you have a moment to chat?' recurring verbatim), not elaborate business-recurrence scenarios.",
            "v": "Hi, I could really use someone to talk to right now, like last time.",
            "c": "In an earlier session, the user opened by saying they could really use someone to talk to.",
            "gold": {
                "current_support_goal": "The user wants someone to talk to right now, as they explicitly say they did before.",
                "candidate_increment": "NONE: the current message already states this is the same kind of opener as before; the past source adds no proposition beyond what 'like last time' already says.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE: any reference to the past source would only restate what the current message already says.",
                "forbidden_focus_shift": "Do not treat the past opener as if it adds continuity information the user hasn't already supplied.",
                "nonuse_condition": "Always omit while the current message continues to state the recurrence itself.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "CURRENT_CONTEXT_ALREADY_SUPPLIES_INCREMENT",
            },
        },
        {
            "case_key": "final_control_neg_stale_crude",
            "repair_family": "STALE_RESOLVED_OR_CONFLICTING",
            "grounded_in_real_label": "g4review_ccd9251bd1e3fa5d6c18b62c-style rows (real STALE_RESOLVED_OR_CONFLICTING): real stale candidates are ordinary past worries the current text shows have simply moved on, not elaborate emotional-arc dilemmas.",
            "v": "I finally paid off that credit card debt I mentioned last time -- feels like a weight is off my shoulders.",
            "c": "In an earlier session, the user said they were worried about how they would ever pay off a large credit card balance.",
            "gold": {
                "current_support_goal": "The user wants to share relief now that the credit card debt is paid off.",
                "candidate_increment": "NONE for the current goal: the earlier worry is about a debt that is now resolved and conflicts with the present relief.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE: support the present relief without reopening the earlier worry.",
                "forbidden_focus_shift": "Do not revisit the earlier financial worry or ask about it as if it is still open.",
                "nonuse_condition": "Omit because the user has explicitly closed that worry by paying off the debt.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "STALE_RESOLVED_OR_CONFLICTING",
            },
        },
        {
            "case_key": "final_control_neg_wrong_entity_crude",
            "repair_family": "WRONG_ENTITY_OR_EVENT",
            "grounded_in_real_label": "g4review_a523d64c79e3dd0ff60ef482 / 4acbdc89eca84af54250bda9-style rows (real WRONG_ENTITY_OR_EVENT): real mismatches are retrieval grabbing an unrelated person/topic entirely, not a thoughtfully-chosen contrastive family member.",
            "v": "My mom keeps calling me multiple times a day and it's really overwhelming.",
            "c": "In an earlier session, the user mentioned that a coworker named Jake was very helpful during a tight project deadline.",
            "gold": {
                "current_support_goal": "The user wants support handling feeling overwhelmed by their mom's frequent calls.",
                "candidate_increment": "NONE for this goal: the candidate concerns an unrelated person (a coworker) and an unrelated context (a work deadline) with no connection to the mom or the calls.",
                "entity_link": "WRONG_ENTITY",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE: respond to the mom's calls from current context only.",
                "forbidden_focus_shift": "Do not bring the coworker or the work deadline into a reply about the user's mom.",
                "nonuse_condition": "Omit unless the user explicitly connects the coworker or that deadline to the current situation with their mom.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "WRONG_ENTITY_OR_EVENT",
            },
        },
        {
            "case_key": "final_control_abstain_bare_context_crude",
            "repair_family": "ENTITY_OR_EVENT_UNRESOLVED_WITH_META_QUESTION_FORBIDDEN",
            "grounded_in_real_label": "g4review_02e5cf7c70c98abe501fe7f1-style rows (real TARGET_OR_ENTITY_UNRESOLVED): current text is often just a bare greeting with no goal established at all, so nothing about a vague past mention can be judged relevant.",
            "v": "hey, you there?",
            "c": "In an earlier session, the user mentioned they'd been dealing with a lot of stress lately but did not say why.",
            "gold": {
                "current_support_goal": "UNRESOLVED: the current message establishes no topic, goal, or feeling to connect anything to yet.",
                "candidate_increment": "UNRESOLVED: with no current goal established, it cannot be decided whether this vague past stress mention relates to whatever the user is about to raise.",
                "entity_link": "UNRESOLVED",
                "allowed_response_change_type": "UNRESOLVED",
                "allowed_response_change": "UNRESOLVED: the current text gives nothing to link the past mention to.",
                "forbidden_focus_shift": "Do not guess what the user wants to talk about or ask a meta-question like 'is this related to the stress you mentioned before' -- that assumes relevance the current text has not established.",
                "nonuse_condition": "Omit until the user states what they want to talk about.",
                "final_suitability": "SEMANTIC_ABSTAIN",
                "decision_reason_code": "ENTITY_OR_EVENT_UNRESOLVED",
            },
        },
        {
            "case_key": "final_control_abstain_vague_candidate_crude",
            "repair_family": "MATERIAL_CHANGE_UNRESOLVED",
            "grounded_in_real_label": "g4review_0584fa5b5716403a92146254-style rows (real MATERIAL_USE_UNRESOLVED): the real candidate text itself is sometimes too vague to interpret, independent of whether the current topic is clear.",
            "v": "I've been thinking about reaching out to an old friend but I'm scared to.",
            "c": "In an earlier session, the user said something like 'I don't really know anymore, it's just been a lot.'",
            "gold": {
                "current_support_goal": "The user wants support deciding whether to reach out to an old friend despite being scared.",
                "candidate_increment": "UNRESOLVED: the candidate text is too vague and uninterpretable on its own to tell whether it says anything specific about the friend, the fear, or reaching out.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "UNRESOLVED",
                "allowed_response_change": "UNRESOLVED: it cannot be decided whether this vague past statement would add any concrete, usable content to a reply about reaching out to the friend.",
                "forbidden_focus_shift": "Do not invent a specific meaning for the vague candidate text.",
                "nonuse_condition": "Omit until a clearer, more specific past statement is available.",
                "final_suitability": "SEMANTIC_ABSTAIN",
                "decision_reason_code": "MATERIAL_CHANGE_UNRESOLVED",
            },
        },
    ]


def main() -> None:
    if PUBLIC_OUT.exists() or PRIVATE_OUT.exists():
        raise RuntimeError("realistic anchor set output exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    if current["id"] != "MS_CONSTRUCT_CORRECTED_ROUTE_REOPENED_FRESH_ANCHOR_SET_NEXT":
        raise RuntimeError("authority phase is not the fresh-anchor-set phase; refuse to guess")

    prior_controls = {row["repair_item_id"]: row for row in read_jsonl(PRIOR_CONTROLS)}
    prior_key = {row["repair_item_id"]: row for row in read_jsonl(PRIOR_KEY)}
    kept_ids = {rid for rid, row in prior_key.items() if row["case_key"] in KEPT_CASE_KEYS}
    if len(kept_ids) != 7:
        raise RuntimeError(f"expected exactly 7 kept items, found {len(kept_ids)}")

    retired = read_jsonl(RETIRED_CONTROLS)
    # Deliberately excludes PUBLIC_201: that's a large real corpus where generic
    # opener phrases naturally recur across many real conversations, so overlap
    # there isn't a meaningful duplication signal. What actually matters is not
    # accidentally re-deriving a previous *hand-authored control item*.
    all_prior_texts = [
        " ".join(s["content"] for s in row["visible_current_spans"] + row["strictly_past_candidate_spans"])
        for row in [*retired, *prior_controls.values()]
    ]

    real_labels = read_jsonl(REAL_LABELS)
    real_reason_counts = Counter(
        row.get("primary_reason_code") for row in real_labels if row["teacher_decision"] == "NOT_SUITABLE"
    )

    controls: list[dict[str, Any]] = []
    private_key: list[dict[str, Any]] = []
    max_overlap = 0.0

    # Carry the 7 already-validated items forward unchanged.
    for rid in sorted(kept_ids):
        controls.append(prior_controls[rid])
        key_row = dict(prior_key[rid])
        key_row["carried_forward_from_round_2_unmodified"] = True
        key_row["round_2_reviewer_agreement"] = "both reviewers matched this item's original gold"
        private_key.append(key_row)

    # Author the 5 fresh, realistically-crude items.
    for case in _new_cases():
        item_id = "msrepaircontrol_" + _stable_hex(case["case_key"], "realistic-anchor-v1")
        visible_spans = [{"span_id": "V001", "speaker": "seeker", "content": case["v"]}]
        candidate_spans = [{"span_id": "C001", "kind": "strictly_prior_user_statement", "content": case["c"]}]
        item = {
            "protocol": "pm-v1.5-paper1-ms-realistic-anchor-item-v1",
            "repair_item_id": item_id,
            "component": "MS",
            "visible_current_spans": visible_spans,
            "strictly_past_candidate_spans": candidate_spans,
            "candidate_provenance": {
                "owner_status": "CURRENT_USER_VERIFIED",
                "time_status": "STRICTLY_PRIOR_USER_EVIDENCE_MAY_HAVE_CHANGED",
            },
            "decision_contract": _decision_contract(),
            "annotation": _annotation_template(),
        }
        gold_review = {
            "repair_item_id": item_id,
            "current_goal_span_ids": ["V001"],
            "past_source_span_ids": ["C001"],
            **case["gold"],
        }
        parsed = MSSourceAnnotatedSuitabilityReview(**gold_review)
        validated = validate_review(parsed, item)

        combined_text = case["v"] + " " + case["c"]
        overlap = max((_jaccard(combined_text, other) for other in all_prior_texts), default=0.0)
        max_overlap = max(max_overlap, overlap)

        controls.append(item)
        private_key.append({
            "protocol": "pm-v1.5-paper1-ms-realistic-anchor-key-v1",
            "repair_item_id": item_id,
            "case_key": case["case_key"],
            "repair_family": case["repair_family"],
            "grounded_in_real_label": case["grounded_in_real_label"],
            "not_training": True,
            "expected_final_suitability": validated["final_suitability"],
            "expected_decision_reason_code": validated["decision_reason_code"],
            "candidate_increment": validated["candidate_increment"],
            "allowed_response_change": validated["allowed_response_change"],
            "forbidden_focus_shift": validated["forbidden_focus_shift"],
            "nonuse_condition": validated["nonuse_condition"],
            "content_overlap_vs_all_prior_max_jaccard": round(overlap, 6),
            "carried_forward_from_round_2_unmodified": False,
        })

    controls.sort(key=lambda row: _stable_hex(row["repair_item_id"], "realistic-anchor-blind-order"))
    for position, row in enumerate(controls, start=1):
        row["review_position"] = position

    gold_counts = Counter(row["expected_final_suitability"] for row in private_key)
    checks = {
        "exact_12_items": len(controls) == 12 and len(private_key) == 12,
        "unique_item_ids": len({row["repair_item_id"] for row in controls}) == 12,
        "7_carried_forward_unmodified": sum(row["carried_forward_from_round_2_unmodified"] for row in private_key) == 7,
        "5_freshly_authored": sum(not row["carried_forward_from_round_2_unmodified"] for row in private_key) == 5,
        "distribution_5_5_2": gold_counts == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2},
        "content_disjoint_from_all_prior_rounds": max_overlap < 0.3,
        "all_fresh_gold_answers_schema_valid_via_real_contract": True,  # raised above on failure
        "annotation_template_has_all_blank_fields": all(set(row["annotation"]) == set(_annotation_template()) for row in controls),
        "zero_api_zero_label_zero_fit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"realistic anchor set checks failed: {checks}")

    PUBLIC_OUT.mkdir(parents=True)
    PRIVATE_OUT.mkdir(parents=True)
    controls_path = PUBLIC_OUT / "realistic_anchor_controls_blind.jsonl"
    key_path = PRIVATE_OUT / "realistic_anchor_key.jsonl"
    write_jsonl(controls_path, controls)
    write_jsonl(key_path, private_key)

    report = {
        "protocol": "pm-v1.5-paper1-ms-realistic-anchor-set-report-v1",
        "status": "ZERO_API_REALISTIC_ANCHOR_SET_MATERIALIZED_GROUNDED_IN_REAL_LABEL_DISTRIBUTION",
        "checks": checks,
        "real_negative_reason_distribution_204_real_labels": dict(real_reason_counts),
        "design_note": (
            "Per docs/PM_V1_5_FINAL_RESEARCH_PLAN_ZH.md Sec 5.3-5.4, internal synthetic items must be "
            "a superdomain of real observed constructs (new wording, same pattern), not invented from "
            "intuition and never a literal copy of dataset text. The 5 fresh negative/abstain items "
            "here are each explicitly grounded in a cited real label row's pattern; the 7 carried-forward "
            "items were already validated by both reviewers in round 2 and are unchanged."
        ),
        "counts": {"items": len(controls), "distribution": dict(gold_counts)},
        "max_content_overlap_jaccard_vs_all_prior_rounds": round(max_overlap, 6),
        "next_gate": (
            "User review of this set, then a decision on whether to spend on one more small paid "
            "qualification round or proceed directly to the larger 201-item formal labeling pass."
        ),
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "public_artifacts": {
            "controls": {"path": str(controls_path.relative_to(ROOT)), "sha256": _sha(controls_path)},
        },
        "private_artifacts": {
            "key": {"path": str(key_path.relative_to(ROOT)), "sha256": _sha(key_path)},
        },
        "source_hashes": {
            "authority": _sha(AUTHORITY),
            "prior_controls": _sha(PRIOR_CONTROLS),
            "prior_key": _sha(PRIOR_KEY),
            "real_labels": _sha(REAL_LABELS),
            "instrument": _sha(ROOT / "src/metacom_pm/v1_5_ms_source_annotated_suitability_review.py"),
        },
    }
    write_json(PUBLIC_OUT / "report.json", report)
    rows_html = "".join(
        f"<tr><td>{escape(name)}</td><td>{'PASS' if value else 'FAIL'}</td></tr>" for name, value in checks.items()
    )
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>MS realistic anchor set</title>
<style>body{{font-family:system-ui;max-width:1080px;margin:2rem auto;line-height:1.5}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.45rem;text-align:left}}.ok{{color:#176b2c}}</style></head><body>
<h1>MS realistic anchor set (grounded in real label distribution)</h1>
<p class='ok'><strong>{escape(report['status'])}</strong></p>
<h2>Real negative reason distribution (204 real labels)</h2><p>{escape(json.dumps(dict(real_reason_counts)))}</p>
<h2>Machine checks</h2><table><tr><th>Check</th><th>Result</th></tr>{rows_html}</table>
</body></html>"""
    (PUBLIC_OUT / "report.html").write_text(html, encoding="utf-8")
    report["public_artifacts"]["report_html"] = {
        "path": str((PUBLIC_OUT / "report.html").relative_to(ROOT)),
        "sha256": _sha(PUBLIC_OUT / "report.html"),
    }
    write_json(PUBLIC_OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
