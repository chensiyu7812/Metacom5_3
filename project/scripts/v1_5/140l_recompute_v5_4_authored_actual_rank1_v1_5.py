#!/usr/bin/env python3
"""Recompute production Rank-1 for the 96 authored V5.4 current turns.

The computation is outcome blind.  It first proves that the reconstruction
reproduces each public source anchor, then runs the same frozen lexical typed
memory selector (MP/MS/ME) or six-card RS selector on authored A and B turns.
No Rank-2 promotion is permitted.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.contracts import MemoryItem, MemorySource, StrategyCard  # noqa: E402
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_candidate_discovery import (  # noqa: E402
    discover_final_typed_memory_candidates,
)
from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate  # noqa: E402
from metacom_pm.v1_5_v5_2_atomic_memory import (  # noqa: E402
    compile_atomic_reusable_outcome,
    me_subtype_hints,
)
from metacom_pm.v1_5_v5_3_candidate_layer_responsibility import (  # noqa: E402
    rs_mechanical_candidate_pool,
    rs_shared_candidate_top1,
)
from metacom_pm.v1_5_v5_3_public_backbone import (  # noqa: E402
    _chronological_users,
    _event_items_by_session,
    _exact_me_items,
    _memory_id,
    _official_ms_items,
    _relationship_items_by_session,
)
from metacom_pm.v1_5_v5_3_public_learnability_pilot import (  # noqa: E402
    _memory_candidate_payload,
)


PROTOCOL = "pm-v1.5-v5.4-authored-actual-rank1-recomputation-v1"
AUTHOR_DIR = ROOT / "outputs/pm_v1_5_v5_4_source_prefix_locked_authoring_v2_20260810"
PAIRS = AUTHOR_DIR / "authored_pairs_source_prefix_locked_outcome_blind.jsonl"
PLAN = AUTHOR_DIR / "source_prefix_locked_authoring_packet_private.jsonl"
ANCHORS = ROOT / "outputs/pm_v1_5_v5_4_semantic_development_anchors_20260809/anchors_private.jsonl"
EVOEMO = ROOT / "data/external/evo_emo.json"
CARDS = ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl"
GATE = ROOT / "data/pm_v1_5_contracts/v5_4_fidelity_and_rank1_gate_v2.json"
FIDELITY = ROOT / "outputs/pm_v1_5_v5_4_fidelity_review_20260810/fidelity_agreement_report.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_actual_rank1_recomputation_20260810"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _text_hash(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _user_catalog_before_session(
    user: dict[str, Any], current_session_id: str,
) -> tuple[list[MemoryItem], dict[str, str], int]:
    """Rebuild exactly the public runtime catalog before current session."""

    user_id = str(user["id"])
    sessions = list(user["dialog_history"])
    session_index_by_id = {
        str(session["id"]): index
        for index, session in enumerate(sessions, start=1)
    }
    if current_session_id not in session_index_by_id:
        raise ValueError(f"unknown session {user_id}/{current_session_id}")
    current_index = session_index_by_id[current_session_id]
    prior: list[MemoryItem] = []
    item_types: dict[str, str] = {}
    for field, value in (user.get("basic_info") or {}).items():
        if field == "name":
            continue
        item = MemoryItem(
            memory_id=_memory_id(user_id, "MP_BASIC", field),
            source=MemorySource.MP,
            created_session=0,
            text=f"{field.replace('_', ' ').title()}: {value}",
        )
        prior.append(item)
        item_types[item.memory_id] = "onboarding_profile"

    relationships = _relationship_items_by_session(user, session_index_by_id)
    events = _event_items_by_session(user, session_index_by_id)
    for session_index, session in enumerate(sessions, start=1):
        if session_index >= current_index:
            break
        session_id = str(session["id"])
        for item, subtype in _official_ms_items(session, session_index, user_id):
            prior.append(item)
            item_types[item.memory_id] = subtype
        for item, subtype in relationships.get(session_id, []):
            prior.append(item)
            item_types[item.memory_id] = subtype
        for item, subtype in events.get(session_id, []):
            prior.append(item)
            item_types[item.memory_id] = subtype
        for item in _exact_me_items(session, session_index, user_id):
            prior.append(item)
            item_types[item.memory_id] = "reusable_action_result"
    return prior, item_types, current_index


def _memory_result(
    *, component: str, query: str, user_id: str, current_session_id: str,
    users: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    prior, item_types, current_index = _user_catalog_before_session(
        users[user_id], current_session_id,
    )
    source = MemorySource(component)
    discoveries = discover_final_typed_memory_candidates(
        queries={candidate_source: query for candidate_source in MemorySource},
        items=prior,
        source_metadata=me_subtype_hints(prior),
        session_index=current_index,
        ms_semantic_encoder=None,
    )
    discovery = discoveries[source]
    selected = list(discovery.selected_items)
    rank1 = selected[0] if selected else None
    typed_valid = False
    me_compiler_valid: bool | None = None
    subtype = item_types.get(rank1.memory_id) if rank1 else None
    payload: dict[str, Any] | None = None
    if rank1 is not None:
        payload = _memory_candidate_payload(
            component=component,
            item=rank1,
            subtype=str(subtype),
            user_id=user_id,
            current_session_index=current_index,
        )
        TypedResourceCandidate(**payload)
        typed_valid = True
        if component == "ME":
            me_compiler_valid = (
                compile_atomic_reusable_outcome(rank1.text) is not None
                if subtype == "reusable_action_result"
                else True
            )
    return {
        "query_surface": "CURRENT_USER_TURN_ONLY",
        "actual_rank1_resource_id": rank1.memory_id if rank1 else None,
        "actual_rank1_text_private": rank1.text if rank1 else None,
        "actual_rank1_typed_candidate_private": payload,
        "actual_rank1_text_sha256": _text_hash(rank1.text if rank1 else None),
        "actual_rank1_created_session": rank1.created_session if rank1 else None,
        "actual_rank1_subtype": subtype,
        "topk_resource_ids_audit_only": [item.memory_id for item in selected],
        "candidate_available": rank1 is not None,
        "owner_valid_by_same_user_catalog_construction": rank1 is not None,
        "strict_past_valid": bool(rank1 and rank1.created_session < current_index),
        "candidate_version": "v1" if rank1 else None,
        "typed_adapter_valid": typed_valid,
        "me_compiler_or_context_valid": me_compiler_valid,
        "top1_lexical_relevance_diagnostic": discovery.descriptor.get("top1_lexical_relevance"),
        "top1_top2_lexical_margin_diagnostic": discovery.descriptor.get("top1_top2_lexical_margin"),
        "selected_content_word_match_level": discovery.descriptor.get("selected_content_word_match_level"),
        "catalog_items_for_component": sum(item.source is source for item in prior),
        "outcome_read": False,
    }


def _rs_result(
    *, prefix: list[dict[str, str]], current_user_turn: str,
    cards: list[StrategyCard],
) -> dict[str, Any]:
    dialogue = [*prefix, {"role": "user", "content": current_user_turn}]
    pool = rs_mechanical_candidate_pool(recent_dialogue=dialogue, cards=cards)
    shared = rs_shared_candidate_top1(pool)
    if shared is None:
        return {
            "query_surface": "LOCKED_PREFIX_PLUS_CURRENT_USER_TURN_LAST_SIX_AT_RS_QUERY",
            "actual_rank1_resource_id": None,
            "actual_rank1_text_private": None,
            "actual_rank1_typed_candidate_private": None,
            "actual_rank1_text_sha256": None,
            "topk_resource_ids_audit_only": [],
            "candidate_available": False,
            "hard_off_reason": pool.hard_off_reason,
            "candidate_version": None,
            "typed_adapter_valid": False,
            "selected_lexical_relevance_diagnostic": None,
            "selection_mode": None,
            "outcome_read": False,
        }
    obs = shared.observation
    payload = {
        "component": "RS",
        "subtype": "RS_ATOMIC_MOVE",
        "resource_id": obs.strategy_card.strategy_id,
        "candidate_version": "v1",
        "source_kind": "strategy",
        "support_move": obs.strategy_card.guidance_text,
        "when_to_use": obs.strategy_card.retrieval_text,
        "when_not_to_use": "Follow the boundaries in the frozen card.",
    }
    TypedResourceCandidate(**payload)
    lexical_order = sorted(
        pool.candidates,
        key=lambda candidate: (candidate.lexical_relevance, candidate.move_id),
        reverse=True,
    )
    return {
        "query_surface": "LOCKED_PREFIX_PLUS_CURRENT_USER_TURN_LAST_SIX_AT_RS_QUERY",
        "actual_rank1_resource_id": obs.strategy_card.strategy_id,
        "actual_rank1_text_private": obs.strategy_card.guidance_text,
        "actual_rank1_typed_candidate_private": payload,
        "actual_rank1_text_sha256": _text_hash(obs.strategy_card.guidance_text),
        "topk_resource_ids_audit_only": [candidate.strategy_card.strategy_id for candidate in lexical_order],
        "candidate_available": True,
        "hard_off_reason": None,
        "candidate_version": "v1",
        "typed_adapter_valid": True,
        "selected_lexical_relevance_diagnostic": obs.lexical_relevance,
        "selection_mode": shared.selection_mode,
        "transparent_rule_on": shared.transparent_rule_on,
        "outcome_read": False,
    }


def main() -> None:
    gate = json.loads(GATE.read_text())
    fidelity = json.loads(FIDELITY.read_text())
    if not gate["authorization"]["production_rank1_diagnostic"]:
        raise RuntimeError("Rank-1 diagnostic not authorized")
    if fidelity["status"] != "FIDELITY_GATE_FAIL_NO_PROMOTION":
        raise RuntimeError("historical fidelity state changed unexpectedly")

    pairs = {row["semantic_family_id"]: row for row in _rows(PAIRS)}
    plans = {row["semantic_family_id"]: row for row in _rows(PLAN)}
    anchors = _rows(ANCHORS)
    if len(pairs) != 48 or len(plans) != 48 or set(pairs) != set(plans):
        raise RuntimeError("authoring identities incomplete")
    raw_users = json.loads(EVOEMO.read_text())
    users = {str(user["id"]): user for user in _chronological_users(raw_users)}
    cards = [StrategyCard.model_validate(row) for row in _rows(CARDS)]

    variant_rows = []
    family_rows = []
    for anchor in anchors:
        family_id = anchor["semantic_family_id"]
        pair = pairs[family_id]
        plan = plans[family_id]
        component = anchor["component"]
        frozen_id = str(anchor["candidate"]["resource_id"])
        prefix = list(plan["exact_public_source_visible_prefix_locked"])

        def recompute(text: str) -> dict[str, Any]:
            if component == "RS":
                return _rs_result(prefix=prefix, current_user_turn=text, cards=cards)
            return _memory_result(
                component=component,
                query=text,
                user_id=str(anchor["user_id"]),
                current_session_id=str(anchor["session_id"]),
                users=users,
            )

        original = recompute(str(plan["original_current_user_turn_for_world_and_tone_only"]))
        variants = {
            "A": recompute(str(pair["variant_A_current_user_turn"])),
            "B": recompute(str(pair["variant_B_current_user_turn"])),
        }
        for label, result in variants.items():
            result.update({
                "protocol": PROTOCOL,
                "pair_id": pair["pair_id"],
                "semantic_family_id": family_id,
                "component": component,
                "variant": label,
                "frozen_source_candidate_id": frozen_id,
                "frozen_source_candidate_retained": result["actual_rank1_resource_id"] == frozen_id,
                "private_assignment_read": False,
                "paired_response_or_effect_outcome_read": False,
            })
            variant_rows.append(result)
        same = variants["A"]["actual_rank1_resource_id"] == variants["B"]["actual_rank1_resource_id"]
        both_retained = all(
            variants[label]["actual_rank1_resource_id"] == frozen_id
            for label in ("A", "B")
        )
        family_rows.append({
            "protocol": PROTOCOL,
            "pair_id": pair["pair_id"],
            "semantic_family_id": family_id,
            "component": component,
            "frozen_source_candidate_id": frozen_id,
            "original_source_query_reproduced": original["actual_rank1_resource_id"] == frozen_id,
            "original_recomputed_rank1_id": original["actual_rank1_resource_id"],
            "variant_A_rank1_id": variants["A"]["actual_rank1_resource_id"],
            "variant_B_rank1_id": variants["B"]["actual_rank1_resource_id"],
            "A_B_same_rank1": same,
            "A_B_both_retain_frozen_source_candidate": both_retained,
            "eligible_for_effect_after_rank1_only": same and both_retained,
            "eligible_for_effect_overall": False,
            "overall_blocker": "FIDELITY_GATE_V1_FAILED_AND_FRESH_V2_NOT_RUN",
            "private_assignment_read": False,
            "paired_response_or_effect_outcome_read": False,
        })

    summaries: dict[str, dict[str, Any]] = {}
    for component in ("MP", "MS", "ME", "RS"):
        families = [row for row in family_rows if row["component"] == component]
        variants = [row for row in variant_rows if row["component"] == component]
        summaries[component] = {
            "families": len(families),
            "variants": len(variants),
            "candidate_available_variants": sum(row["candidate_available"] for row in variants),
            "original_source_query_reproduced_families": sum(row["original_source_query_reproduced"] for row in families),
            "A_B_same_rank1_families": sum(row["A_B_same_rank1"] for row in families),
            "A_B_both_retain_frozen_source_candidate_families": sum(row["A_B_both_retain_frozen_source_candidate"] for row in families),
            "rank1_gate_12_of_12": all(row["A_B_both_retain_frozen_source_candidate"] for row in families) and len(families) == 12,
            "shifted_or_absent_pair_ids": [row["pair_id"] for row in families if not row["A_B_both_retain_frozen_source_candidate"]],
        }
    original_all = all(row["original_source_query_reproduced"] for row in family_rows)
    rank1_all = all(summary["rank1_gate_12_of_12"] for summary in summaries.values())
    report = {
        "protocol": PROTOCOL,
        "status": "RANK1_DIAGNOSTIC_PASS_BUT_FIDELITY_BLOCKED" if rank1_all else "RANK1_DIAGNOSTIC_FAIL_AND_FIDELITY_BLOCKED",
        "production_route_reconstruction_validated_on_all_original_anchors": original_all,
        "component_summary": summaries,
        "all_components_rank1_gate": rank1_all,
        "memory_query_contract_correction": "The frozen V5.3 memory retriever consumes only the current user turn; it does not consume the public dialogue prefix. RS consumes recent dialogue including prefix and current turn.",
        "rank2_promotions": 0,
        "fidelity_v1_status": fidelity["status"],
        "effect_calls_authorized": False,
        "pm_training_authorized": False,
        "private_assignment_read": False,
        "paired_response_or_effect_outcome_read": False,
        "api_calls": 0,
        "source_hashes": {
            "pairs": sha256_file(PAIRS),
            "plan": sha256_file(PLAN),
            "anchors": sha256_file(ANCHORS),
            "evoemo": sha256_file(EVOEMO),
            "cards": sha256_file(CARDS),
            "gate_v2": sha256_file(GATE),
            "fidelity_v1": sha256_file(FIDELITY),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "variant_actual_rank1_private_outcome_blind.jsonl", variant_rows)
    write_jsonl(OUT / "family_rank1_stability_outcome_blind.jsonl", family_rows)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
