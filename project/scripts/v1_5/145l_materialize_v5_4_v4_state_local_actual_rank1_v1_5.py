#!/usr/bin/env python3
"""Materialize one production actual Rank-1 for each completed V4 state."""

from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-v4-state-local-actual-rank1-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810"
PACKET = DIR / "authoring_v4_packet_private_outcome_blind.jsonl"
AUTHORED_ORIGINAL = DIR / "authored_pairs_v4_outcome_blind.jsonl"
AUTHORED_REPAIRED = DIR / "authored_pairs_v4_after_rank1_repair_outcome_blind.jsonl"
AUTHORED_FIDELITY_REPAIRED = DIR / "authored_pairs_v4_after_fidelity_repair_outcome_blind.jsonl"
ASSIGNMENT = DIR / "construction_assignment_private_do_not_join.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_state_local_rank1_factorial_oracle_v1.json"
EVOEMO = ROOT / "data/external/evo_emo.json"
CARDS = ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl"
RANK1_IMPL = ROOT / "scripts/v1_5/140l_recompute_v5_4_authored_actual_rank1_v1_5.py"
OUT = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _implementation():
    spec = importlib.util.spec_from_file_location("v5_4_rank1_impl", RANK1_IMPL)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Rank-1 implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    authored_path = (
        AUTHORED_FIDELITY_REPAIRED if AUTHORED_FIDELITY_REPAIRED.exists()
        else AUTHORED_REPAIRED if AUTHORED_REPAIRED.exists()
        else AUTHORED_ORIGINAL
    )
    contract = json.loads(CONTRACT.read_text())
    if not contract["current_authorization"]["state_local_actual_rank1_materialization"]:
        raise RuntimeError("state-local Rank-1 not authorized")
    packet_rows = _rows(PACKET)
    packet = {row["pair_id"]: row for row in packet_rows}
    authored_rows = _rows(authored_path)
    authored = {row["pair_id"]: row for row in authored_rows}
    assignments = {row["pair_id"]: row for row in _rows(ASSIGNMENT)}
    if len(packet) != 48 or len(authored) != 48 or set(packet) != set(authored) or set(packet) != set(assignments):
        raise RuntimeError("V4 identities incomplete")

    impl = _implementation()
    users = {
        str(user["id"]): user
        for user in impl._chronological_users(json.loads(EVOEMO.read_text()))
    }
    cards = [impl.StrategyCard.model_validate(row) for row in _rows(CARDS)]
    private_rows = []
    runtime_rows = []
    family_rows = []
    for source in packet_rows:
        pair_id = source["pair_id"]
        pair = authored[pair_id]
        component = source["component"]
        variant_results = {}
        for variant in ("A", "B"):
            text = pair[f"variant_{variant}_current_user_turn"]
            if component == "RS":
                result = impl._rs_result(
                    prefix=source["exact_public_source_visible_prefix_locked"],
                    current_user_turn=text,
                    cards=cards,
                )
            else:
                result = impl._memory_result(
                    component=component,
                    query=text,
                    user_id=str(source["user_id"]),
                    current_session_id=str(source["session_id"]),
                    users=users,
                )
            variant_id = pair_id + "_" + variant.casefold()
            state_id = "v54v4state_" + stable_hex(PROTOCOL, variant_id, n=20)
            available = bool(result["candidate_available"] and result["typed_adapter_valid"])
            private_rows.append({
                "protocol": PROTOCOL,
                "state_id": state_id,
                "variant_id": variant_id,
                "pair_id": pair_id,
                "semantic_family_id": source["semantic_family_id"],
                "component": component,
                "variant": variant,
                "actual_rank1": result,
                "target_component_candidate_available_and_typed": available,
                "source_anchor_candidate_id_for_diagnostic_only": source["frozen_candidate"]["resource_id"],
                "source_anchor_candidate_retained_diagnostic_only": result["actual_rank1_resource_id"] == source["frozen_candidate"]["resource_id"],
                "candidate_identity_may_differ_across_states": True,
                "candidate_identity_must_be_frozen_within_state_action_arms": True,
                "construction_assignment_read_by_retriever": False,
                "response_effect_or_oracle_outcome_read": False,
            })
            visible = [
                *source["exact_public_source_visible_prefix_locked"],
                {"role": "user", "content": text},
            ]
            runtime_rows.append({
                "protocol": PROTOCOL,
                "state_id": state_id,
                "variant_id": variant_id,
                "pair_id": pair_id,
                "semantic_family_id": source["semantic_family_id"],
                "source_dataset": source["source_dataset"],
                "component": component,
                "visible_dialogue": visible,
                "current_user_text": text,
                "actual_rank1_candidate_text": result["actual_rank1_text_private"],
                "actual_rank1_typed_candidate": result["actual_rank1_typed_candidate_private"],
                "candidate_present": available,
                "candidate_id_present_in_pm_feature_surface": False,
                "construction_assignment_present": False,
                "response_effect_quality_risk_function_oracle_present": False,
                "action_arm_execution_status": "NOT_AUTHORIZED",
            })
            variant_results[variant] = result
        family_rows.append({
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": source["semantic_family_id"],
            "component": component,
            "A_candidate_present": variant_results["A"]["candidate_available"],
            "B_candidate_present": variant_results["B"]["candidate_available"],
            "A_B_same_candidate_diagnostic_only": variant_results["A"]["actual_rank1_resource_id"] == variant_results["B"]["actual_rank1_resource_id"],
            "cross_state_same_candidate_required": False,
            "both_states_candidate_available": variant_results["A"]["candidate_available"] and variant_results["B"]["candidate_available"],
            "eligible_for_fidelity_if_machine_gates_pass": variant_results["A"]["candidate_available"] and variant_results["B"]["candidate_available"],
            "eligible_for_effect": False,
        })

    summary = {}
    for component in ("MP", "MS", "ME", "RS"):
        variants = [row for row in private_rows if row["component"] == component]
        families = [row for row in family_rows if row["component"] == component]
        summary[component] = {
            "variants": len(variants),
            "candidate_available_and_typed": sum(row["target_component_candidate_available_and_typed"] for row in variants),
            "families_both_states_available": sum(row["both_states_candidate_available"] for row in families),
            "A_B_same_candidate_diagnostic_only": sum(row["A_B_same_candidate_diagnostic_only"] for row in families),
        }
    all_available = all(row["target_component_candidate_available_and_typed"] for row in private_rows)
    checks = {
        "96_states": len(private_rows) == len(runtime_rows) == 96,
        "24_states_per_component": Counter(row["component"] for row in private_rows) == Counter({key: 24 for key in ("MP", "MS", "ME", "RS")}),
        "all_target_component_candidates_available_and_typed": all_available,
        "runtime_has_no_candidate_ids": all(not row["candidate_id_present_in_pm_feature_surface"] for row in runtime_rows),
        "runtime_has_no_assignment_or_outcome": all(not row["construction_assignment_present"] and not row["response_effect_quality_risk_function_oracle_present"] for row in runtime_rows),
        "action_execution_not_authorized": all(row["action_arm_execution_status"] == "NOT_AUTHORIZED" for row in runtime_rows),
    }
    report = {
        "protocol": PROTOCOL,
        "status": "STATE_LOCAL_RANK1_MACHINE_PASS_AWAITING_FIDELITY" if all(checks.values()) else "STATE_LOCAL_RANK1_MACHINE_FAIL_REPLENISH_BEFORE_FIDELITY",
        "checks": checks,
        "component_summary": summary,
        "cross_state_same_candidate_is_diagnostic_not_gate": True,
        "response_effect_calls_authorized": False,
        "pm_training_authorized": False,
        "construction_assignment_read": False,
        "response_effect_or_oracle_outcome_read": False,
        "api_calls": 0,
        "source_hashes": {
            "packet": sha256_file(PACKET),
            "authored": sha256_file(authored_path),
            "authored_surface": str(authored_path.relative_to(ROOT)),
            "assignments": sha256_file(ASSIGNMENT),
            "contract": sha256_file(CONTRACT),
            "rank1_implementation": sha256_file(RANK1_IMPL),
            "evoemo": sha256_file(EVOEMO),
            "cards": sha256_file(CARDS),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "state_local_actual_rank1_private.jsonl", private_rows)
    write_jsonl(OUT / "runtime_state_candidate_surface_no_ids_no_assignment.jsonl", runtime_rows)
    write_jsonl(OUT / "family_candidate_availability_diagnostic.jsonl", family_rows)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
