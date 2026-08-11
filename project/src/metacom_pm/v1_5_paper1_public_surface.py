"""Deterministic, zero-model structural materialization for Paper 1 P1.

This module creates only unlabeled state references, literal raw-source
candidate catalogs, canonical groups, and physically separated QA surfaces.
It does not retrieve Rank-1, call an encoder or API, create PM labels, inspect
observed response quality, or train a model.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .v1_5_v5_2_atomic_memory import (
    compile_atomic_reusable_outcome,
    compile_atomic_session_observation,
)


PUBLIC_SURFACE_PROTOCOL = "pm-v1.5-paper1-public-structural-surface-v1"


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _opaque(prefix: str, *parts: Any) -> str:
    raw = _canonical([str(part) for part in parts]).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:24]}"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(_canonical(dict(row)) + "\n")
            count += 1
    return count


def _contains_key(value: Any, denied: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in denied:
                found.add(str(key))
            found.update(_contains_key(item, denied))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            found.update(_contains_key(item, denied))
    return found


def build_esconv_states(
    dialogues: Sequence[Mapping[str, Any]],
    split_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(dialogues) != len(split_rows):
        raise ValueError("ESConv source and split manifest lengths differ")
    states: list[dict[str, Any]] = []
    for raw_index, (dialogue, split_row) in enumerate(
        zip(dialogues, split_rows, strict=True)
    ):
        dialogue_id = f"esconv_{raw_index:04d}"
        if (
            split_row.get("index") != raw_index
            or split_row.get("dialogue_id") != dialogue_id
        ):
            raise ValueError("ESConv split manifest is reordered")
        if bool(split_row.get("excluded_for_evoemo_overlap")):
            continue
        split = str(split_row["split"])
        turns = list(dialogue.get("dialog") or [])
        visible: list[dict[str, Any]] = []
        for turn_index, turn in enumerate(turns):
            speaker = str(turn.get("speaker") or "")
            content = _compact(turn.get("content"))
            if speaker not in {"seeker", "supporter"} or not content:
                continue
            visible.append(
                {
                    "raw_turn_index": turn_index,
                    "speaker": speaker,
                    "content": content,
                }
            )
            if speaker != "seeker":
                continue
            later_supporter_exists = any(
                later.get("speaker") == "supporter"
                and _compact(later.get("content"))
                for later in turns[turn_index + 1 :]
            )
            if not later_supporter_exists:
                continue
            state_id = f"esconv::{dialogue_id}::seeker_turn::{turn_index}"
            states.append(
                {
                    "protocol": PUBLIC_SURFACE_PROTOCOL,
                    "dataset": "ESConv",
                    "state_id": state_id,
                    "runtime_owner_key": f"esconv::{dialogue_id}",
                    "split_group_key": f"esconv::{dialogue_id}",
                    "dialogue_id": dialogue_id,
                    "split": split,
                    "raw_current_turn_index": turn_index,
                    "current_user_text": content,
                    "visible_dialogue": list(visible),
                    "memory_available": {"MP": False, "MS": False, "ME": False},
                    "rs_bank_bound": True,
                    "label": None,
                }
            )
    return states


def _evo_user_component_map(
    users: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    owners_by_session: dict[str, set[str]] = defaultdict(set)
    user_ids = [str(user["id"]) for user in users]
    for user in users:
        user_id = str(user["id"])
        for session in user.get("dialog_history") or []:
            owners_by_session[str(session["id"])].add(user_id)
    adjacency = {user_id: set() for user_id in user_ids}
    for owners in owners_by_session.values():
        for owner in owners:
            adjacency[owner].update(owners - {owner})
    result: dict[str, str] = {}
    seen: set[str] = set()
    for user_id in sorted(user_ids, key=lambda value: int(value[1:])):
        if user_id in seen:
            continue
        stack = [user_id]
        component: list[str] = []
        seen.add(user_id)
        while stack:
            current = stack.pop()
            component.append(current)
            for linked in sorted(adjacency[current]):
                if linked not in seen:
                    seen.add(linked)
                    stack.append(linked)
        ordered = sorted(component, key=lambda value: int(value[1:]))
        component_id = "evo_component::" + "__".join(ordered)
        for owner in ordered:
            result[owner] = component_id
    return result


def build_evo_states_and_candidates(
    users: Sequence[Mapping[str, Any]],
    fold_by_user: Mapping[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    component_by_user = _evo_user_component_map(users)
    states: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for component_id in sorted(set(component_by_user.values())):
        owners = sorted(
            [owner for owner, value in component_by_user.items() if value == component_id],
            key=lambda value: int(value[1:]),
        )
        folds = {int(fold_by_user[owner]) for owner in owners}
        if len(folds) != 1:
            raise ValueError(f"connected EvoEmo owners cross folds: {owners}")
        groups.append(
            {
                "dataset": "EvoEmo",
                "split_group_key": component_id,
                "runtime_owners": owners,
                "outer_fold": next(iter(folds)),
            }
        )

    for user in users:
        user_id = str(user["id"])
        owner = f"evo::{user_id}"
        component_id = component_by_user[user_id]
        fold = int(fold_by_user[user_id])
        profile_ids: list[str] = []
        for key, raw_value in sorted((user.get("basic_info") or {}).items()):
            if key == "name":
                continue
            value = _compact(raw_value)
            if not value:
                continue
            candidate_id = _opaque("mp", user_id, key, value)
            profile_ids.append(candidate_id)
            candidates.append(
                {
                    "protocol": PUBLIC_SURFACE_PROTOCOL,
                    "candidate_id": candidate_id,
                    "component": "MP",
                    "subtype": "MP_PROFILE",
                    "runtime_owner_key": owner,
                    "split_group_key": component_id,
                    "outer_fold": fold,
                    "available_after_session_index": 0,
                    "source_session_id": "ONBOARDING_BASIC_INFO",
                    "source_turn_index": None,
                    "profile_field": str(key),
                    "literal_text": f"{key}: {value}",
                    "action_span": None,
                    "result_span": None,
                }
            )

        prior_ms_ids: list[str] = []
        prior_me_ids: list[str] = []
        sessions = list(user.get("dialog_history") or [])
        for session_index, session in enumerate(sessions, start=1):
            session_id = str(session["id"])
            visible: list[dict[str, Any]] = []
            dialogue = list(session.get("dialogue") or [])
            for turn in dialogue:
                role = str(turn.get("role") or "")
                content = _compact(turn.get("content"))
                raw_turn_index = int(turn.get("idx") or 0)
                if role not in {"seeker", "supporter"} or not content:
                    continue
                visible.append(
                    {
                        "raw_turn_index": raw_turn_index,
                        "speaker": role,
                        "content": content,
                    }
                )
                if role != "seeker":
                    continue
                state_id = (
                    f"evo::{user_id}::{session_id}::seeker_turn::{raw_turn_index}"
                )
                states.append(
                    {
                        "protocol": PUBLIC_SURFACE_PROTOCOL,
                        "dataset": "EvoEmo",
                        "state_id": state_id,
                        "runtime_owner_key": owner,
                        "split_group_key": component_id,
                        "outer_fold": fold,
                        "source_session_id": session_id,
                        "source_session_index": session_index,
                        "raw_current_turn_index": raw_turn_index,
                        "current_user_text": content,
                        "visible_current_session_dialogue": list(visible),
                        "completed_prior_session_ids": [
                            str(previous["id"])
                            for previous in sessions[: session_index - 1]
                        ],
                        "candidate_source_counts": {
                            "MP": len(profile_ids),
                            "MS": len(prior_ms_ids),
                            "ME": len(prior_me_ids),
                        },
                        "rs_bank_bound": True,
                        "label": None,
                    }
                )

            # Open literal candidates only after the complete source session closes.
            for turn in dialogue:
                if str(turn.get("role") or "") != "seeker":
                    continue
                content = _compact(turn.get("content"))
                raw_turn_index = int(turn.get("idx") or 0)
                if not content:
                    continue
                ms = compile_atomic_session_observation(content)
                if ms is not None:
                    candidate_id = _opaque(
                        "ms", user_id, session_id, raw_turn_index, content
                    )
                    prior_ms_ids.append(candidate_id)
                    candidates.append(
                        {
                            "protocol": PUBLIC_SURFACE_PROTOCOL,
                            "candidate_id": candidate_id,
                            "component": "MS",
                            "subtype": "MS_SESSION",
                            "runtime_owner_key": owner,
                            "split_group_key": component_id,
                            "outer_fold": fold,
                            "available_after_session_index": session_index,
                            "source_session_id": session_id,
                            "source_turn_index": raw_turn_index,
                            "profile_field": None,
                            "literal_text": ms.literal_past_note,
                            "action_span": None,
                            "result_span": None,
                        }
                    )
                me = compile_atomic_reusable_outcome(content)
                if me is not None:
                    candidate_id = _opaque(
                        "me", user_id, session_id, raw_turn_index, me.literal_evidence_span
                    )
                    prior_me_ids.append(candidate_id)
                    candidates.append(
                        {
                            "protocol": PUBLIC_SURFACE_PROTOCOL,
                            "candidate_id": candidate_id,
                            "component": "ME",
                            "subtype": "ME_REUSABLE_OUTCOME",
                            "runtime_owner_key": owner,
                            "split_group_key": component_id,
                            "outer_fold": fold,
                            "available_after_session_index": session_index,
                            "source_session_id": session_id,
                            "source_turn_index": raw_turn_index,
                            "profile_field": None,
                            "literal_text": me.literal_evidence_span,
                            "action_span": me.past_action_span,
                            "result_span": me.observed_outcome_span,
                            "outcome_polarity": me.polarity,
                        }
                    )
    return states, candidates, groups


def build_qa_surfaces(
    users: Sequence[Mapping[str, Any]],
    fold_by_user: Mapping[str, int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    component_by_user = _evo_user_component_map(users)
    visible_rows: list[dict[str, Any]] = []
    evaluator_rows: list[dict[str, Any]] = []
    for user in users:
        user_id = str(user["id"])
        component_id = component_by_user[user_id]
        fold = int(fold_by_user[user_id])
        for group in user.get("questions") or []:
            group_id = str(group["id"])
            for question in group.get("questions") or []:
                idx = int(question["idx"])
                question_id = _opaque("qa", user_id, group_id, idx)
                visible_rows.append(
                    {
                        "protocol": PUBLIC_SURFACE_PROTOCOL,
                        "question_id": question_id,
                        "question": _compact(question["question"]),
                        "history_surface_key": _opaque("history", user_id),
                    }
                )
                evaluator_rows.append(
                    {
                        "protocol": PUBLIC_SURFACE_PROTOCOL,
                        "question_id": question_id,
                        "wrapper_user_id": user_id,
                        "split_group_key": component_id,
                        "outer_fold": fold,
                        "question_group_id": group_id,
                        "question_idx": idx,
                        "capability": str(question["capability"]),
                        "answer": question.get("answer"),
                        "evidence": question.get("evidence"),
                    }
                )
    return visible_rows, evaluator_rows


def validate_surfaces(
    *,
    esconv_states: Sequence[Mapping[str, Any]],
    evo_states: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    qa_visible: Sequence[Mapping[str, Any]],
    qa_evaluator: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    runtime_denied = {
        "summary",
        "observation",
        "event_experience",
        "social_relationship",
        "summaries",
        "subsequent_topics",
        "questions",
        "answer",
        "evidence",
        "capability",
        "annotation",
        "survey_score",
        "situation",
    }
    runtime_found = set()
    for row in [*esconv_states, *evo_states, *candidates, *qa_visible]:
        runtime_found.update(_contains_key(row, runtime_denied))
    ids = [str(row["state_id"]) for row in [*esconv_states, *evo_states]]
    candidate_ids = [str(row["candidate_id"]) for row in candidates]
    visible_question_ids = {str(row["question_id"]) for row in qa_visible}
    evaluator_question_ids = {str(row["question_id"]) for row in qa_evaluator}
    strict_past_valid = all(
        int(row["available_after_session_index"]) >= 0
        for row in candidates
    ) and all(
        int(row["candidate_source_counts"]["MS"]) >= 0
        and int(row["candidate_source_counts"]["ME"]) >= 0
        for row in evo_states
    )
    checks = {
        "runtime_forbidden_keys_absent": not runtime_found,
        "state_ids_unique": len(ids) == len(set(ids)),
        "candidate_ids_unique": len(candidate_ids) == len(set(candidate_ids)),
        "qa_question_id_sets_match": visible_question_ids == evaluator_question_ids,
        "qa_visible_has_no_owner_or_gold": all(
            not ({"wrapper_user_id", "answer", "evidence", "capability"} & set(row))
            for row in qa_visible
        ),
        "candidate_owner_present": all(row.get("runtime_owner_key") for row in candidates),
        "strict_past_fields_well_formed": strict_past_valid,
        "labels_absent": all(row.get("label") is None for row in [*esconv_states, *evo_states]),
    }
    return {
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "runtime_forbidden_keys_found": sorted(runtime_found),
    }


def write_structural_surface(
    *,
    output_dir: Path,
    private_output_dir: Path,
    esconv_states: Sequence[Mapping[str, Any]],
    evo_states: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
    qa_visible: Sequence[Mapping[str, Any]],
    qa_evaluator: Sequence[Mapping[str, Any]],
    source_index: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_surfaces(
        esconv_states=esconv_states,
        evo_states=evo_states,
        candidates=candidates,
        qa_visible=qa_visible,
        qa_evaluator=qa_evaluator,
    )
    if validation["failed_checks"]:
        raise ValueError(f"surface validation failed: {validation['failed_checks']}")
    paths = {
        "source_index": output_dir / "source_index.json",
        "esconv_states": output_dir / "esconv_states_unlabeled.jsonl",
        "evoemo_states": output_dir / "evoemo_states_unlabeled.jsonl",
        "evoemo_candidates": output_dir / "evoemo_candidates_unlabeled.jsonl",
        "qa_generator_visible": output_dir / "qa_generator_visible.jsonl",
        "qa_evaluator_only": private_output_dir / "qa_evaluator_only.jsonl",
        "canonical_groups": output_dir / "canonical_groups.jsonl",
        "audit_report": output_dir / "audit_report.json",
    }
    _write_json(paths["source_index"], dict(source_index))
    counts = {
        "esconv_states": _write_jsonl(paths["esconv_states"], esconv_states),
        "evoemo_states": _write_jsonl(paths["evoemo_states"], evo_states),
        "evoemo_candidates": _write_jsonl(paths["evoemo_candidates"], candidates),
        "qa_generator_visible": _write_jsonl(paths["qa_generator_visible"], qa_visible),
        "qa_evaluator_only": _write_jsonl(paths["qa_evaluator_only"], qa_evaluator),
        "canonical_groups": _write_jsonl(paths["canonical_groups"], groups),
    }
    report = {
        "protocol": PUBLIC_SURFACE_PROTOCOL,
        "status": "P1_STRUCTURAL_SURFACE_PASS_ACTUAL_RANK1_NOT_YET_MATERIALIZED",
        "counts": counts,
        "validation": validation,
        "artifacts": {
            name: {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in paths.items()
            if name != "audit_report"
        },
        "actual_rank1_materialized": False,
        "api_calls": 0,
        "responses_generated": 0,
        "labels_created": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }
    _write_json(paths["audit_report"], report)
    return report
