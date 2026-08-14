#!/usr/bin/env python3
"""Materialize the one authorized fresh 12-item MS control-construct repair batch.

Zero API, zero training labels, zero fits. This is the "fresh control
materialization" step named as next_scientific_action in
paper1_active_execution_bundle_v1.json's current_phase, gated by
paper1_ms_final_control_construct_repair_design_v1.json. Content is
hand-authored to satisfy that design's three construct repairs and is
disjoint from the retired 12-item control set and the public 201-item
reannotation packet (checked below, not just asserted).
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

from metacom_pm.v1_5_ms_source_annotated_suitability_review import (  # noqa: E402
    MSSourceAnnotatedSuitabilityReview,
    validate_review,
)

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_ms_final_control_construct_repair_design_v1.json"
RETIRED_CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/qualification_controls_blind.jsonl"
PUBLIC_201 = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/ms_reannotation_packet_blind.jsonl"
PUBLIC_OUT = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_20260812"
PRIVATE_OUT = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_private_20260812"

EXPECTED_DESIGN_SHA256 = "52e1b498c2d7cd7ed790e8212817464de238279d65b423f748adf5113ba8615a"

REQUIRED_NEGATIVE_FAMILIES = [
    "LOW_INFORMATION_OR_PHATIC",
    "TRUE_CURRENT_REDUNDANCY_INCLUDING_RECURRENCE",
    "WRONG_ENTITY_OR_EVENT",
    "STALE_RESOLVED_OR_CONFLICTING",
    "CURRENT_BOUNDARY_FORBIDS_HISTORY",
]
REQUIRED_POSITIVE_FAMILIES = [
    "PAST_ONLY_UNDERSTANDING_INCREMENT",
    "PAST_ONLY_QUESTION_INCREMENT_WITH_RESOLVED_EVENT",
    "PAST_ONLY_RESPONSE_CONSTRAINT",
    "PAST_ONLY_DECLINABLE_OPTION",
]
REQUIRED_ABSTAIN_FAMILIES = [
    "ENTITY_OR_EVENT_UNRESOLVED_WITH_META_QUESTION_FORBIDDEN",
    "MATERIAL_CHANGE_UNRESOLVED",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


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


def _cases() -> list[dict[str, Any]]:
    return [
        {
            "case_key": "final_control_neg_phatic",
            "repair_family": "LOW_INFORMATION_OR_PHATIC",
            "v": "I think I'm ready to start looking for a new apartment closer to the studio.",
            "c": "Thanks so much, that really helped.",
            "gold": {
                "current_support_goal": "The user wants to start the practical process of looking for a new apartment closer to the studio.",
                "candidate_increment": "NONE: the source is only social gratitude and contains no proposition about apartments, the studio, or moving.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE: it cannot materially change the present support response.",
                "forbidden_focus_shift": "Do not mention or paraphrase the prior thanks to prove memory use.",
                "nonuse_condition": "Always omit this source for the shown goal; it never becomes usable.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "LOW_INFORMATION_OR_PHATIC",
            },
        },
        {
            "case_key": "final_control_neg_recurrence_echo",
            "repair_family": "TRUE_CURRENT_REDUNDANCY_INCLUDING_RECURRENCE",
            "v": "My co-founder cancelled our planning call again today — that's the third time this month he's bailed at the last minute.",
            "c": "In an earlier session, the user said their co-founder had cancelled a planning call at the last minute before, and that it had already happened more than once that month.",
            "gold": {
                "current_support_goal": "The user wants support processing frustration about their co-founder repeatedly cancelling planning calls at the last minute this month.",
                "candidate_increment": "NONE: the current message already states both that this happened before and that it is the third time this month, so the past source adds no proposition the current text does not already supply.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE: any reference to the past source would only restate what the current message already says.",
                "forbidden_focus_shift": "Do not cite the past session as if it adds new evidence of a pattern the user has not already named themselves.",
                "nonuse_condition": "Always omit while the current message continues to state the recurrence itself.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "CURRENT_CONTEXT_ALREADY_SUPPLIES_INCREMENT",
            },
            "repair_marker": {"recurrence_in_current_text": ["third time this month", "again"]},
        },
        {
            "case_key": "final_control_neg_wrong_entity",
            "repair_family": "WRONG_ENTITY_OR_EVENT",
            "v": "My sister keeps telling me I'm not saving enough for retirement and it's stressing me out.",
            "c": "In an earlier session, the user said their brother had been very supportive about their retirement savings plan.",
            "gold": {
                "current_support_goal": "The user wants support handling stress caused by their sister's comments about their retirement savings.",
                "candidate_increment": "NONE for this goal: the candidate concerns a different person (brother, supportive) than the one causing the current stress (sister, critical).",
                "entity_link": "WRONG_ENTITY",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE: respond to the sister's comments from current context only.",
                "forbidden_focus_shift": "Do not credit the brother's supportiveness in a reply about the sister, and do not imply the family is uniformly supportive.",
                "nonuse_condition": "Omit unless the user explicitly connects the brother's past support to the current situation with their sister.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "WRONG_ENTITY_OR_EVENT",
            },
        },
        {
            "case_key": "final_control_neg_stale_resolved",
            "repair_family": "STALE_RESOLVED_OR_CONFLICTING",
            "v": "I finally got the biopsy results back and everything is clear — I'm just trying to process the relief.",
            "c": "In an earlier session, the user said they were terrified about what the biopsy might show.",
            "gold": {
                "current_support_goal": "The user wants to process relief now that their biopsy results came back clear.",
                "candidate_increment": "NONE for the current goal: the earlier fear is about an outcome that is now resolved and conflicts with the present relief.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE: support the present relief without reopening the earlier fear.",
                "forbidden_focus_shift": "Do not revive the earlier terror or ask the user to relive it now that the results are clear.",
                "nonuse_condition": "Omit because the user has explicitly closed that fear with a clear result.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "STALE_RESOLVED_OR_CONFLICTING",
            },
        },
        {
            "case_key": "final_control_neg_boundary",
            "repair_family": "CURRENT_BOUNDARY_FORBIDS_HISTORY",
            "v": "I'd rather not go over the details from before — can we just focus on today and what I should do about tomorrow's presentation?",
            "c": "In an earlier session, the user described feeling humiliated after a presentation went badly six months ago.",
            "gold": {
                "current_support_goal": "The user wants help preparing for tomorrow's presentation, focused only on the present.",
                "candidate_increment": "NONE under the current boundary: the user has asked not to revisit earlier material.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "NONE",
                "allowed_response_change": "NONE under the current boundary.",
                "forbidden_focus_shift": "Do not mention, allude to, or imply awareness of the earlier humiliating presentation.",
                "nonuse_condition": "Omit while the user's start-fresh request is active.",
                "final_suitability": "NOT_SUITABLE",
                "decision_reason_code": "CURRENT_BOUNDARY_FORBIDS_HISTORY",
            },
        },
        {
            "case_key": "final_control_pos_understanding",
            "repair_family": "PAST_ONLY_UNDERSTANDING_INCREMENT",
            "v": "I don't know why, but I get really quiet and just shut down whenever my manager gives me feedback in front of other people.",
            "c": "In an earlier session, the user said that at their last job, a manager once criticized their work loudly in a team meeting and it felt humiliating.",
            "gold": {
                "current_support_goal": "The user wants to understand why they shut down when their manager gives feedback in front of others.",
                "candidate_increment": "The user was once publicly and loudly criticized by a manager at a previous job, and it felt humiliating.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "UNDERSTANDING",
                "allowed_response_change": "Reflect that shutting down in front of others may connect to that earlier humiliating experience, without asserting it as the definite cause.",
                "forbidden_focus_shift": "Do not turn this into a review of the old job or the old manager instead of the current one.",
                "nonuse_condition": "Do not use if the user states the current reaction has a different, already-explained cause.",
                "final_suitability": "SUITABLE",
                "decision_reason_code": "PAST_ONLY_UNDERSTANDING_INCREMENT",
            },
        },
        {
            "case_key": "final_control_pos_question_event_a",
            "repair_family": "PAST_ONLY_QUESTION_INCREMENT_WITH_RESOLVED_EVENT",
            "v": "We're picking this back up — same call with the mortgage broker I mentioned, and I still don't know if I should ask about the rate lock extension.",
            "c": "In an earlier session about that same mortgage broker call, the user said the broker had mentioned the rate lock might expire before closing.",
            "gold": {
                "current_support_goal": "The user wants help deciding whether to ask the mortgage broker about a rate lock extension on this same call.",
                "candidate_increment": "The broker had earlier mentioned that the rate lock might expire before closing.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "ONE_QUESTION",
                "allowed_response_change": "Ask whether the rate lock expiring before closing, which the broker raised earlier, is part of what's making the extension question feel urgent now.",
                "forbidden_focus_shift": "Do not ask whether this is the same broker or call — the current text already names both; do not re-litigate entity identity.",
                "nonuse_condition": "Do not use if the user has since said the rate lock issue was already settled.",
                "final_suitability": "SUITABLE",
                "decision_reason_code": "PAST_ONLY_QUESTION_INCREMENT",
            },
            "repair_marker": {"event_binding_phrase_in_current_text": ["same call", "mortgage broker"]},
        },
        {
            "case_key": "final_control_pos_question_event_b",
            "repair_family": "PAST_ONLY_QUESTION_INCREMENT_WITH_RESOLVED_EVENT",
            "v": "I'm about to call my dad back about the inheritance paperwork — the same conversation we didn't finish yesterday.",
            "c": "In an earlier session about that same unfinished conversation with the user's dad, the user said they had not yet decided whether to bring up their sibling's objection.",
            "gold": {
                "current_support_goal": "The user wants to prepare to resume yesterday's unfinished call with their dad about the inheritance paperwork.",
                "candidate_increment": "The user had not yet decided whether to bring up their sibling's objection in this same conversation.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "ONE_QUESTION",
                "allowed_response_change": "Ask whether they've decided how to raise the sibling's objection this time, since that was left open before.",
                "forbidden_focus_shift": "Do not ask which conversation or which relative this is — the current text already names both.",
                "nonuse_condition": "Do not use if the user has already said the sibling issue was resolved separately.",
                "final_suitability": "SUITABLE",
                "decision_reason_code": "PAST_ONLY_QUESTION_INCREMENT",
            },
            "repair_marker": {"event_binding_phrase_in_current_text": ["same conversation", "dad"]},
        },
        {
            "case_key": "final_control_pos_constraint",
            "repair_family": "PAST_ONLY_RESPONSE_CONSTRAINT",
            "v": "I'm trying to figure out how to get back into a workout routine without burning out again.",
            "c": "In an earlier session, the user said that jumping straight into daily one-hour gym sessions last time led to an injury that set them back for months.",
            "gold": {
                "current_support_goal": "The user wants help restarting a workout routine without repeating a past burnout or injury.",
                "candidate_increment": "Jumping straight into daily one-hour sessions last time led to an injury that set the user back for months.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "RESPONSE_CONSTRAINT",
                "allowed_response_change": "Avoid suggesting a return to daily one-hour sessions right away, since that pace led to an injury before; favor a gradual restart.",
                "forbidden_focus_shift": "Do not dwell on the old injury itself or turn this into a medical discussion.",
                "nonuse_condition": "Do not use if the user says they've already cleared a faster restart with a doctor.",
                "final_suitability": "SUITABLE",
                "decision_reason_code": "PAST_ONLY_RESPONSE_CONSTRAINT",
            },
        },
        {
            "case_key": "final_control_pos_option",
            "repair_family": "PAST_ONLY_DECLINABLE_OPTION",
            "v": "I have another flight next month and I'm already dreading the anxiety during takeoff.",
            "c": "In an earlier session, the user said that counting backwards from 100 during a previous flight's takeoff had noticeably helped calm them down.",
            "gold": {
                "current_support_goal": "The user wants support anticipating and managing takeoff anxiety on an upcoming flight.",
                "candidate_increment": "Counting backwards from 100 during a previous flight's takeoff noticeably helped calm the user down.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "DECLINABLE_OPTION",
                "allowed_response_change": "Offer counting backwards from 100 during takeoff as something they could try again, noting it isn't the only option and they can decline it.",
                "forbidden_focus_shift": "Do not present it as a required fix or imply the anxiety is already solved.",
                "nonuse_condition": "Do not use if the user says that technique stopped working or wasn't actually helpful.",
                "final_suitability": "SUITABLE",
                "decision_reason_code": "PAST_ONLY_DECLINABLE_OPTION",
            },
        },
        {
            "case_key": "final_control_abstain_entity_meta_forbidden",
            "repair_family": "ENTITY_OR_EVENT_UNRESOLVED_WITH_META_QUESTION_FORBIDDEN",
            "v": "Something happened with one of my roommates again and now the kitchen situation is a mess.",
            "c": "In an earlier session, the user described a conflict with a roommate named Priya about dishes being left in the sink, and separately described a different conflict with a roommate named Marcus about grocery costs.",
            "gold": {
                "current_support_goal": "The user wants support with a new kitchen-related conflict with a roommate.",
                "candidate_increment": "UNRESOLVED: it is not established whether this refers to the earlier Priya/dishes conflict, the earlier Marcus/grocery-cost conflict, or a new issue.",
                "entity_link": "UNRESOLVED",
                "allowed_response_change_type": "UNRESOLVED",
                "allowed_response_change": "UNRESOLVED: the current text does not identify which roommate or which prior conflict this new kitchen situation involves.",
                "forbidden_focus_shift": "Do not guess Priya or Marcus, and do not ask a meta-question such as 'is this related to something from before' or 'which roommate do you mean' — that is clarification about the candidate, not a candidate-specific response change.",
                "nonuse_condition": "Omit until the current text names which roommate or the specific kitchen issue.",
                "final_suitability": "SEMANTIC_ABSTAIN",
                "decision_reason_code": "ENTITY_OR_EVENT_UNRESOLVED",
            },
            "repair_marker": {"meta_question_explicitly_forbidden_in_forbidden_focus_shift": ["meta-question", "which roommate", "is this related to something from before"]},
        },
        {
            "case_key": "final_control_abstain_material_change",
            "repair_family": "MATERIAL_CHANGE_UNRESOLVED",
            "v": "I'm trying to decide how to structure tomorrow's team meeting.",
            "c": "In an earlier session, the user mentioned that they generally prefer sending a written agenda before meetings rather than deciding the structure live.",
            "gold": {
                "current_support_goal": "The user wants help deciding how to structure tomorrow's team meeting.",
                "candidate_increment": "UNRESOLVED: it is not clear from the current text whether sending a written agenda first is already the user's default practice for this meeting or would be a new suggestion for them.",
                "entity_link": "RESOLVED",
                "allowed_response_change_type": "UNRESOLVED",
                "allowed_response_change": "UNRESOLVED: whether raising the written-agenda habit would add a new option or merely restate something the user already always does cannot be decided from the shown text.",
                "forbidden_focus_shift": "Do not assert that a written agenda is needed or missing without knowing whether the user already plans to send one.",
                "nonuse_condition": "Omit until the current text clarifies whether an agenda is already planned or not.",
                "final_suitability": "SEMANTIC_ABSTAIN",
                "decision_reason_code": "MATERIAL_CHANGE_UNRESOLVED",
            },
        },
    ]


def main() -> None:
    if PUBLIC_OUT.exists() or PRIVATE_OUT.exists():
        raise RuntimeError("final control repair output exists; refusing overwrite")
    if _sha(DESIGN) != EXPECTED_DESIGN_SHA256:
        raise RuntimeError("final control construct repair design drifted from the frozen bundle-bound hash")
    authority = _read(AUTHORITY)
    current = authority["current_execution_phase"]
    if current["id"] != "MS_SOURCE_ANNOTATED_CONTROL_REPAIR_DESIGN":
        raise RuntimeError("authority phase is not the fresh-control-repair-design phase; refuse to guess")

    retired = _jsonl(RETIRED_CONTROLS)
    retired_ids = {row["repair_item_id"] for row in retired}
    retired_texts = [
        " ".join(s["content"] for s in row["visible_current_spans"] + row["strictly_past_candidate_spans"])
        for row in retired
    ]
    public_201 = _jsonl(PUBLIC_201)
    public_texts = [
        " ".join(s["content"] for s in row["visible_current_spans"] + row["strictly_past_candidate_spans"])
        for row in public_201
    ]

    cases = _cases()
    controls: list[dict[str, Any]] = []
    private_key: list[dict[str, Any]] = []
    max_overlap_vs_retired = 0.0
    max_overlap_vs_public = 0.0
    repair_marker_checks: dict[str, bool] = {}

    for case in cases:
        item_id = "msrepaircontrol_" + _stable_hex(case["case_key"], "final-control-repair-v1")
        if item_id in retired_ids:
            raise RuntimeError(f"fresh item id collided with a retired id: {item_id}")
        visible_spans = [{"span_id": "V001", "speaker": "seeker", "content": case["v"]}]
        candidate_spans = [{"span_id": "C001", "kind": "strictly_prior_user_statement", "content": case["c"]}]
        item = {
            "protocol": "pm-v1.5-paper1-ms-final-control-repair-item-v1",
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
        validated = validate_review(parsed, item)  # raises on any internal inconsistency

        combined_text = case["v"] + " " + case["c"]
        overlap_vs_retired = max((_jaccard(combined_text, other) for other in retired_texts), default=0.0)
        overlap_vs_public = max((_jaccard(combined_text, other) for other in public_texts), default=0.0)
        max_overlap_vs_retired = max(max_overlap_vs_retired, overlap_vs_retired)
        max_overlap_vs_public = max(max_overlap_vs_public, overlap_vs_public)

        marker_haystacks = {
            "recurrence_in_current_text": case["v"],
            "event_binding_phrase_in_current_text": case["v"],
            "meta_question_explicitly_forbidden_in_forbidden_focus_shift": case["gold"]["forbidden_focus_shift"],
        }
        for marker_name, needles in case.get("repair_marker", {}).items():
            haystack = marker_haystacks[marker_name]
            repair_marker_checks[f"{case['case_key']}::{marker_name}"] = all(
                needle.lower() in haystack.lower() for needle in needles
            )

        controls.append(item)
        private_key.append({
            "protocol": "pm-v1.5-paper1-ms-final-control-repair-key-v1",
            "repair_item_id": item_id,
            "case_key": case["case_key"],
            "repair_family": case["repair_family"],
            "not_training": True,
            "expected_final_suitability": validated["final_suitability"],
            "expected_decision_reason_code": validated["decision_reason_code"],
            "candidate_increment": validated["candidate_increment"],
            "allowed_response_change": validated["allowed_response_change"],
            "forbidden_focus_shift": validated["forbidden_focus_shift"],
            "nonuse_condition": validated["nonuse_condition"],
            "content_overlap_vs_retired_12_max_jaccard": round(overlap_vs_retired, 6),
            "content_overlap_vs_public_201_max_jaccard": round(overlap_vs_public, 6),
        })

    controls.sort(key=lambda row: _stable_hex(row["repair_item_id"], "final-control-blind-order"))
    for position, row in enumerate(controls, start=1):
        row["review_position"] = position

    families_by_decision = {
        "NOT_SUITABLE": {row["repair_family"] for row in private_key if row["expected_final_suitability"] == "NOT_SUITABLE"},
        "SUITABLE": {row["repair_family"] for row in private_key if row["expected_final_suitability"] == "SUITABLE"},
        "SEMANTIC_ABSTAIN": {row["repair_family"] for row in private_key if row["expected_final_suitability"] == "SEMANTIC_ABSTAIN"},
    }
    gold_counts = Counter(row["expected_final_suitability"] for row in private_key)

    checks = {
        "exact_12_items": len(controls) == 12 and len(private_key) == 12,
        "unique_item_ids": len({row["repair_item_id"] for row in controls}) == 12,
        "no_id_collision_with_retired": not (retired_ids & {row["repair_item_id"] for row in controls}),
        "distribution_5_5_2": gold_counts == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2},
        "all_5_negative_families_present": set(REQUIRED_NEGATIVE_FAMILIES) == families_by_decision["NOT_SUITABLE"],
        "all_4_positive_families_present": set(REQUIRED_POSITIVE_FAMILIES) == families_by_decision["SUITABLE"],
        "all_2_abstain_families_present": set(REQUIRED_ABSTAIN_FAMILIES) == families_by_decision["SEMANTIC_ABSTAIN"],
        "content_disjoint_from_retired_12": max_overlap_vs_retired < 0.3,
        "content_disjoint_from_public_201": max_overlap_vs_public < 0.3,
        "all_gold_answers_schema_valid_via_real_contract": True,  # raised above on failure
        "annotation_template_has_all_blank_fields": all(set(row["annotation"]) == set(_annotation_template()) for row in controls),
        "repair_marker_defect_1_recurrence_stated_in_current_text": repair_marker_checks.get(
            "final_control_neg_recurrence_echo::recurrence_in_current_text", False
        ),
        "repair_marker_defect_2a_event_binding_in_current_text": repair_marker_checks.get(
            "final_control_pos_question_event_a::event_binding_phrase_in_current_text", False
        ),
        "repair_marker_defect_2b_event_binding_in_current_text": repair_marker_checks.get(
            "final_control_pos_question_event_b::event_binding_phrase_in_current_text", False
        ),
        "repair_marker_defect_3_meta_question_explicitly_forbidden": repair_marker_checks.get(
            "final_control_abstain_entity_meta_forbidden::meta_question_explicitly_forbidden_in_forbidden_focus_shift", False
        ),
        "zero_api_zero_label_zero_fit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"final control repair materialization checks failed: {checks}")

    PUBLIC_OUT.mkdir(parents=True)
    PRIVATE_OUT.mkdir(parents=True)
    controls_path = PUBLIC_OUT / "final_control_repair_controls_blind.jsonl"
    key_path = PRIVATE_OUT / "final_control_repair_key.jsonl"
    _write_jsonl(controls_path, controls)
    _write_jsonl(key_path, private_key)

    report = {
        "protocol": "pm-v1.5-paper1-ms-final-control-repair-materialization-report-v1",
        "status": "ZERO_API_FRESH_CONTROLS_MATERIALIZED_LOCAL_CONSTRUCT_AUDIT_PASS_REVIEW_CALLS_NOT_YET_AUTHORIZED",
        "checks": checks,
        "counts": {
            "items": len(controls),
            "distribution": dict(gold_counts),
        },
        "max_content_overlap_jaccard": {
            "vs_retired_12": round(max_overlap_vs_retired, 6),
            "vs_public_201": round(max_overlap_vs_public, 6),
        },
        "construct_repairs_verified": {
            "defect_1_current_echo_recurrence": "final_control_neg_recurrence_echo now states the recurrence proposition in the visible current text itself, so the past candidate is a true redundancy, not a hidden increment.",
            "defect_2_event_binding": "final_control_pos_question_event_a/b visibly bind the same entity/event via an explicit continuity phrase ('same call' / 'same conversation') before crediting the past-only proposition.",
            "defect_3_meta_question_forbidden": "final_control_abstain_entity_meta_forbidden's forbidden_focus_shift explicitly names asking which entity/whether-relevant as forbidden meta-clarification, not candidate Function.",
        },
        "next_gate": "Authorize and run the fresh-identity 24-call qualification (12 items x GPT-5.6 + Gemini) exactly once. If it fails, retire the MS label route per the pre-registered fallback and proceed with MP/ME only.",
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
            "design": _sha(DESIGN),
            "retired_controls": _sha(RETIRED_CONTROLS),
            "public_201": _sha(PUBLIC_201),
            "instrument": _sha(ROOT / "src/metacom_pm/v1_5_ms_source_annotated_suitability_review.py"),
        },
    }
    _write_json(PUBLIC_OUT / "report.json", report)
    rows_html = "".join(
        f"<tr><td>{escape(name)}</td><td>{'PASS' if value else 'FAIL'}</td></tr>" for name, value in checks.items()
    )
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>MS final control repair materialization</title>
<style>body{{font-family:system-ui;max-width:1080px;margin:2rem auto;line-height:1.5}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.45rem;text-align:left}}.ok{{color:#176b2c}}</style></head><body>
<h1>MS final control repair: fresh 12-item materialization</h1>
<p class='ok'><strong>{escape(report['status'])}</strong></p>
<h2>Distribution</h2><p>{escape(json.dumps(dict(gold_counts)))}</p>
<h2>Construct repairs verified</h2><ul>{''.join(f"<li>{escape(v)}</li>" for v in report['construct_repairs_verified'].values())}</ul>
<h2>Machine checks</h2><table><tr><th>Check</th><th>Result</th></tr>{rows_html}</table>
<h2>Next hard gate</h2><p>{escape(report['next_gate'])}</p>
</body></html>"""
    (PUBLIC_OUT / "report.html").write_text(html, encoding="utf-8")
    report["public_artifacts"]["report_html"] = {
        "path": str((PUBLIC_OUT / "report.html").relative_to(ROOT)),
        "sha256": _sha(PUBLIC_OUT / "report.html"),
    }
    _write_json(PUBLIC_OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
