#!/usr/bin/env python3
"""Audit what RS and DG amount calibration would actually require.

Offline and free: no generation, no paid call, no k selection, no formal
outcome. Every number is either read from an existing hash-verified artifact or
derived from one by arithmetic that is stated in the output. Quantities that
have not been measured yet are reported as unmeasured rather than estimated,
because the point of this audit is to find out, before anything is spent,
whether each remaining calibration stage is affordable at all.

RS/ESC-Eval and DG differ sharply: the ESC-Eval loop (supporter, ESC-Role
seeker and the official ESC-RANK scorer) is entirely local, while the DG loop
pays for every logical seeker turn. That asymmetry decides what is feasible.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import read_json, sha256_file, utc_now, write_json
from metacom_pm.paper1.api_budget import (
    CumulativePaper1ApiBudgetLedger, PAPER1_API_HARD_CAP_USD, PAPER1_RETRY_RESERVE_USD,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

CONFIG = PROJECT / "configs/paper1_public_only.yaml"
LEDGER = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
PROTOCOL = "paper1-rs-dg-calibration-readiness-audit-v1"

AUTHORITY = PROJECT / "data/paper1_authority"
SOURCES = {
    "esc_split": AUTHORITY / "paper1_esc_split_large52_frozen_v1.jsonl",
    "planning_envelope": AUTHORITY / "paper1_expected_api_gpu_call_budget_20260820_v1.json",
    "esc_eval_compatibility": AUTHORITY / "paper1_official_esc_eval_compatibility_amendment_20260902_v1.json",
    "dg_cost_surface": AUTHORITY / "paper1_official_dg_simulator_call_cost_surface_20260904_v1.json",
    "dg_execution_policy": AUTHORITY / "paper1_official_dg_execution_policy_amendment_20260904_v1.json",
    "static_execution": AUTHORITY / "paper1_static_amount_calibration_execution_20260917_v1.json",
}

# The static QA/Summary batch fixed the calibration design: three memory heads,
# k in 1..4, plus one shared true-OFF per unit. The same shape is what RS and DG
# would need, which is why their volumes are computed against it.
HEADS = ("MP", "ME", "MS")
K_GRID = (1, 2, 3, 4)
CONDITIONS_PER_UNIT = len(HEADS) * len(K_GRID) + 1


def usd(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.00000001")))


def audit_rs(planning: dict, compatibility: dict, split_rows: list[dict]) -> dict:
    """RS amount calibration is a local ESC-Eval loop with a local official scorer."""
    large = planning["rq1_rs_external_calibration_scenarios"]["large_52"]
    turns = planning["rq1_rs_external_calibration_scenarios"]["turns_per_esc_eval_trajectory"]
    arms = planning["rq1_rs_external_calibration_scenarios"]["amount_arms"]
    calibration_cards = sum(1 for r in split_rows if r["split"] == "calibration")
    confirmatory_cards = sum(1 for r in split_rows if r["split"] == "confirmatory")
    seconds_per_scoring_pass = compatibility["runtime_evidence_before_amendment"]["mean_seven_dimension_seconds"]
    trajectories = large["trajectories"]
    scorer_seconds = Decimal(str(seconds_per_scoring_pass)) * trajectories
    return {
        "stage": "RS_amount_calibration",
        "benchmark": "ESC-Eval",
        "cards": {"calibration": calibration_cards, "confirmatory": confirmatory_cards,
                  "planning_envelope_role_cards": large["role_cards"]},
        "amount_arms": arms,
        "turns_per_trajectory": turns,
        "trajectories": trajectories,
        "generator_calls": large["nvidia_generator_calls"],
        "esc_role_seeker_turns_local": large["esc_role_local_inference_turns"],
        "official_esc_rank_dimension_passes": large["official_esc_rank_dimension_passes"],
        "paid_api_calls_required": 0,
        "paid_usd_required": "0",
        "why_free": ("The ESC-Eval loop is local end to end: the frozen Generator is the supporter, "
                     "ESC-Role is local inference, and the official ESC-RANK scorer is a local "
                     "internlm2-chat-7b plus adapter. No provider call is involved."),
        "measured_scorer_seconds_per_trajectory": seconds_per_scoring_pass,
        "official_scorer_wall_seconds_for_all_trajectories": float(scorer_seconds),
        "generation_wall_time": "UNMEASURED_FOR_THIS_LOOP",
        "generation_wall_time_note": (
            "Supporter and ESC-Role turn latency on this stack has not been measured for the "
            "ESC-Eval loop. It must be timed on a small pilot before a wall-clock claim; the "
            "judge-development rate is not transferable because those were long reasoning outputs."),
        "blocking_decisions": [
            "RS amount calibration uses the 52 calibration cards only; the 121 confirmatory cards stay sealed.",
            "The five-point arm grid (k=0..4) and five turns per trajectory come from the 2026-08-20 planning "
            "envelope, which is explicitly PLANNING_ENVELOPE_NOT_AUTHORIZATION and must be re-confirmed.",
            "The RS bundle is retrieved per turn under leave-current-dialogue-out retrieval; the exact per-turn "
            "retrieval binding for the ESC-Eval loop is not yet materialized as a request manifest.",
        ],
        "feasible_within_remaining_budget": True,
        "binding_constraint": "GPU wall time, not money",
    }


def audit_dg(dg_cost: dict, dg_policy: dict, remaining: Decimal, primary_ceiling_headroom: Decimal) -> dict:
    """DG calibration pays for every logical seeker turn, so volume decides feasibility."""
    surface = dg_cost["six_system_call_surface"]
    seeker = dg_cost["seeker_cost_surface_six_systems"]["one_physical_attempt_per_logical_call"]
    scenarios = dg_cost["public_population"]["scenarios"]
    rounds = dg_cost["upstream"]["seeker_rounds_per_scenario"]
    six_system_seeker_calls = surface["seeker_logical_calls"]
    six_system_usd = Decimal(str(seeker["uncached_worst_case_usd"]))
    per_logical_call = six_system_usd / Decimal(six_system_seeker_calls)

    calibration_seeker_calls = scenarios * rounds * CONDITIONS_PER_UNIT
    calibration_usd = per_logical_call * Decimal(calibration_seeker_calls)
    judge_scale = Decimal(CONDITIONS_PER_UNIT) / Decimal(6)
    calibration_overall_judge_calls = int(surface["gpt4o_overall_judge_calls"] * judge_scale)
    calibration_local_turn_judge_calls = int(surface["total_local_mistral24b_turn_judge_calls"] * judge_scale)

    return {
        "stage": "DG_amount_calibration",
        "benchmark": "ES-MemEval Dialogue Generation",
        "scenarios": scenarios,
        "rounds_per_scenario": rounds,
        "conditions_per_scenario": CONDITIONS_PER_UNIT,
        "conditions_note": f"{len(HEADS)} heads x k in {list(K_GRID)} plus one shared true-OFF",
        "static_query_substitute_forbidden": True,
        "retrieval_note": ("DG retrieves after each live seeker utterance, so a condition cannot reuse "
                           "another condition's trajectory: every condition is its own paid run."),
        "recorded_six_system_reference": {
            "seeker_logical_calls": six_system_seeker_calls,
            "uncached_worst_case_usd": usd(six_system_usd),
            "derived_usd_per_logical_seeker_call": usd(per_logical_call),
        },
        "calibration_volume": {
            "paid_seeker_logical_calls": calibration_seeker_calls,
            "paid_official_overall_judge_calls": calibration_overall_judge_calls,
            "local_mistral24b_turn_judge_calls": calibration_local_turn_judge_calls,
        },
        "paid_usd_required_seeker_only_worst_case": usd(calibration_usd),
        "cumulative_remaining_usd": usd(remaining),
        "primary_call_headroom_usd": usd(primary_ceiling_headroom),
        "feasible_within_remaining_budget": calibration_usd <= primary_ceiling_headroom,
        "shortfall_usd": usd(calibration_usd - primary_ceiling_headroom) if calibration_usd > primary_ceiling_headroom else "0",
        "still_owed_after_calibration": {
            "six_system_confirmatory_seeker_worst_case_usd": usd(six_system_usd),
            "note": "The confirmatory six-system DG run is the actual RQ2 deliverable and is not included above.",
        },
        "blocking_decisions": [
            "Full-grid DG amount calibration is not affordable; the researcher must choose how to reduce it.",
            "Reduction options that do not depend on seeing any result: fewer DG scenarios in calibration, "
            "a coarser k grid, calibrating fewer heads live, or adopting the static QA/Summary k for DG with "
            "the transfer stated as a limitation.",
            "Whatever is chosen must be fixed before any DG call, because a result-driven choice is forbidden.",
        ],
        "binding_constraint": "paid seeker calls",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/rs_dg_readiness_20260918_v1")
    args = parser.parse_args()

    assert_pre_outcome_locked(load_public_only_config(CONFIG))
    missing = {name: str(path) for name, path in SOURCES.items() if not path.exists()}
    if missing:
        raise RuntimeError(f"required audit source is absent: {missing}")
    sources = {name: sha256_file(path) for name, path in SOURCES.items()}

    planning = read_json(SOURCES["planning_envelope"])
    compatibility = read_json(SOURCES["esc_eval_compatibility"])
    dg_cost = read_json(SOURCES["dg_cost_surface"])
    dg_policy = read_json(SOURCES["dg_execution_policy"])
    split_rows = [json.loads(line) for line in SOURCES["esc_split"].read_text().splitlines() if line.strip()]

    ledger = CumulativePaper1ApiBudgetLedger(LEDGER)
    remaining = ledger.remaining_usd
    primary_ceiling_headroom = PAPER1_API_HARD_CAP_USD - PAPER1_RETRY_RESERVE_USD - ledger.accounted_cost_usd

    rs = audit_rs(planning, compatibility, split_rows)
    dg = audit_dg(dg_cost, dg_policy, remaining, primary_ceiling_headroom)

    report = {
        "protocol": PROTOCOL, "generated_at": utc_now(),
        "status": "OFFLINE_READINESS_AUDIT_NO_EXECUTION_NO_PAID_CALLS_NO_K_SELECTION",
        "purpose": ("Establish, before anything is spent, what RS and DG amount calibration each require "
                    "and whether they fit the remaining Paper-1 API budget."),
        "budget": {
            "cumulative_accounted_usd": usd(ledger.accounted_cost_usd),
            "cumulative_remaining_usd": usd(remaining),
            "hard_cap_usd": str(PAPER1_API_HARD_CAP_USD),
            "primary_retry_reserve_usd": str(PAPER1_RETRY_RESERVE_USD),
            "headroom_for_non_retry_calls_usd": usd(primary_ceiling_headroom),
            "not_yet_authorized_static_qa_summary_stage_usd": 15,
            "static_stage_authorized": False,
        },
        "stages": [rs, dg],
        "headline": (
            "RS amount calibration needs no paid call at all and is limited by GPU wall time. "
            "DG amount calibration at the full grid needs about "
            f"USD {dg['paid_usd_required_seeker_only_worst_case']} of paid seeker calls alone, against "
            f"USD {usd(primary_ceiling_headroom)} of headroom, and the six-system confirmatory DG run "
            f"(about USD {dg['still_owed_after_calibration']['six_system_confirmatory_seeker_worst_case_usd']}) "
            "has not been spent yet either. DG calibration must be reduced by an explicit, "
            "result-blind researcher decision before any DG call."),
        "explicitly_not_done_here": [
            "no generation", "no paid API call", "no k selection", "no k* freeze",
            "no formal outcome", "no PM training", "no lock opened",
        ],
        "sources_sha256": sources,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "readiness_report.json", report)
    print(json.dumps({
        "status": report["status"],
        "RS_paid_usd": rs["paid_usd_required"],
        "RS_trajectories": rs["trajectories"],
        "RS_feasible": rs["feasible_within_remaining_budget"],
        "DG_paid_seeker_calls": dg["calibration_volume"]["paid_seeker_logical_calls"],
        "DG_paid_usd_worst_case": dg["paid_usd_required_seeker_only_worst_case"],
        "DG_headroom_usd": dg["primary_call_headroom_usd"],
        "DG_feasible": dg["feasible_within_remaining_budget"],
        "DG_shortfall_usd": dg["shortfall_usd"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
