from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_component_general_v3_repair_contract_v1.json"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/pm_v1_5_paper1_component_general_v3_repair_contract_validation_20260811/report.json"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def validate() -> dict[str, Any]:
    contract = _read(CONTRACT)
    authority = _read(AUTHORITY)
    feasibility = authority["current_phase"]["system_feasibility_design_candidate"]
    binding = feasibility["component_general_v3_repair_contract"]
    plan_path = _resolve(contract["human_plan"]["path"])
    ledger_path = _resolve(contract["global_failure_ledger"]["path"])
    plan_text = plan_path.read_text(encoding="utf-8")
    ledger_text = ledger_path.read_text(encoding="utf-8")
    evidence_hashes_match = all(
        _sha(_resolve(row["path"])) == row["sha256"]
        for row in contract["historical_evidence"]
    )
    checks = {
        "protocol": contract["protocol"]
        == "pm-v1.5-paper1-component-general-v3-repair-contract-v1",
        "status_is_design_only": contract["status"]
        == "ZERO_API_DESIGN_FROZEN_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT",
        "authority_hash_binds_contract": binding["path"]
        == "data/pm_v1_5_contracts/paper1_component_general_v3_repair_contract_v1.json"
        and binding["sha256"] == _sha(CONTRACT)
        and binding["execution_authority"] is False,
        "git_baseline_frozen": contract["git_baseline"]["commit"] == "8337f15",
        "plan_hash_matches": _sha(plan_path) == contract["human_plan"]["sha256"],
        "ledger_hash_and_section_match": _sha(ledger_path)
        == contract["global_failure_ledger"]["sha256"]
        and contract["global_failure_ledger"]["required_section"] in ledger_text,
        "historical_v2_evidence_immutable": evidence_hashes_match,
        "success_requires_rs_plus_memory": contract["research_success"]["only_RS"]
        == "PAPER1_MEMORY_PM_PRIMARY_FAIL",
        "sixteen_requested_actions": contract["research_success"]["requested_action_count"]
        == 16,
        "mp_is_profile_only": contract["component_scope"]["MP"].startswith(
            "Profile-based Personalization only"
        )
        and {"MP_PREFERENCE", "candidate_is_preference", "preference_applies_to_response_act"}.issubset(
            set(contract["component_scope"]["forbidden"])
        ),
        "five_action_layers_exact": contract["action_accounting"]["layers"]
        == [
            "requested",
            "structurally_eligible",
            "jointly_planned",
            "generator_claimed",
            "offline_verified_functional",
        ],
        "single_suitability_not_independent_axes": contract["suitability_gold"][
            "independent_per_axis_agreement_gate_forbidden"
        ]
        is True
        and contract["suitability_gold"]["primary_decision"]
        == ["SUITABLE", "NOT_SUITABLE", "SEMANTIC_ABSTAIN"],
        "component_suitability_is_nonexclusive": contract["suitability_gold"][
            "components_may_all_be_suitable_in_the_same_state"
        ]
        is True
        and contract["suitability_gold"][
            "one_of_k_softmax_or_winner_take_all_forbidden"
        ]
        is True
        and "state by component" in contract["suitability_gold"]["decision_grain"],
        "all_six_component_pairs": set(contract["v3_executor"]["pair_rules_required"])
        == {"MP-MS", "MP-ME", "MP-RS", "MS-ME", "MS-RS", "ME-RS"},
        "one_primary_without_one_memory_cap": contract["v3_executor"]["response_budget"]
        == {
            "primary_acts": 1,
            "explicit_memory_contributions_max": 2,
            "global_one_memory_cap": False,
            "low_burden_invitations_max": 1,
            "MP_visible_act": False,
        }
        and contract["v3_executor"]["pre_outcome_joint_policy"][
            "preserve_all_requested_bits_when_structurally_eligible_and_no_hard_safety_veto"
        ]
        is True
        and contract["v3_executor"]["pre_outcome_joint_policy"][
            "unknown_redundant_or_conflicting_relation_automatically_suppresses_a_bit"
        ]
        is False,
        "no_literal_or_lexical_use_gate": contract["v3_executor"]["meaning_absorption"][
            "literal_mention_required"
        ]
        is False
        and contract["v3_executor"]["meaning_absorption"]["lexical_overlap_required"]
        is False,
        "safe_nonuse_preserved": contract["v3_executor"]["guard"][
            "fixed_generic_safe_nonuse_fallback_forbidden"
        ]
        is True
        and "Keep reply" in contract["v3_executor"]["guard"]["safe_nonuse"],
        "telemetry_not_function_gold": contract["measurement"]["generator_telemetry_is_not_gold"]
        is True,
        "q_r_f_cost_separate": contract["measurement"]["quality_risk_function_cost_separate"]
        is True,
        "mp_ms_parallel_me_sparse": contract["learning"]["parallel_primary_memory_candidates"]
        == ["MP_PROFILE", "MS"]
        and contract["learning"]["sparse_optional"] == "ME",
        "baseline_matrix_complete": set(contract["baselines"])
        == {
            "always-off",
            "RS-only",
            "fixed-high eligible",
            "transparent suitability rule",
            "learned qualified",
            "cost-matched fixed",
            "cost-and-ON-rate-matched random",
        },
        "three_external_tracks": set(contract["external_tracks"])
        == {"ESConv", "EvoEmo", "ES-MemEval"},
        "ordered_gates_complete": len(contract["ordered_gates"]) == 9
        and contract["ordered_gates"][0] == "G0_GIT_AND_AUTHORITY_FREEZE"
        and contract["ordered_gates"][-1]
        == "G8_THREE_PUBLIC_TRACKS_AND_TERMINAL_CLOSEOUT",
        "all_execution_authority_false": all(
            value is False for value in contract["authorization"].values()
        ),
        "plan_names_literal_splice_and_old_immutability": "literal splice" in plan_text
        and "V2 文件只读" in plan_text,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-component-general-v3-repair-contract-validation-v1",
        "status": "V3_REPAIR_CONTRACT_PASS_G2_PHASE_MAY_BE_DESIGNED"
        if not failed
        else "V3_REPAIR_CONTRACT_FAIL_CLOSED",
        "checks": checks,
        "failed_checks": failed,
        "hashes": {
            "contract_sha256": _sha(CONTRACT),
            "authority_sha256": _sha(AUTHORITY),
            "human_plan_sha256": _sha(plan_path),
            "failure_ledger_sha256": _sha(ledger_path),
        },
        "api_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
        "v3_implementation_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
