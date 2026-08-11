"""Deterministic G4A packet construction for nonexclusive suitability review.

The public unit is one state-by-component-by-actual-Rank-1 case.  Selection
flags are used only to cover difficult surfaces and stay in the private key.
No function in this module creates a suitability label for a public case.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


PACKET_PROTOCOL = "pm-v1.5-paper1-v3-g4a-nonexclusive-suitability-packet-v1"
CONTROL_PROTOCOL = "pm-v1.5-paper1-v3-g4a-fresh-control-v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _opaque(prefix: str, *parts: object) -> str:
    return f"{prefix}_{_stable(_canonical([str(part) for part in parts]))[:24]}"


def _extreme_order(rows: Sequence[Mapping[str, Any]], component: str) -> list[Mapping[str, Any]]:
    """Return an outcome-blind order that alternates observed surface extremes."""

    remaining = {str(row["state_id"]): row for row in rows}
    ordered: list[Mapping[str, Any]] = []
    length_key = {
        "MP": lambda row: len(str(row.get("profile_field") or "")),
        "MS": lambda row: int(row.get("candidate_word_count") or 0),
        "ME": lambda row: int(row.get("action_word_count") or 0)
        + int(row.get("result_word_count") or 0),
    }[component]
    selectors = (
        lambda row: (float(row.get("selection_score") or 0.0), _stable(row["state_id"])),
        lambda row: (-float(row.get("selection_score") or 0.0), _stable(row["state_id"])),
        lambda row: (float(row.get("top1_top2_margin") or 0.0), _stable(row["state_id"])),
        lambda row: (-float(row.get("top1_top2_margin") or 0.0), _stable(row["state_id"])),
        lambda row: (int(row.get("candidate_age_sessions") or 0), _stable(row["state_id"])),
        lambda row: (-int(row.get("candidate_age_sessions") or 0), _stable(row["state_id"])),
        lambda row: (length_key(row), _stable(row["state_id"])),
        lambda row: (-length_key(row), _stable(row["state_id"])),
    )
    while remaining:
        for selector in selectors:
            if not remaining:
                break
            chosen = min(remaining.values(), key=selector)
            ordered.append(chosen)
            remaining.pop(str(chosen["state_id"]))
    return ordered


def _append_unique(
    selected: list[Mapping[str, Any]],
    seen: set[str],
    rows: Iterable[Mapping[str, Any]],
    limit: int,
) -> None:
    for row in rows:
        state_id = str(row["state_id"])
        if state_id in seen:
            continue
        selected.append(row)
        seen.add(state_id)
        if len(selected) == limit:
            return


def select_cases(
    diagnostics: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[str, str]]:
    """Select 204 MP, 204 MS and 99 ME cases without labels or outcomes."""

    present = [row for row in diagnostics if bool(row["candidate_present"])]
    by_state: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    by_component_group: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in present:
        state_id = str(row["state_id"])
        component = str(row["component"])
        by_state[state_id][component] = row
        by_component_group[component][str(row["split_group_key"])].append(row)

    shared_state_by_group: dict[str, str] = {}
    for state_id, component_rows in by_state.items():
        if set(component_rows) != {"MP", "MS", "ME"}:
            continue
        group = str(next(iter(component_rows.values()))["split_group_key"])
        current = shared_state_by_group.get(group)
        if current is None or _stable(state_id) < _stable(current):
            shared_state_by_group[group] = state_id
    if len(shared_state_by_group) != 14:
        raise ValueError(f"expected 14 all-three groups, found {len(shared_state_by_group)}")

    selected_by_component: dict[str, list[Mapping[str, Any]]] = {
        "MP": [],
        "MS": [],
        "ME": [],
    }

    for component in ("MP", "MS"):
        for group in sorted(by_component_group[component], key=_stable):
            pool = by_component_group[component][group]
            selected: list[Mapping[str, Any]] = []
            seen: set[str] = set()
            shared = shared_state_by_group.get(group)
            if shared is not None:
                _append_unique(selected, seen, [by_state[shared][component]], 12)
            if component == "MP":
                mandatory = sorted(
                    (row for row in pool if row.get("exact_profile_value_already_visible")),
                    key=lambda row: _stable(row["state_id"]),
                )
                _append_unique(selected, seen, mandatory, 12)
                non_job = sorted(
                    (row for row in pool if row.get("profile_field") != "job"),
                    key=lambda row: (
                        str(row.get("profile_field")),
                        _stable(row["state_id"]),
                    ),
                )
                while sum(row.get("profile_field") != "job" for row in selected) < min(
                    2, len(non_job)
                ):
                    before = len(selected)
                    _append_unique(selected, seen, non_job, min(12, len(selected) + 1))
                    if len(selected) == before:
                        break
            else:
                mandatory = sorted(
                    (
                        row
                        for row in pool
                        if row.get("low_information_rank1")
                        or row.get("exact_or_containment_current_echo")
                    ),
                    key=lambda row: _stable(row["state_id"]),
                )
                _append_unique(selected, seen, mandatory, 12)
            _append_unique(selected, seen, _extreme_order(pool, component), 12)
            if len(selected) != 12:
                raise ValueError(f"{component} {group} supplied {len(selected)}/12")
            selected_by_component[component].extend(selected)

    # ME uses all available rows in the one-row group and caps every other group
    # at seven.  Every distinct action-result candidate is represented first.
    for group in sorted(by_component_group["ME"], key=_stable):
        pool = by_component_group["ME"][group]
        limit = min(7, len(pool))
        selected: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        shared = shared_state_by_group.get(group)
        if shared is not None:
            _append_unique(selected, seen, [by_state[shared]["ME"]], limit)
        by_candidate: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in pool:
            by_candidate[str(row["actual_rank1_id"])].append(row)
        unique_representatives = [
            min(rows, key=lambda row: _stable(row["state_id"]))
            for _candidate, rows in sorted(by_candidate.items(), key=lambda item: _stable(item[0]))
        ]
        _append_unique(selected, seen, unique_representatives, limit)
        _append_unique(selected, seen, _extreme_order(pool, "ME"), limit)
        if len(selected) != limit:
            raise ValueError(f"ME {group} supplied {len(selected)}/{limit}")
        selected_by_component["ME"].extend(selected)

    if {component: len(rows) for component, rows in selected_by_component.items()} != {
        "MP": 204,
        "MS": 204,
        "ME": 99,
    }:
        raise ValueError("G4A component denominators drifted")
    return [
        row
        for component in ("MP", "MS", "ME")
        for row in selected_by_component[component]
    ], shared_state_by_group


def _visible_spans(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "span_id": f"V{index:03d}",
            "speaker": str(turn["speaker"]),
            "content": str(turn["content"]),
        }
        for index, turn in enumerate(state["visible_current_session_dialogue"], start=1)
    ]


def _candidate_surface(
    candidate: Mapping[str, Any], component: str, age_sessions: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if component == "MP":
        spans = [
            {
                "span_id": "C001",
                "kind": "verified_profile_fact",
                "content": str(candidate["literal_text"]),
            }
        ]
        metadata = {
            "owner_status": "CURRENT_USER_VERIFIED",
            "time_status": "STABLE_PROFILE_AVAILABLE_BEFORE_CURRENT_SESSION",
            "profile_field": str(candidate["profile_field"]),
        }
    elif component == "MS":
        spans = [
            {
                "span_id": "C001",
                "kind": "strictly_prior_user_statement",
                "content": str(candidate["literal_text"]),
            }
        ]
        metadata = {
            "owner_status": "CURRENT_USER_VERIFIED",
            "time_status": "STRICTLY_PRIOR_SESSION_MAY_HAVE_CHANGED",
            "age_sessions": age_sessions,
        }
    else:
        spans = [
            {
                "span_id": "C001",
                "kind": "verified_past_action",
                "content": str(candidate["action_span"]),
            },
            {
                "span_id": "C002",
                "kind": "verified_observed_result",
                "content": str(candidate["result_span"]),
            },
        ]
        metadata = {
            "owner_status": "CURRENT_USER_VERIFIED",
            "time_status": "STRICTLY_PRIOR_ACTION_RESULT_NO_RECURRENCE_GUARANTEE",
            "age_sessions": age_sessions,
        }
    return spans, metadata


def build_packets(
    *,
    selected: Sequence[Mapping[str, Any]],
    states: Mapping[str, Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
    design: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    common: list[tuple[str, dict[str, Any], Mapping[str, Any]]] = []
    private: list[dict[str, Any]] = []
    for row in selected:
        state_id = str(row["state_id"])
        component = str(row["component"])
        candidate_id = str(row["actual_rank1_id"])
        case_key = _opaque("g4case", state_id, component, candidate_id)
        candidate_spans, candidate_metadata = _candidate_surface(
            candidates[candidate_id], component, int(row["candidate_age_sessions"])
        )
        anchors = design["component_anchors"][component]
        surface = {
            "protocol": PACKET_PROTOCOL,
            "component": component,
            "component_name": anchors["name"],
            "component_minimum": anchors["suitable_minimum"],
            "visible_spans": _visible_spans(states[state_id]),
            "candidate_spans": candidate_spans,
            "candidate_metadata": candidate_metadata,
            "decision_contract": {
                "values": ["SUITABLE", "NOT_SUITABLE", "SEMANTIC_ABSTAIN"],
                "one_component_candidate_only": True,
                "not_a_comparison_with_other_components": True,
                "checklist_attestation_value": "ALL_FOUR_CONSIDERED",
                "checklist": design["review_instrument"][
                    "checklist_is_attestation_not_four_labels"
                ],
                "suitable_reason_codes": anchors["suitable_reason_codes"],
                "not_suitable_reason_codes": anchors["not_suitable_reason_codes"],
                "abstain_reason_codes": [
                    "TARGET_OR_ENTITY_UNRESOLVED",
                    "REDUNDANCY_UNRESOLVED",
                    "MATERIAL_USE_UNRESOLVED",
                    "BOUNDARY_UNRESOLVED",
                ],
                "evidence_submission": "PRE_NUMBERED_SPAN_IDS_ONLY",
            },
            "annotation_schema": {
                "review_item_id": "COPY_EXACTLY",
                "decision": "ONE_OF_DECISION_VALUES",
                "primary_reason_code": "ONE_ALLOWED_CODE_FOR_DECISION",
                "visible_span_ids": ["V..."],
                "candidate_span_ids": ["C..."],
                "checklist_attested": "ALL_FOUR_CONSIDERED",
            },
        }
        common.append((case_key, surface, row))
        private.append(
            {
                "case_key": case_key,
                "state_id": state_id,
                "component": component,
                "actual_rank1_id": candidate_id,
                "runtime_owner_key": str(row["runtime_owner_key"]),
                "split_group_key": str(row["split_group_key"]),
                "outer_fold": row.get("outer_fold"),
                "selection_score": row.get("selection_score"),
                "top1_top2_margin": row.get("top1_top2_margin"),
                "proxy_flags": {
                    key: row[key]
                    for key in (
                        "exact_profile_value_already_visible",
                        "profile_field",
                        "low_information_rank1",
                        "exact_or_containment_current_echo",
                        "typed_action_and_result_exact",
                        "compiler_valid",
                    )
                    if key in row
                },
                "suitability_label": None,
                "proxy_flags_are_not_labels": True,
            }
        )

    packets: dict[str, list[dict[str, Any]]] = {}
    for reviewer in ("A", "B"):
        ordered = sorted(common, key=lambda value: _stable(f"G4A-{reviewer}:{value[0]}"))
        packets[reviewer] = [
            {
                **surface,
                "review_item_id": _opaque("g4review", reviewer, case_key),
                "review_position": position,
            }
            for position, (case_key, surface, _row) in enumerate(ordered, start=1)
        ]
        item_ids = {
            case_key: _opaque("g4review", reviewer, case_key)
            for case_key, _surface, _row in common
        }
        for private_row in private:
            private_row[f"reviewer_{reviewer.lower()}_item_id"] = item_ids[
                private_row["case_key"]
            ]
    return packets["A"], packets["B"], private


def _control_surface(
    component: str,
    ordinal: int,
    visible: Sequence[tuple[str, str]],
    candidate_spans: Sequence[tuple[str, str]],
    gold: str,
    reason: str,
    design: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_key = _opaque("g4control", component, ordinal, visible, candidate_spans)
    anchors = design["component_anchors"][component]
    surface = {
        "protocol": CONTROL_PROTOCOL,
        "component": component,
        "component_name": anchors["name"],
        "component_minimum": anchors["suitable_minimum"],
        "visible_spans": [
            {"span_id": f"V{index:03d}", "speaker": speaker, "content": content}
            for index, (speaker, content) in enumerate(visible, start=1)
        ],
        "candidate_spans": [
            {"span_id": f"C{index:03d}", "kind": kind, "content": content}
            for index, (kind, content) in enumerate(candidate_spans, start=1)
        ],
        "candidate_metadata": {
            "owner_status": "CURRENT_USER_VERIFIED",
            "time_status": (
                "STABLE_PROFILE_AVAILABLE_BEFORE_CURRENT_SESSION"
                if component == "MP"
                else "STRICTLY_PRIOR_USER_EVIDENCE_MAY_HAVE_CHANGED"
            ),
        },
        "decision_contract": {
            "values": ["SUITABLE", "NOT_SUITABLE", "SEMANTIC_ABSTAIN"],
            "one_component_candidate_only": True,
            "not_a_comparison_with_other_components": True,
            "checklist_attestation_value": "ALL_FOUR_CONSIDERED",
            "checklist": design["review_instrument"][
                "checklist_is_attestation_not_four_labels"
            ],
            "suitable_reason_codes": anchors["suitable_reason_codes"],
            "not_suitable_reason_codes": anchors["not_suitable_reason_codes"],
            "abstain_reason_codes": [
                "TARGET_OR_ENTITY_UNRESOLVED",
                "REDUNDANCY_UNRESOLVED",
                "MATERIAL_USE_UNRESOLVED",
                "BOUNDARY_UNRESOLVED",
            ],
            "evidence_submission": "PRE_NUMBERED_SPAN_IDS_ONLY",
        },
        "annotation_schema": {
            "review_item_id": "COPY_EXACTLY",
            "decision": "ONE_OF_DECISION_VALUES",
            "primary_reason_code": "ONE_ALLOWED_CODE_FOR_DECISION",
            "visible_span_ids": ["V..."],
            "candidate_span_ids": ["C..."],
            "checklist_attested": "ALL_FOUR_CONSIDERED",
        },
    }
    key = {
        "case_key": case_key,
        "component": component,
        "gold_decision": gold,
        "gold_primary_reason_code": reason,
        "fresh_control_not_training": True,
    }
    return surface, key


def build_fresh_controls(
    design: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build 36 fresh controls: per head 5 suitable, 5 not, 2 abstain."""

    # These cases use new wording and situations, and their gold is a single
    # anchored decision rather than the retired four-axis projection.
    specs: dict[str, list[tuple[Sequence[tuple[str, str]], Sequence[tuple[str, str]], str, str]]] = {
        "MP": [
            ([('seeker', 'I need a sleep step that I can follow consistently instead of a plan that only works on some days.')], [('profile_fact', 'work schedule: rotating weekly shifts')], 'SUITABLE', 'MATERIAL_CONSTRAINT'),
            ([('seeker', 'The in-person appointment is across town; help me choose a realistic way to attend it.')], [('profile_fact', 'transport constraint: does not have access to a car')], 'SUITABLE', 'MATERIAL_LOGISTICAL_DETAIL'),
            ([('seeker', 'This plan has several steps and I need them presented in a format I can reliably use.')], [('profile_fact', 'communication access: relies on written instructions')], 'SUITABLE', 'MATERIAL_FRAMING'),
            ([('seeker', 'I need an approach that can fit around my responsibilities at home without becoming another large task.')], [('profile_fact', 'caregiving role: primary caregiver for an older parent')], 'SUITABLE', 'MATERIAL_CONSTRAINT'),
            ([('seeker', 'I need to discuss asking for an extension and choose a realistic time to contact the office.')], [('profile_fact', 'employment: works overnight')], 'SUITABLE', 'MATERIAL_PREMISE'),
            ([('seeker', 'I am grieving my dog and only want help naming what I feel.')], [('profile_fact', 'job: civil engineer')], 'NOT_SUITABLE', 'CURRENT_SCOPE_MISMATCH'),
            ([('seeker', 'As a wheelchair user, stairs are not an option; I need an accessible route.')], [('profile_fact', 'mobility: uses a wheelchair')], 'NOT_SUITABLE', 'ALREADY_VISIBLE'),
            ([('seeker', 'Please use only what I say here and do not consult my saved profile.')], [('profile_fact', 'preferred language: English')], 'NOT_SUITABLE', 'CURRENT_BOUNDARY_FORBIDS_PROFILE'),
            ([('seeker', 'I feel uncertain about how my colleague interpreted the email.')], [('profile_fact', 'job: accountant')], 'NOT_SUITABLE', 'DECORATIVE_ONLY'),
            ([('seeker', 'I am worried about tomorrow.')], [('profile_fact', 'nationality: Canadian')], 'NOT_SUITABLE', 'UNSUPPORTED_INFERENCE_REQUIRED'),
            ([('seeker', 'Work has become difficult, but I cannot yet say whether the problem is scheduling, money, conflict, or something else.')], [('profile_fact', 'job: nurse')], 'SEMANTIC_ABSTAIN', 'TARGET_OR_ENTITY_UNRESOLVED'),
            ([('seeker', 'I need support nearby, but I have not said whether I mean transport, people, services, or simply being heard.')], [('profile_fact', 'location: small rural town')], 'SEMANTIC_ABSTAIN', 'MATERIAL_USE_UNRESOLVED'),
        ],
        "MS": [
            ([('seeker', 'The same supervisor meeting is tomorrow, and I want to prepare for the point where I freeze.')], [('strictly_prior_user_statement', 'Last month, the user said they froze after the supervisor asked for an immediate answer.')], 'SUITABLE', 'CHANGES_CURRENT_OPTION'),
            ([('seeker', 'The headaches have returned in the morning and I am trying to describe the pattern accurately.')], [('strictly_prior_user_statement', 'In a prior session, the user said the headaches usually began before breakfast.')], 'SUITABLE', 'CHANGES_CURRENT_UNDERSTANDING'),
            ([('seeker', 'I want one focused question to help me untangle why the call with my sister felt different.')], [('strictly_prior_user_statement', 'In the prior call, the sister ended the conversation immediately after money was mentioned.')], 'SUITABLE', 'CHANGES_ONE_QUESTION'),
            ([('seeker', 'I need a very low-pressure way to return to the application today.')], [('strictly_prior_user_statement', 'Previously the user said a ten-minute timer made starting the application feel manageable.')], 'SUITABLE', 'CHANGES_RESPONSE_CONSTRAINT'),
            ([('seeker', 'The landlord dispute is active again; I want to understand what has changed since the first notice.')], [('strictly_prior_user_statement', 'In a prior session, the user said the first notice did not state an amount or deadline.')], 'SUITABLE', 'CHANGES_CURRENT_UNDERSTANDING'),
            ([('seeker', 'Today I need help with a rent increase.')], [('strictly_prior_user_statement', 'Thanks, I really appreciate it.')], 'NOT_SUITABLE', 'LOW_INFORMATION_OR_PHATIC'),
            ([('seeker', 'My manager interrupted me three times in today’s meeting; that exact pattern is what I want to discuss.')], [('strictly_prior_user_statement', 'Previously the user said their manager interrupted them repeatedly in a meeting.')], 'NOT_SUITABLE', 'CURRENT_ECHO_OR_CONTAINMENT'),
            ([('seeker', 'I need support after an argument with my brother.')], [('strictly_prior_user_statement', 'Previously the user discussed a disagreement with a landlord about repairs.')], 'NOT_SUITABLE', 'WRONG_ENTITY_OR_EVENT'),
            ([('seeker', 'The exam is over and the result was fine; I want to move to a new concern about housing.')], [('strictly_prior_user_statement', 'Before the exam, the user feared they would fail it.')], 'NOT_SUITABLE', 'STALE_RESOLVED_OR_CONFLICTING'),
            ([('seeker', 'Do not bring in anything from earlier sessions. I want to start fresh here.')], [('strictly_prior_user_statement', 'In a prior session, the user said mornings were the hardest time.')], 'NOT_SUITABLE', 'CURRENT_BOUNDARY_FORBIDS_HISTORY'),
            ([('seeker', 'The problem at home happened again, but I have not said who was involved or what happened this time.')], [('strictly_prior_user_statement', 'In a prior session, the user described both a roommate dispute and a separate conflict with a parent.')], 'SEMANTIC_ABSTAIN', 'TARGET_OR_ENTITY_UNRESOLVED'),
            ([('seeker', 'Something feels different now, though I cannot tell whether the old issue is still relevant.')], [('strictly_prior_user_statement', 'Previously the user said evening walks reduced their tension.')], 'SEMANTIC_ABSTAIN', 'MATERIAL_USE_UNRESOLVED'),
        ],
        "ME": [
            ([('seeker', 'My thoughts are racing again and I would like one optional idea grounded in something that helped me before.')], [('past_action', 'The user wrote each worry on paper before bed.'), ('observed_result', 'They reported that the thoughts slowed enough to rest.')], 'SUITABLE', 'CURRENT_READY_DECLINABLE_OPTION'),
            ([('seeker', 'I have another meeting tomorrow and want to consider what made the last one manageable.')], [('past_action', 'The user requested the agenda in advance.'), ('observed_result', 'They reported feeling prepared enough to speak once.')], 'SUITABLE', 'CURRENT_READY_USER_EVIDENCE'),
            ([('seeker', 'I want one low-burden way to begin this task, and I am open to revisiting my own earlier experience.')], [('past_action', 'The user set a five-minute timer and opened the document.'), ('observed_result', 'They reported continuing for twenty minutes without forcing it.')], 'SUITABLE', 'TRANSFERABLE_WITH_TENTATIVE_FRAMING'),
            ([('seeker', 'The commute is overwhelming again; could we look at an option I have already tested?')], [('past_action', 'The user took an earlier train before a crowded commute.'), ('observed_result', 'They reported arriving calmer and on time.')], 'SUITABLE', 'CURRENT_READY_DECLINABLE_OPTION'),
            ([('seeker', 'I want evidence from my own experience before deciding whether to ask for written instructions.')], [('past_action', 'The user asked a colleague to send the steps in writing.'), ('observed_result', 'They reported completing the task with fewer mistakes.')], 'SUITABLE', 'CURRENT_READY_USER_EVIDENCE'),
            ([('seeker', 'I only want space to grieve tonight, not an action or suggestion.')], [('past_action', 'The user used a calendar reminder for a bill.'), ('observed_result', 'The bill was paid on time.')], 'NOT_SUITABLE', 'CURRENT_GOAL_NOT_ACTION_READY'),
            ([('seeker', 'I need help with a conflict between two friends.')], [('past_action', 'The user asked a landlord for a written repair date.'), ('observed_result', 'The repair was scheduled the next day.')], 'NOT_SUITABLE', 'ACTION_RESULT_NOT_TRANSFERABLE'),
            ([('seeker', 'I already tried the five-minute timer today and chose not to continue with it.')], [('past_action', 'The user used a five-minute timer to start the task.'), ('observed_result', 'They previously reported continuing for twenty minutes.')], 'NOT_SUITABLE', 'ALREADY_VISIBLE_OR_ALREADY_CHOSEN'),
            ([('seeker', 'Please do not use earlier experiences or suggest any action.')], [('past_action', 'The user wrote worries before bed.'), ('observed_result', 'They previously reported resting more easily.')], 'NOT_SUITABLE', 'CURRENT_BOUNDARY_FORBIDS_ACTION_OR_HISTORY'),
            ([('seeker', 'I want to understand the sadness after my friend moved away; please do not turn this into planning.')], [('past_action', 'The user arrived early to one prior meeting.'), ('observed_result', 'That meeting started calmly.')], 'NOT_SUITABLE', 'CURRENT_GOAL_NOT_ACTION_READY'),
            ([('seeker', 'I may want an option, but I have not said whether the current problem is sleep, work, or a relationship.')], [('past_action', 'The user wrote a short list before starting.'), ('observed_result', 'They reported feeling less overwhelmed.')], 'SEMANTIC_ABSTAIN', 'TARGET_OR_ENTITY_UNRESOLVED'),
            ([('seeker', 'I am not sure whether I want advice or only to be heard; I have not decided yet.')], [('past_action', 'The user took a short walk after a difficult call.'), ('observed_result', 'They reported that their breathing settled.')], 'SEMANTIC_ABSTAIN', 'MATERIAL_USE_UNRESOLVED'),
        ],
    }
    common: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for component in ("MP", "MS", "ME"):
        for ordinal, (visible, candidate, gold, reason) in enumerate(specs[component], start=1):
            surface, key = _control_surface(
                component, ordinal, visible, candidate, gold, reason, design
            )
            common.append((key["case_key"], surface, key))
    packets: dict[str, list[dict[str, Any]]] = {}
    for reviewer in ("A", "B"):
        ordered = sorted(common, key=lambda value: _stable(f"G4A-control-{reviewer}:{value[0]}"))
        packets[reviewer] = [
            {
                **surface,
                "review_item_id": _opaque("g4controlreview", reviewer, case_key),
                "review_position": position,
            }
            for position, (case_key, surface, _key) in enumerate(ordered, start=1)
        ]
    private = []
    for case_key, _surface, key in common:
        private.append(
            {
                **key,
                "reviewer_a_item_id": _opaque("g4controlreview", "A", case_key),
                "reviewer_b_item_id": _opaque("g4controlreview", "B", case_key),
            }
        )
    return packets["A"], packets["B"], private


def public_surface_signature(row: Mapping[str, Any]) -> str:
    excluded = {"review_item_id", "review_position"}
    return _stable(_canonical({key: value for key, value in row.items() if key not in excluded}))
