#!/usr/bin/env python3
"""Freeze outcome-blind, high-support anchors for Rank-1-stable V5.4 V3 authoring."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-rank1-stable-anchor-authoring-v3-plan"
MANIFEST = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/effect_group_manifest_private.jsonl"
GATE = ROOT / "data/pm_v1_5_contracts/v5_4_fidelity_and_rank1_gate_v2.json"
FAILURE = ROOT / "outputs/pm_v1_5_v5_4_fidelity_failure_diagnosis_20260810/report.json"
RANK1 = ROOT / "outputs/pm_v1_5_v5_4_actual_rank1_recomputation_20260810/report.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_rank1_stable_authoring_v3_20260810"

COMPONENTS = ("MP", "MS", "ME", "RS")
SUBTYPE_QUOTAS = {
    "MP": {"relationship_update": 9, "onboarding_profile": 3},
    "MS": {"turn_observation": 8, "session_summary": 4},
    "ME": {"context_event": 8, "reusable_action_result": 4},
    "RS": {
        "AM01_invite_open_expression": 2,
        "AM02_ask_one_focused_clarification": 2,
        "AM04_tentative_paraphrase_check": 2,
        "AM05_grounded_validation": 2,
        "AM10_offer_one_optional_micro_step": 2,
        "AM14_supportive_transition": 2,
    },
}

HIGH = {
    "MP": "INCREMENTAL: the current user turn names the same central entity/topic but leaves one response-relevant personalization or constraint slot that the verified prior candidate can add without repetition",
    "MS": "INCREMENTAL: the current user turn names the same central entity/topic but leaves a genuine continuity gap that the verified prior observation can bridge",
    "ME": "INCREMENTAL: the current user turn names the same central entity/topic and presents a live option or concern whose framing can be changed by the verified prior episode or action-result",
    "RS": "INCREMENTAL: the current user turn creates a clear present opportunity for the selected card's one prospective assistant move; the user does not perform the assistant move",
}
LOW_TEXT = {
    "MP": {
        "ALREADY_VISIBLE": "ALREADY_VISIBLE: keep the same central entity/topic and request, but make the candidate's specific useful contribution already explicit in the current user turn, so reopening it would add no new personalization",
        "CURRENT_GOAL_UNRELATED": "CURRENT_GOAL_UNRELATED: keep the same central entity/topic cue but make the user's immediate response goal independent of the candidate's specific profile or relationship contribution",
    },
    "MS": {
        "ALREADY_VISIBLE": "ALREADY_VISIBLE: keep the same central entity/topic and request, but state the relevant prior observation explicitly enough that a continuity bridge would add no new information",
        "SELF_CONTAINED": "SELF_CONTAINED: keep the same central entity/topic but make the current turn fully self-contained, with no unresolved reference or continuity gap for the prior observation to bridge",
    },
    "ME": {
        "ALREADY_VISIBLE": "ALREADY_VISIBLE: keep the same central entity/topic and live option, but state the prior episode's relevant contribution explicitly so using it adds no new framing",
        "RESOLVED_OR_DECLINED": "RESOLVED_OR_DECLINED: keep the same central entity/topic cue but clearly resolve or decline the current option for which the prior episode could otherwise help",
    },
    "RS": {
        "FUNCTION_BOUNDARY": "FUNCTION_BOUNDARY: the current user naturally sets a present boundary incompatible with the selected prospective assistant move; do not claim the assistant move already occurred",
        "CURRENT_TURN_RESOLVES_MOVE_NEED": "CURRENT_TURN_RESOLVES_MOVE_NEED: the current user turn itself naturally resolves or removes the need for the selected prospective assistant move; do not write or impersonate the assistant move and do not claim it already occurred",
    },
}


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _cluster(row: dict[str, Any]) -> str:
    return str(row.get("user_id") or row.get("dialogue_id"))


def _score(row: dict[str, Any]) -> float:
    return float(row["model_features"]["candidate_state_bge_m3_cosine"])


def _select(rows: list[dict[str, Any]], component: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_clusters: set[str] = set()
    by_subtype: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_subtype[str(row["candidate_type"])].append(row)
    for subtype, quota in SUBTYPE_QUOTAS[component].items():
        candidates = sorted(
            by_subtype[subtype],
            key=lambda row: (
                _score(row),
                stable_hex(PROTOCOL, row["effect_group_id"], n=24),
            ),
            reverse=True,
        )
        distinct = [row for row in candidates if _cluster(row) not in used_clusters]
        repeated = [row for row in candidates if _cluster(row) in used_clusters]
        chosen = (distinct + repeated)[:quota]
        if len(chosen) != quota:
            raise RuntimeError(f"insufficient {component}/{subtype}")
        selected.extend(chosen)
        used_clusters.update(_cluster(row) for row in chosen)
    if len(selected) != 12:
        raise RuntimeError(f"{component} anchor count")
    return selected


def _low_mode(component: str, ordinal: int) -> str:
    modes = list(LOW_TEXT[component])
    return modes[(ordinal - 1) % len(modes)]


def main() -> None:
    gate = json.loads(GATE.read_text())
    failure = json.loads(FAILURE.read_text())
    rank1 = json.loads(RANK1.read_text())
    if not gate["authorization"]["outcome_blind_repair"]:
        raise RuntimeError("V3 repair is not authorized")
    if failure["status"] != "ROOT_CAUSES_FROZEN_V1_REMAINS_FAILED":
        raise RuntimeError("fidelity failure diagnosis not frozen")
    if rank1["status"] != "RANK1_DIAGNOSTIC_FAIL_AND_FIDELITY_BLOCKED":
        raise RuntimeError("Rank-1 failure diagnosis not frozen")

    manifest = _rows(MANIFEST)
    chosen: list[dict[str, Any]] = []
    for component in COMPONENTS:
        chosen.extend(_select([row for row in manifest if row["component"] == component], component))

    # Stable deterministic order makes author and high/low orientation exactly balanced.
    chosen.sort(key=lambda row: (COMPONENTS.index(str(row["component"])), stable_hex(PROTOCOL, row["effect_group_id"], n=24)))
    packet = []
    assignments = []
    anchor_audit = []
    for global_index, row in enumerate(chosen, start=1):
        component = str(row["component"])
        component_index = sum(1 for previous in chosen[:global_index] if previous["component"] == component)
        family_id = "v54v3sem_" + stable_hex(PROTOCOL, row["effect_group_id"], n=18)
        pair_id = "v54v3pair_" + stable_hex(PROTOCOL, family_id, n=18)
        visible = list(row["visible_dialogue"])
        if not visible or visible[-1]["role"] != "user" or visible[-1]["content"] != row["current_user_text"]:
            raise RuntimeError(f"{row['effect_group_id']} current user lineage mismatch")
        low_mode = _low_mode(component, component_index)
        low = LOW_TEXT[component][low_mode]
        incremental_is_A = (component_index % 2 == 1)
        endpoint = "anthropic_claude_haiku_4_5" if global_index % 2 == 1 else "openai_gpt_5_mini"
        instruction_A = HIGH[component] if incremental_is_A else low
        instruction_B = low if incremental_is_A else HIGH[component]
        base = {
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": family_id,
            "component": component,
            "assigned_author_endpoint": endpoint,
            "source_dataset": row["source_dataset"],
            "source_formal_effect_group_id": row["effect_group_id"],
            "source_state_id": row["state_id"],
            "user_id": row.get("user_id"),
            "session_id": row.get("session_id"),
            "turn_id": row.get("turn_id"),
            "dialogue_id": row.get("dialogue_id"),
            "candidate_subtype": row["candidate_type"],
            "frozen_candidate": row["candidate"],
            "frozen_candidate_text": row["candidate_text"],
            "exact_public_source_visible_prefix_locked": visible[:-1],
            "original_current_user_turn_for_world_and_tone_only": row["current_user_text"],
            "variant_A_private_instruction": instruction_A,
            "variant_B_private_instruction": instruction_B,
            "shared_retrieval_stability_requirement": "Both alternatives must naturally retain the same central entity/topic cue that connects the original current turn to the frozen candidate. Do not copy the full candidate. Rank-1 identity will be checked mechanically before acceptance.",
            "retrieval_query_boundary": "MP/MS/ME use current user turn only; RS uses recent locked prefix plus current user turn",
            "source_candidate_bge_m3_cosine_selection_diagnostic": _score(row),
            "world_fidelity_union": "locked prefix + original public current turn + verified prior candidate",
            "paired_response_effect_or_oracle_outcome_visible": False,
            "authoring_attempt_may_be_retried_only_on_machine_or_rank1_failure_before_any_outcome": True,
        }
        packet.append(base)
        assignments.append({
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": family_id,
            "component": component,
            "low_mode": low_mode,
            "variant_A_assignment": "INCREMENTAL" if incremental_is_A else "LOW_OPPORTUNITY",
            "variant_B_assignment": "LOW_OPPORTUNITY" if incremental_is_A else "INCREMENTAL",
            "exclude_from_pm_features_generator_effect_judges_and_oracle": True,
            "construction_assignment_is_not_value_gold": True,
        })
        anchor_audit.append({
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "component": component,
            "candidate_subtype": row["candidate_type"],
            "independent_cluster_id": _cluster(row),
            "source_candidate_bge_m3_cosine_selection_diagnostic": _score(row),
            "source_formal_effect_group_id": row["effect_group_id"],
            "selection_read_response_or_effect_outcome": False,
        })

    checks = {
        "48_pairs": len(packet) == 48,
        "12_per_component": Counter(row["component"] for row in packet) == Counter({key: 12 for key in COMPONENTS}),
        "24_per_author": Counter(row["assigned_author_endpoint"] for row in packet) == Counter({"anthropic_claude_haiku_4_5": 24, "openai_gpt_5_mini": 24}),
        "6_incremental_A_and_6_incremental_B_per_component": all(
            sum(row["variant_A_assignment"] == "INCREMENTAL" for row in assignments if row["component"] == component) == 6
            for component in COMPONENTS
        ),
        "removed_rs_move_already_performed": all(row["low_mode"] != "MOVE_ALREADY_PERFORMED" for row in assignments),
        "source_manifest_only_no_result_file_read": True,
        "all_outcomes_hidden": all(not row["paired_response_effect_or_oracle_outcome_visible"] for row in packet),
    }
    if not all(checks.values()):
        raise RuntimeError(f"V3 plan checks failed: {checks}")
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "authoring_v3_packet_private_outcome_blind.jsonl", packet)
    write_jsonl(OUT / "construction_assignment_private_do_not_join.jsonl", assignments)
    write_jsonl(OUT / "anchor_selection_audit_outcome_blind.jsonl", anchor_audit)
    report = {
        "protocol": PROTOCOL,
        "status": "V3_RANK1_STABLE_AUTHORING_PLAN_FROZEN_ZERO_API",
        "checks": checks,
        "component_minimum_bge_selection_diagnostic": {
            component: min(row["source_candidate_bge_m3_cosine_selection_diagnostic"] for row in packet if row["component"] == component)
            for component in COMPONENTS
        },
        "component_cluster_counts": {
            component: len({row["independent_cluster_id"] for row in anchor_audit if row["component"] == component})
            for component in COMPONENTS
        },
        "outcome_blind_retry_rule": "An authored pair may be retried only for frozen surface, fidelity-construction, or exact Rank-1 identity failures before any response/effect/oracle outcome exists. Every attempt remains in the ledger.",
        "response_effect_calls": 0,
        "api_calls": 0,
        "source_hashes": {
            "manifest": sha256_file(MANIFEST),
            "gate_v2": sha256_file(GATE),
            "failure_diagnosis": sha256_file(FAILURE),
            "rank1_diagnosis": sha256_file(RANK1),
        },
    }
    write_json(OUT / "plan_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
