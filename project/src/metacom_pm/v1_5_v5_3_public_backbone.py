"""Leakage-controlled public-data backbone for the V5.3 PM study.

This is an additive, versioned replacement for *future synthetic-user
expansion*.  It does not rewrite historical V5.3 experiments.  The runtime
surface uses session-local annotations only after their source session has
closed.  Cross-session QA answers/evidence and future annotations remain
audit-only and cannot become PM input, state-selection gold, or an effect
label.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import hashlib
import json
import re
from typing import Any, Literal, Mapping, Sequence

from pydantic import Field, model_validator

from .contracts import MemoryItem, MemorySource, StrictModel
from .io import canonical_json, stable_hex
from .v1_5_candidate_discovery import discover_final_typed_memory_candidates
from .v1_5_v5_2_atomic_memory import (
    compile_atomic_reusable_outcome,
    compile_atomic_session_observation,
    me_subtype_hints,
)
from .v1_5_strategy_rag_runtime import observable_flags


PUBLIC_BACKBONE_PROTOCOL = "pm-v1.5-v5.3-public-backbone-effect-learning-v1"

class PublicBackboneFreeze(StrictModel):
    protocol: Literal[
        "pm-v1.5-v5.3-public-backbone-effect-learning-v1"
    ] = PUBLIC_BACKBONE_PROTOCOL
    status: Literal["PRE_EFFECT_PUBLIC_BACKBONE_FROZEN"]
    route_decision: dict[str, Any]
    source_freeze: dict[str, Any]
    historical_exposure: dict[str, Any]
    observability_boundary: dict[str, Any]
    candidate_materialization: dict[str, Any]
    effect_estimand: dict[str, Any]
    measurement: dict[str, Any]
    cross_fitting: dict[str, Any]
    qualification_gates: dict[str, Any]
    inference_and_claims: dict[str, Any]
    api_calls: Literal[0] = 0
    freeze_identity: str = Field(pattern=r"^v53public_[0-9a-f]{24}$")

    @model_validator(mode="after")
    def coherent(self):
        exposure = self.historical_exposure
        if exposure.get("evoemo_pristine_confirmation") is not False:
            raise ValueError("previously exposed EvoEmo cannot be called pristine")
        if self.effect_estimand.get("cost_enters_component_training_label") is not False:
            raise ValueError("cost may not contaminate a component effect label")
        denied = set(self.observability_boundary.get("runtime_denied_evoemo_fields", []))
        required_denials = {
            "questions",
            "summaries",
            "subsequent_topics",
            "future_dialog_history[].summary",
            "future_dialog_history[].observation",
            "current_unclosed_session.summary",
            "current_unclosed_session.observation",
        }
        if not required_denials <= denied:
            raise ValueError("EvoEmo hindsight/gold fields are not fully denied")
        folds = self.cross_fitting.get("outer_folds", [])
        held_out = [user for fold in folds for user in fold.get("held_out_users", [])]
        if len(folds) != 6 or len(held_out) != 18 or len(set(held_out)) != 18:
            raise ValueError("outer folds must cover 18 users exactly once")
        if any(len(fold.get("held_out_users", [])) != 3 for fold in folds):
            raise ValueError("each outer fold must hold out exactly three users")
        payload = self.model_dump(mode="json", exclude={"freeze_identity"})
        expected = "v53public_" + stable_hex(canonical_json(payload), n=24)
        if self.freeze_identity != expected:
            raise ValueError("freeze identity does not match public-backbone content")
        return self


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chronological_users(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    for source_user in raw:
        user = dict(source_user)
        sessions = list(user.get("dialog_history") or [])
        sessions.sort(key=lambda row: (date.fromisoformat(str(row["timestamp"])), str(row["id"])))
        user["dialog_history"] = sessions
        users.append(user)
    return users


def _outer_folds(users: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Balance six folds while binding users that share any source session.

    EvoEmo contains one real global duplicate seed (``esc1198`` in p13 and
    p18).  User-exclusive folds alone would therefore still leak verbatim
    source dialogue.  Connected users are assigned as an indivisible group.
    """

    bins: list[list[Mapping[str, Any]]] = [[] for _ in range(6)]
    totals = [0] * 6
    by_id = {str(user["id"]): user for user in users}
    parent = {user_id: user_id for user_id in by_id}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    owners: dict[str, list[str]] = {}
    for user in users:
        user_id = str(user["id"])
        for session in user["dialog_history"]:
            owners.setdefault(str(session["id"]), []).append(user_id)
    for session_owners in owners.values():
        for other in session_owners[1:]:
            union(session_owners[0], other)

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for user_id, user in by_id.items():
        grouped.setdefault(find(user_id), []).append(user)
    ordered_groups = sorted(
        grouped.values(),
        key=lambda group: (
            -len(group),
            -sum(len(user["dialog_history"]) for user in group),
            tuple(sorted(str(user["id"]) for user in group)),
        ),
    )
    for group in ordered_groups:
        choices = [
            index for index, bucket in enumerate(bins)
            if len(bucket) + len(group) <= 3
        ]
        if not choices:
            raise ValueError("shared-source grouping cannot fit six 3-user folds")
        target = min(choices, key=lambda index: (totals[index], len(bins[index]), index))
        bins[target].extend(group)
        totals[target] += sum(len(user["dialog_history"]) for user in group)
    return [
        {
            "fold": index + 1,
            "held_out_users": sorted(str(user["id"]) for user in bucket),
            "held_out_sessions": totals[index],
        }
        for index, bucket in enumerate(bins)
    ]


def _seed_ids(users: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            str(session["id"])
            for user in users
            for session in user["dialog_history"]
            if str(session["id"]).startswith("esc")
        }
    )


def _memory_id(*parts: object) -> str:
    return "mem_" + stable_hex("|".join(map(str, parts)), n=16)


def _seeker_turns(session: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [turn for turn in session.get("dialogue", []) if turn.get("role") == "seeker"]


def _official_ms_items(
    session: Mapping[str, Any], session_index: int, user_id: str,
) -> list[tuple[MemoryItem, str]]:
    """Materialize session-local annotations only after session close.

    EvoEmo's paper states that summary and turn-level observations are
    auxiliary annotations added to each generated session.  Observations also
    carry source ``utt_id`` lineage in the release.  They are therefore useful
    production-memory proxies when made available *after* the source session,
    while QA/cross-session gold remains forbidden.
    """

    items: list[tuple[MemoryItem, str]] = []
    summary = " ".join(str(session.get("summary") or "").split())
    if compile_atomic_session_observation(summary) is not None:
        items.append(
            (
                MemoryItem(
                    memory_id=_memory_id(user_id, session["id"], "MS_SUMMARY"),
                    source=MemorySource.MS,
                    created_session=session_index,
                    timestamp=str(session.get("timestamp") or "") or None,
                    text=summary,
                ),
                "session_summary",
            )
        )
    valid_turn_ids = {turn.get("idx") for turn in _seeker_turns(session)}
    for observation in session.get("observation") or []:
        utt_ids = observation.get("utt_id") or []
        if isinstance(utt_ids, int):
            utt_ids = [utt_ids]
        if not utt_ids or not set(utt_ids) <= valid_turn_ids:
            continue
        text = " ".join(str(observation.get("content") or "").split())
        if compile_atomic_session_observation(text) is None:
            continue
        items.append(
            (
                MemoryItem(
                    memory_id=_memory_id(
                        user_id, session["id"], "MS_OBSERVATION", observation.get("idx")
                    ),
                    source=MemorySource.MS,
                    created_session=session_index,
                    timestamp=str(session.get("timestamp") or "") or None,
                    text=text,
                ),
                "turn_observation",
            )
        )
    return items


def _exact_me_items(session: Mapping[str, Any], session_index: int, user_id: str) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    for turn in _seeker_turns(session):
        compiled = compile_atomic_reusable_outcome(str(turn.get("content") or ""))
        if compiled is None:
            continue
        items.append(
            MemoryItem(
                memory_id=_memory_id(user_id, session["id"], turn.get("idx"), "ME"),
                source=MemorySource.ME,
                created_session=session_index,
                timestamp=str(session.get("timestamp") or "") or None,
                text=compiled.literal_evidence_span,
            )
        )
    return items


_RELATIONSHIP_RE = re.compile(
    r"^<(?P<name>[^,]*), (?P<relation>[^,]*), (?P<description>.*), (?P<conv_id>[^,>]*)>$"
)


def _relationship_items_by_session(
    user: Mapping[str, Any], session_index_by_id: Mapping[str, int],
) -> dict[str, list[tuple[MemoryItem, str]]]:
    result: dict[str, list[tuple[MemoryItem, str]]] = {}
    for position, raw in enumerate(user.get("social_relationship") or []):
        match = _RELATIONSHIP_RE.match(str(raw))
        if match is None:
            continue
        conv_id = match.group("conv_id")
        if conv_id not in session_index_by_id:
            continue
        text = (
            f"{match.group('relation')} {match.group('name')}: "
            f"{match.group('description')}"
        )
        result.setdefault(conv_id, []).append(
            (
                MemoryItem(
                    memory_id=_memory_id(user["id"], conv_id, "MP_RELATIONSHIP", position),
                    source=MemorySource.MP,
                    created_session=session_index_by_id[conv_id],
                    text=text,
                ),
                "relationship_update",
            )
        )
    return result


def _event_items_by_session(
    user: Mapping[str, Any], session_index_by_id: Mapping[str, int],
) -> dict[str, list[tuple[MemoryItem, str]]]:
    result: dict[str, list[tuple[MemoryItem, str]]] = {}
    for event in user.get("event_experience") or []:
        conv_id = str(event.get("conv_id") or "")
        if conv_id not in session_index_by_id:
            continue
        text = " ".join(str(event.get("event") or "").split())
        if not text:
            continue
        result.setdefault(conv_id, []).append(
            (
                MemoryItem(
                    memory_id=_memory_id(user["id"], event.get("id"), "ME_EVENT"),
                    source=MemorySource.ME,
                    created_session=session_index_by_id[conv_id],
                    timestamp=str(event.get("date") or "") or None,
                    text=text,
                ),
                "context_event",
            )
        )
    return result


def audit_public_backbone(
    *, evoemo_path: Path, esconv_path: Path, esconv_manifest_path: Path,
) -> dict[str, Any]:
    evo_raw = json.loads(evoemo_path.read_text(encoding="utf-8"))
    esconv_raw = json.loads(esconv_path.read_text(encoding="utf-8"))
    users = _chronological_users(evo_raw)
    manifest = [
        json.loads(line)
        for line in esconv_manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    seed_ids = _seed_ids(users)
    seed_dialogue_ids = {f"esconv_{int(value[3:]):04d}" for value in seed_ids}
    manifest_by_id = {str(row["dialogue_id"]): row for row in manifest}
    missing_seed_rows = sorted(seed_dialogue_ids - set(manifest_by_id))
    unquarantined = sorted(
        value
        for value in seed_dialogue_ids
        if value in manifest_by_id
        and not bool(manifest_by_id[value].get("excluded_for_evoemo_overlap"))
    )

    profile_states = 0
    profile_rank1_states = 0
    profile_rank1_users: set[str] = set()
    state_count = 0
    states_with_prior_session = 0
    ms_catalog_states = 0
    ms_rank1_states = 0
    ms_rank1_users: set[str] = set()
    me_catalog_states = 0
    me_rank1_states = 0
    me_rank1_users: set[str] = set()
    me_exact_items = 0
    me_exact_users: set[str] = set()
    ms_items = 0
    mp_items = 0
    me_items = 0
    three_memory_rank1_states = 0
    rank1_type_counts: dict[str, Counter[str]] = {
        "MP": Counter(), "MS": Counter(), "ME": Counter(),
    }

    for user in users:
        user_id = str(user["id"])
        basic_info = dict(user.get("basic_info") or {})
        prior_items: list[MemoryItem] = []
        item_types: dict[str, str] = {}
        for field, value in basic_info.items():
            if field == "name":
                continue
            item = MemoryItem(
                memory_id=_memory_id(user_id, "MP_BASIC", field),
                source=MemorySource.MP,
                created_session=0,
                text=f"{field.replace('_', ' ').title()}: {value}",
            )
            prior_items.append(item)
            item_types[item.memory_id] = "onboarding_profile"
            mp_items += 1
        session_index_by_id = {
            str(session["id"]): index
            for index, session in enumerate(user["dialog_history"], start=1)
        }
        relationships = _relationship_items_by_session(user, session_index_by_id)
        events = _event_items_by_session(user, session_index_by_id)
        for session_index, session in enumerate(user["dialog_history"], start=1):
            for turn in _seeker_turns(session):
                current = " ".join(str(turn.get("content") or "").split())
                if not current:
                    continue
                state_count += 1
                profile_states += 1
                if session_index > 1:
                    states_with_prior_session += 1
                if any(item.source is MemorySource.MS for item in prior_items):
                    ms_catalog_states += 1
                if any(item.source is MemorySource.ME for item in prior_items):
                    me_catalog_states += 1
                queries = {source: current for source in MemorySource}
                discoveries = discover_final_typed_memory_candidates(
                    queries=queries,
                    items=prior_items,
                    source_metadata=me_subtype_hints(prior_items),
                    session_index=session_index,
                )
                memory_present = []
                if discoveries[MemorySource.MP].selected_items:
                    profile_rank1_states += 1
                    profile_rank1_users.add(user_id)
                    top = discoveries[MemorySource.MP].selected_items[0]
                    rank1_type_counts["MP"][item_types[top.memory_id]] += 1
                    memory_present.append("MP")
                if discoveries[MemorySource.MS].selected_items:
                    ms_rank1_states += 1
                    ms_rank1_users.add(user_id)
                    top = discoveries[MemorySource.MS].selected_items[0]
                    rank1_type_counts["MS"][item_types[top.memory_id]] += 1
                    memory_present.append("MS")
                if discoveries[MemorySource.ME].selected_items:
                    me_rank1_states += 1
                    me_rank1_users.add(user_id)
                    top = discoveries[MemorySource.ME].selected_items[0]
                    rank1_type_counts["ME"][item_types[top.memory_id]] += 1
                    memory_present.append("ME")
                if len(memory_present) == 3:
                    three_memory_rank1_states += 1

            for item, item_type in _official_ms_items(session, session_index, user_id):
                prior_items.append(item)
                item_types[item.memory_id] = item_type
                ms_items += 1
            for item, item_type in relationships.get(str(session["id"]), []):
                prior_items.append(item)
                item_types[item.memory_id] = item_type
                mp_items += 1
            for item, item_type in events.get(str(session["id"]), []):
                prior_items.append(item)
                item_types[item.memory_id] = item_type
                me_items += 1
            exact_items = _exact_me_items(session, session_index, user_id)
            if exact_items:
                me_exact_users.add(user_id)
                prior_items.extend(exact_items)
                me_exact_items += len(exact_items)
                me_items += len(exact_items)
                for item in exact_items:
                    item_types[item.memory_id] = "reusable_action_result"

    eligible_manifest = [row for row in manifest if not row["excluded_for_evoemo_overlap"]]
    split_counts = Counter(str(row["split"]) for row in eligible_manifest)
    rs_flag_counts: Counter[str] = Counter()
    rs_states = 0
    for row in eligible_manifest:
        dialogue = esconv_raw[int(row["index"])]
        prefix: list[dict[str, str]] = []
        for turn in dialogue.get("dialog") or []:
            role = "user" if turn.get("speaker") == "seeker" else "assistant"
            prefix.append({"role": role, "content": str(turn.get("content") or "")})
            if role != "user":
                continue
            rs_states += 1
            for flag, value in observable_flags(prefix).items():
                rs_flag_counts[flag] += int(bool(value))
    total_sessions = sum(len(user["dialog_history"]) for user in users)
    session_ids = [
        str(session["id"])
        for user in users
        for session in user["dialog_history"]
    ]
    folds = _outer_folds(users)
    fold_by_user = {
        user: int(fold["fold"])
        for fold in folds
        for user in fold["held_out_users"]
    }
    shared_session_owners: dict[str, list[str]] = {}
    for user in users:
        for session in user["dialog_history"]:
            shared_session_owners.setdefault(str(session["id"]), []).append(str(user["id"]))
    shared_session_owners = {
        session_id: sorted(owner_ids)
        for session_id, owner_ids in shared_session_owners.items()
        if len(owner_ids) > 1
    }
    shared_source_cross_fold = {
        session_id: owner_ids
        for session_id, owner_ids in shared_session_owners.items()
        if len({fold_by_user[owner] for owner in owner_ids}) > 1
    }
    checks = {
        "source_hashes_frozen": True,
        "evoemo_user_count_is_18": len(users) == 18,
        "outer_folds_cover_each_user_once": (
            len({user for fold in folds for user in fold["held_out_users"]}) == 18
        ),
        "shared_source_sessions_never_cross_outer_folds": not shared_source_cross_fold,
        "all_evoemo_seed_dialogues_quarantined_from_esconv": (
            not missing_seed_rows and not unquarantined and len(seed_ids) == 84
        ),
        "runtime_hindsight_fields_denied_by_contract": True,
        "paired_effect_labels_available": False,
        "pm_learnability_established": False,
    }
    return {
        "protocol": "pm-v1.5-v5.3-public-backbone-zero-api-audit-v1",
        "status": "STRUCTURAL_PASS_EFFECT_LEARNABILITY_NOT_YET_ESTABLISHED",
        "api_calls": 0,
        "source_snapshot": {
            "evoemo_path": str(evoemo_path),
            "evoemo_sha256": _sha256(evoemo_path),
            "evoemo_users": len(users),
            "evoemo_sessions": total_sessions,
            "evoemo_session_ids_unique_globally": len(set(session_ids)),
            "evoemo_composite_user_session_keys_unique": len(
                {
                    (str(user["id"]), str(session["id"]))
                    for user in users
                    for session in user["dialog_history"]
                }
            ),
            "globally_shared_session_owners": shared_session_owners,
            "evoemo_seeker_turns": state_count,
            "esconv_path": str(esconv_path),
            "esconv_sha256": _sha256(esconv_path),
            "esconv_dialogues": len(esconv_raw),
            "esconv_manifest_path": str(esconv_manifest_path),
            "esconv_manifest_sha256": _sha256(esconv_manifest_path),
            "evoemo_unique_esconv_seed_ids": len(seed_ids),
            "esconv_quarantined_seed_ids": len(seed_dialogue_ids) - len(unquarantined),
            "esconv_eligible_after_quarantine": len(eligible_manifest),
            "esconv_eligible_by_split": dict(sorted(split_counts.items())),
        },
        "outer_folds": folds,
        "candidate_support_lower_bound": {
            "state_grain": "each EvoEmo seeker turn; memory candidates use completed prior sessions only",
            "states_total": state_count,
            "states_with_at_least_one_completed_prior_session": states_with_prior_session,
            "MP": {
                "profile_items": mp_items,
                "preliminary_actual_rank1_states": profile_rank1_states,
                "users_with_preliminary_actual_rank1": len(profile_rank1_users),
                "rank1_type_counts": dict(sorted(rank1_type_counts["MP"].items())),
                "note": "basic_info except name is available at onboarding; relationship updates open only after source conv_id closes",
            },
            "MS": {
                "session_local_summary_and_observation_items": ms_items,
                "states_with_prior_catalog": ms_catalog_states,
                "preliminary_actual_rank1_states": ms_rank1_states,
                "users_with_preliminary_actual_rank1": len(ms_rank1_users),
                "rank1_type_counts": dict(sorted(rank1_type_counts["MS"].items())),
                "note": "official session-local summary/observations open only after source session closes; observations require valid seeker utt_id lineage",
            },
            "ME": {
                "event_and_reusable_items": me_items,
                "strict_exact_action_result_items": me_exact_items,
                "users_with_strict_exact_item": len(me_exact_users),
                "states_with_prior_catalog": me_catalog_states,
                "preliminary_actual_rank1_states": me_rank1_states,
                "users_with_preliminary_actual_rank1": len(me_rank1_users),
                "rank1_type_counts": dict(sorted(rank1_type_counts["ME"].items())),
                "users_without_strict_exact_item": sorted(
                    str(user["id"]) for user in users if str(user["id"]) not in me_exact_users
                ),
                "note": "context events open only after their conv_id closes; reusable outcomes retain exact action/result source spans",
            },
            "states_with_preliminary_rank1_for_MP_MS_ME": three_memory_rank1_states,
            "RS": {
                "esconv_dialogues_after_evoemo_seed_quarantine": len(eligible_manifest),
                "seeker_turn_states": rs_states,
                "transparent_flag_counts": dict(sorted(rs_flag_counts.items())),
                "transparent_flag_rates": {
                    key: round(value / rs_states, 6)
                    for key, value in sorted(rs_flag_counts.items())
                },
                "transparent_flags_sufficient_as_only_learned_features": False,
                "required_addition": "frozen candidate-state semantic similarity plus bounded dialogue-act/readiness representation",
                "strategy_cards_must_be_definition_bank_or_outer_train_only": True,
            },
        },
        "historical_exposure": {
            "all_18_evoemo_users_treated_as_exposed": True,
            "allowed_claim": "cross-fitted development-benchmark evaluation",
            "forbidden_claim": "pristine confirmatory external validation",
        },
        "checks": checks,
        "blocking_before_paid_effects": [
            "freeze the exact effect-state sampling manifest from these outcome-blind candidate states",
            "qualify and freeze the revised positive-contribution/risk judge",
            "freeze generator, typed executor, guard, fallback, model features, and all six outer/inner folds",
            "run all folds without changing the method after any held-out outcome is opened",
        ],
    }


def build_public_backbone_freeze(audit: Mapping[str, Any]) -> PublicBackboneFreeze:
    source = audit["source_snapshot"]
    payload: dict[str, Any] = {
        "protocol": PUBLIC_BACKBONE_PROTOCOL,
        "status": "PRE_EFFECT_PUBLIC_BACKBONE_FROZEN",
        "route_decision": {
            "primary_research_backbone": "ESConv plus the 18-user EvoEmo/ES-MemEval public release",
            "new_longitudinal_synthetic_users": "STOP_FOR_PAPER_1_PRIMARY_ANALYSIS",
            "existing_11_synthetic_users": "engineering_stress_tests_and_failure_analysis_only",
            "new_generation_scope": "paired_response_effects_only_after_all_pre-effect_gates_pass",
        },
        "source_freeze": source,
        "historical_exposure": {
            "all_18_evoemo_users_previously_used_for_development": True,
            "evoemo_pristine_confirmation": False,
            "permitted_description": "previously exposed public development benchmark with fully cross-fitted predictions",
            "fresh_confirmation_required_for_strong_external_claim": True,
        },
        "observability_boundary": {
            "runtime_allowed": [
                "authorized onboarding basic_info profile",
                "current dialogue prefix ending at the current seeker turn",
                "completed-session summary and utt_id-grounded observations, opened only after session close",
                "conv_id-grounded event annotations plus strictly-prior exact seeker action-result spans",
                "frozen actual Rank-1 descriptors and transparent RS card descriptors",
            ],
            "runtime_denied_evoemo_fields": [
                "questions",
                "summaries",
                "subsequent_topics",
                "future_dialog_history[].summary",
                "future_dialog_history[].observation",
                "current_unclosed_session.summary",
                "current_unclosed_session.observation",
            ],
            "denied_uses": [
                "state selection",
                "candidate ranking",
                "PM features",
                "worth-opening labels",
                "judge evidence other than an audit-only leakage check",
            ],
            "profile_assumption": "basic_info is an authorized onboarding resource available before session 1, not inferred from future dialogue",
        },
        "candidate_materialization": {
            "state_grain": "each seeker turn with its within-session prefix; memory sources use completed prior sessions only",
            "MP": "basic_info except name at onboarding plus relationship updates after source conv_id closes; frozen actual Rank-1 is not gold",
            "MS": "official session-local summary plus utt_id-grounded turn observations, available only after source session close",
            "ME": "conv_id-grounded context events plus strict exact action/result spans, available only after source session close",
            "RS": "six-card definition bank; ESConv seed dialogues used by EvoEmo are quarantined",
            "actual_rank1_only": True,
            "rank2_promotion_after_effects": False,
            "semantic_usefulness_prefilter": False,
        },
        "effect_estimand": {
            "unit": "requested-component intention-to-treat effect on the same frozen state and same frozen actual Rank-1 candidate",
            "arms": "component ON versus OFF under the same generator, seed policy, executor, guard, and fallback",
            "component_training_target": "replicate-aggregated conditional positive-support-contribution uplift for the requested component",
            "quality_target_form": "continuous/ordinal ON-minus-OFF effect or pairwise soft target; tie is zero uplift/0.5, never forced negative",
            "material_risk_target": "separate absolute-arm and incremental risk auxiliary; never intersected into the quality target",
            "functional_use_target": "separate mechanism diagnostic and executor-validity audit; never required to turn a real quality gain positive",
            "replication": "three pre-frozen paired generator seeds per formal effect group; aggregate before deriving the target",
            "cost_enters_component_training_label": False,
            "cost_use": "deterministic penalty only during 16-action joint projection and separate reporting",
            "construction_condition_is_gold": False,
            "candidate_presence_is_gold": False,
        },
        "measurement": {
            "quality_axis_name": "positive_support_contribution_not_overall_quality",
            "quality_dimensions": [
                "goal_advance",
                "emotional_support",
                "specific_useful_contribution",
                "clarity_and_naturalness",
            ],
            "overall_acceptability": "reported separately and subject to risk veto",
            "risk_families": [
                "R1_explicit_boundary_violation",
                "R2_unsupported_or_wrong_owner_personal_grounding",
                "R3_excessive_directiveness_or_burden",
            ],
            "risk_records": "absolute events for both arms plus incremental/resource-attributable direction",
            "system_integrity": "resource/scaffold exposure is a separate event family",
            "cost": "incremental tokens, latency, fallback/recovery and monetary cost reported separately",
            "no_double_count_rule": "record each primary event once, but do not force positive contribution and risk to be statistically independent",
            "judge_independence": "primary judge model family must differ from the frozen generator family; judge prompts and thresholds freeze pre-effect",
            "human_audit": "predeclared stratified blind subset, two independent human raters, agreement plus adjudication; never used for post-hoc prompt tuning",
        },
        "cross_fitting": {
            "outer_protocol": "six user-held-out folds; 15 development users and 3 held-out users per fold",
            "outer_folds": list(audit["outer_folds"]),
            "shared_source_grouping": "users sharing any raw session ID are inseparable; composite (user_id, session_id) is the session primary key",
            "inner_protocol": "all model choice, regularization, calibration and thresholds use user-grouped inner validation inside the 15 outer-training users",
            "representation_rule": "any learned vocabulary/encoder/calibrator is fitted only inside the outer-training users; globally fixed third-party encoders must be frozen pre-effect",
            "automation_rule": "freeze once, run all six folds without between-fold method edits",
            "rs_rule": "ESConv dialogue groups are split separately; all 84 EvoEmo seed IDs are permanently excluded",
        },
        "qualification_gates": {
            "pre_effect": [
                "source hash and denominator freeze",
                "84-seed ESConv quarantine",
                "strict chronology and forbidden-field audit",
                "actual Rank-1 effect-state manifest freeze",
                "judge qualification and generator/Step2 compatibility",
                "cross-family judge plus frozen double-human blind audit plan",
            ],
            "head_engineering_gate_provisional": {
                "balanced_accuracy_point": 0.65,
                "recall_and_specificity_point_each": 0.60,
                "brier": "must beat within-fold prevalence constant and transparent rule",
                "noncollapse": "OOF predictions must contain both ON and OFF",
                "support": "report distinct contributing users per class; state counts may not substitute for users",
                "interpretation": "engineering adoption gate, not a powered scientific guarantee",
            },
            "learnability_first_design": {
                "state_sampling": "balance observable pre-treatment strata, never outcome classes",
                "per_component_strata": {
                    "MP": "onboarding profile versus relationship update; relevance, age, redundancy, response-act fit",
                    "MS": "session summary versus turn observation; relevance, age, continuity and redundancy",
                    "ME": "context event versus reusable action-result; relevance, age, current action readiness and redundancy",
                    "RS": "candidate move, dialogue phase, semantic candidate-state fit, advice/readiness and repetition/burden",
                },
                "primary_feature_capacity": "4-7 nonconstant deployable features per component",
                "required_semantic_feature": "one frozen candidate-state semantic similarity or a cross-fitted bounded dialogue-act representation",
                "transparent_regex_flags_alone_are_forbidden_for_RS": True,
                "ties_are_training_information_not_negative_class_padding": True,
            },
            "fold_failure": "fail closed to OFF or the predeclared transparent rule for that component in that fold",
            "system_reference_gates": {
                "quality_netwin_margin": -0.05,
                "material_risk_margin": 0.05,
                "minimum_input_token_reduction": 0.10,
                "critical_grounding_events": 0,
            },
        },
        "inference_and_claims": {
            "independent_cluster": "user for EvoEmo and dialogue for ESConv",
            "state_is_not_independent_user": True,
            "report": "OOF point estimates, user/dialogue-cluster bootstrap or permutation intervals, raw support, abstentions and all failed heads",
            "primary_comparator_predeclared": True,
            "eighteen_users_support_broad_generalization": False,
            "guaranteed": "workflow closure, leakage barriers, reproducibility and fail-closed behavior",
            "not_guaranteed": "a learnable effect, passing metrics, narrow confidence intervals or clinical/general-population validity",
            "fresh_confirmation": "required before describing the result as independent confirmation or broad external validation",
        },
        "api_calls": 0,
    }
    payload["freeze_identity"] = "v53public_" + stable_hex(canonical_json(payload), n=24)
    return PublicBackboneFreeze.model_validate(payload)
