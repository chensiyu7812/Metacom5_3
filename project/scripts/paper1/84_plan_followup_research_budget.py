#!/usr/bin/env python3
"""Cost every remaining paid stage of Paper-1 under the follow-up USD 10/20 cap.

Offline and free. This is a quotation, not an authorization: it selects nothing,
freezes nothing and sends nothing.

The point is that paid stages cannot be approved one at a time. Finding k is
cheap compared with the formal evaluation that the paper actually reports, so
this prices the whole remainder together -- amount calibration, training
labels, and the RQ1/RQ2 formal runs -- and then shows which combinations fit.

Two rates are reported for every paid item and never mixed up:
  * reserve  -- the worst case actually held before a call, assuming the
                provider's full native output allowance;
  * observed -- what measured usage suggests, from the one recorded DG pilot
                and from measured scorer input tokens plus assumed reply
                lengths. Assumed reply lengths are assumptions, not caps.
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
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.followup_budget import (
    FOLLOWUP_HARD_CAP_USD, FOLLOWUP_TARGET_USD, FollowupBudget,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

CONFIG = PROJECT / "configs/paper1_public_only.yaml"
LEDGER = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
FOLLOWUP_SNAPSHOT = PROJECT / "outputs/paper1_api_budget/followup_budget_boundary_20260918_v1.json"
DG_COST_SURFACE = PROJECT / "data/paper1_authority/paper1_official_dg_simulator_call_cost_surface_20260904_v1.json"
DG_POLICY = PROJECT / "data/paper1_authority/paper1_official_dg_execution_policy_amendment_20260904_v1.json"
PACKAGE = PROJECT / "outputs/paper1_calibration/static_sample_20260917_v1"
PROTOCOL = "paper1-followup-research-budget-plan-v1"

SYNC = {"input": Decimal("2.5"), "output": Decimal("10")}
BATCH = {"input": Decimal("1.25"), "output": Decimal("5")}

# Measured on 2026-09-19 from the completed 1,924 natural-end generations:
# mean official scorer input per distinct call, prediction INCLUDED.
MEASURED_SCORER_INPUT = {"qa": 388, "summary": 880}
# The prediction is no longer an assumption; it is inside the figure above.
ASSUMED_PREDICTION_TOKENS = {"qa": 0, "summary": 0}
ASSUMED_JUDGE_OUTPUT_TOKENS = {"qa": 8, "summary": 1024}

POPULATION = {"qa": 1427, "summary": 125, "dialogue_generation": 34}
RQ2_ARMS = 6
DG_ROUNDS = 10


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


def static_call_usd(task: str, rate: dict) -> Decimal:
    inputs = Decimal(MEASURED_SCORER_INPUT[task] + ASSUMED_PREDICTION_TOKENS[task])
    outputs = Decimal(ASSUMED_JUDGE_OUTPUT_TOKENS[task])
    return (inputs * rate["input"] + outputs * rate["output"]) / Decimal(1_000_000)


def static_reserve_usd(task: str, rate: dict, native_output: int = 16384) -> Decimal:
    inputs = Decimal(MEASURED_SCORER_INPUT[task] + ASSUMED_PREDICTION_TOKENS[task])
    return (inputs * rate["input"] + Decimal(native_output) * rate["output"]) / Decimal(1_000_000)


def dg_seeker_rates(dg_cost: dict) -> dict:
    surface = dg_cost["six_system_call_surface"]
    reserve_total = Decimal(str(
        dg_cost["seeker_cost_surface_six_systems"]["one_physical_attempt_per_logical_call"]
        ["uncached_worst_case_usd"]))
    reserve_per_call = reserve_total / Decimal(surface["seeker_logical_calls"])
    # The recorded A6000 compatibility trajectory: 10 real paid seeker calls.
    pilot = dg_cost_pilot_usd()
    return {"reserve_per_call_usd": reserve_per_call,
            "observed_per_call_usd": pilot / Decimal(10),
            "observed_source": "single recorded 10-call A6000 pilot; one scenario, not a population mean"}


def dg_cost_pilot_usd() -> Decimal:
    policy = read_json(DG_POLICY)
    return Decimal(str(policy["compatibility_evidence"]["active_a6000_trajectory"]["actual_cost_usd"]))


def stage_rows(dg_rates: dict) -> list[dict]:
    """Every remaining paid item, at full original scope."""
    rows = []

    # 1. QA/Summary static amount calibration (the 1,924 prepared requests).
    prepared = read_json(PACKAGE / "preparation_summary.json")
    # Measured after the real run: byte-identical scorer prompts are bought once.
    calls = {"qa": 903, "summary": 728}
    rows.append({
        "stage": "A. QA/Summary amount calibration scoring",
        "purpose": "choose k for MP/ME/MS on the static tasks",
        "paid_calls": sum(calls.values()),
        "rows_before_identical_payload_reuse": prepared["generator_calls"],
        "calls_detail": calls,
        "delivery_options": {
            "sync_observed_usd": money(sum(static_call_usd(t, SYNC) * calls[t] for t in calls)),
            "batch_observed_usd": money(sum(static_call_usd(t, BATCH) * calls[t] for t in calls)),
            "batch_reserve_usd": money(sum(static_reserve_usd(t, BATCH) * calls[t] for t in calls)),
        },
        "generation": ("DONE 2026-09-19: all 1,924 natural-end generations completed, "
                       "6,199 s GPU wall, USD 0"),
        "note": ("input tokens measured from the real predictions; only the judge reply length "
                 "is still an assumption"),
    })

    # 2. Training labels for the four heads on the static tasks.
    # Effect labels need a scored ON and OFF response per contrast.
    label_targets = POPULATION["qa"] + POPULATION["summary"]
    rows.append({
        "stage": "B. PM training labels (static tasks)",
        "purpose": "materially-positive effect labels for MP/ME/MS heads",
        "paid_calls": "SCOPE_NOT_FIXED",
        "note": ("Label volume depends on how many independent states are scored per head. "
                 "At the full population one ON scoring per head plus one shared OFF is "
                 f"{label_targets} x 4 = {label_targets * 4} official calls, which alone exceeds "
                 "the follow-up cap at any delivery rate. This stage must be sized deliberately."),
        "batch_observed_usd_full_population": money(
            sum(static_call_usd(t, BATCH) * POPULATION[t] * 4 for t in ["qa", "summary"])),
    })

    # 3. RQ1 formal evaluation: entirely local.
    rows.append({
        "stage": "C. RQ1 ESC-Eval formal evaluation",
        "purpose": "official RQ1 capability table, 4 arms on 121 confirmatory cards",
        "paid_calls": 0, "usd": "0",
        "note": "supporter, ESC-Role seeker and the official ESC-RANK scorer are all local",
    })

    # 4. RQ2 static formal evaluation.
    rq2_static_calls = {t: POPULATION[t] * RQ2_ARMS for t in ["qa", "summary"]}
    rows.append({
        "stage": "D. RQ2 QA/Summary formal evaluation",
        "purpose": f"official QA/Summarization metrics, {RQ2_ARMS} arms on the full population",
        "paid_calls": sum(rq2_static_calls.values()),
        "calls_detail": rq2_static_calls,
        "delivery_options": {
            "batch_observed_usd": money(
                sum(static_call_usd(t, BATCH) * rq2_static_calls[t] for t in rq2_static_calls)),
            "sync_observed_usd": money(
                sum(static_call_usd(t, SYNC) * rq2_static_calls[t] for t in rq2_static_calls)),
        },
        "note": "this is the reported result, not a tuning step",
    })

    # 5. RQ2 DG formal evaluation.
    dg_calls = POPULATION["dialogue_generation"] * DG_ROUNDS * RQ2_ARMS
    rows.append({
        "stage": "E. RQ2 DG formal evaluation",
        "purpose": f"official Dialogue Generation metrics, {RQ2_ARMS} arms x 34 scenarios x 10 rounds",
        "paid_calls": dg_calls,
        "usd_at_reserve": money(dg_rates["reserve_per_call_usd"] * dg_calls),
        "usd_at_pilot_observed_rate": money(dg_rates["observed_per_call_usd"] * dg_calls),
        "plus_official_overall_judge_calls": POPULATION["dialogue_generation"] * RQ2_ARMS,
        "note": ("the simulated user is sequential and cannot be pre-batched; each round depends "
                 "on the previous supporter reply"),
    })

    # 6. DG amount calibration at the full grid, for comparison only.
    grid_calls = POPULATION["dialogue_generation"] * DG_ROUNDS * 13
    rows.append({
        "stage": "F. DG amount calibration at the full 13-condition grid",
        "purpose": "choose k live for MP/ME/MS on DG",
        "paid_calls": grid_calls,
        "usd_at_reserve": money(dg_rates["reserve_per_call_usd"] * grid_calls),
        "usd_at_pilot_observed_rate": money(dg_rates["observed_per_call_usd"] * grid_calls),
        "verdict": "incompatible with the follow-up cap at either rate",
    })
    return rows


def plans(dg_rates: dict) -> list[dict]:
    """Candidate whole-programme plans. Proposals only: none is selected."""
    calls = {"qa": 903, "summary": 728}
    calib_batch = sum(static_call_usd(t, BATCH) * calls[t] for t in calls)

    def dg(scenarios: int, arms: int, rounds: int = DG_ROUNDS) -> tuple[int, Decimal, Decimal]:
        n = scenarios * arms * rounds
        return n, dg_rates["reserve_per_call_usd"] * n, dg_rates["observed_per_call_usd"] * n

    def rq2_static(fraction: Decimal) -> Decimal:
        return sum(static_call_usd(t, BATCH) * int(POPULATION[t] * RQ2_ARMS * fraction)
                   for t in ["qa", "summary"])

    result = []

    # P0 targets the researcher's ~USD 10 figure. Its levers are the two that
    # actually move money: how much Summary calibration is bought, and how many
    # RQ2 arms are scored -- not the length of any answer.
    qa_calib = static_call_usd("qa", BATCH) * 903
    summary_calib_reduced = static_call_usd("summary", BATCH) * 728
    rq2_four_arms = sum(static_call_usd(t, BATCH) * POPULATION[t] * 4 for t in ["qa", "summary"])
    p0_total = qa_calib + summary_calib_reduced + rq2_four_arms
    result.append({
        "plan": "P0 - aim at the USD 10 target",
        "components": {
            "A QA amount calibration, full prepared sample (batch)": money(qa_calib),
            "A Summary amount calibration, full prepared sample (batch)": money(summary_calib_reduced),
            "D RQ2 static formal at FULL population, 4 arms (batch)": money(rq2_four_arms),
            "C RQ1 ESC-Eval formal": "0",
            "E RQ2 DG formal": "not executed",
        },
        "total_at_observed_rates_usd": money(p0_total),
        "total_at_dg_reserve_usd": money(p0_total),
        "dg_paid_calls": 0,
        "retry_margin_to_cap_usd": money(FOLLOWUP_HARD_CAP_USD - p0_total),
        "keeps": ["full-population official QA/Summarization results on the compared arms",
                  "k chosen from real official quality on both static tasks",
                  "complete RQ1 official table at full scope, free",
                  "the largest retry and training-label margin of any plan here"],
        "gives_up": ["two of the six RQ2 arms", "the entire DG component"],
        "cannot_claim": ("RQ2 would cover two of three ES-MemEval tasks, and which four arms to keep "
                         "is a research decision, not a costing one"),
    })

    dg_calls, dg_reserve, dg_observed = dg(8, RQ2_ARMS)
    total_observed = calib_batch + rq2_static(Decimal("0.25")) + dg_observed
    result.append({
        "plan": "P1 - calibrate the static tasks, evaluate on a declared subset",
        "components": {
            "A static amount calibration (batch)": money(calib_batch),
            "D RQ2 static formal on a 25% pre-drawn subset (batch)": money(rq2_static(Decimal("0.25"))),
            "E RQ2 DG formal on 8 pre-drawn scenarios, all 6 arms": money(dg_observed),
            "C RQ1 ESC-Eval formal": "0",
        },
        "total_at_observed_rates_usd": money(total_observed),
        "total_at_dg_reserve_usd": money(calib_batch + rq2_static(Decimal("0.25")) + dg_reserve),
        "dg_paid_calls": dg_calls,
        "keeps": ["k chosen from real official quality on QA/Summary",
                  "all six RQ2 arms compared against each other",
                  "complete RQ1 official table at full scope, free",
                  "complete dialogues and natural ending"],
        "gives_up": ["full-population RQ2 static numbers",
                     "all 34 DG scenarios",
                     "any DG-specific k tuning"],
        "cannot_claim": "subset results do not carry the evidential strength of the full benchmark",
    })

    dg_calls, dg_reserve, dg_observed = dg(6, 3)
    total_observed = calib_batch + rq2_static(Decimal("1.0")) + dg_observed
    result.append({
        "plan": "P2 - full static evaluation, minimal DG",
        "components": {
            "A static amount calibration (batch)": money(calib_batch),
            "D RQ2 static formal at FULL population (batch)": money(rq2_static(Decimal("1.0"))),
            "E RQ2 DG formal on 6 scenarios, 3 arms only": money(dg_observed),
            "C RQ1 ESC-Eval formal": "0",
        },
        "total_at_observed_rates_usd": money(total_observed),
        "total_at_dg_reserve_usd": money(calib_batch + rq2_static(Decimal("1.0")) + dg_reserve),
        "dg_paid_calls": dg_calls,
        "keeps": ["full-population official QA/Summarization results",
                  "k chosen from real official quality",
                  "complete RQ1 official table"],
        "gives_up": ["three of the six DG arms", "28 of 34 DG scenarios"],
        "cannot_claim": "DG becomes an illustration, not a benchmark result",
    })

    dg_calls, dg_reserve, dg_observed = dg(0, 0)
    total_observed = calib_batch + rq2_static(Decimal("1.0"))
    result.append({
        "plan": "P3 - no paid DG at all",
        "components": {
            "A static amount calibration (batch)": money(calib_batch),
            "D RQ2 static formal at FULL population (batch)": money(rq2_static(Decimal("1.0"))),
            "C RQ1 ESC-Eval formal": "0",
            "E RQ2 DG formal": "not executed",
        },
        "total_at_observed_rates_usd": money(total_observed),
        "total_at_dg_reserve_usd": money(total_observed),
        "dg_paid_calls": 0,
        "keeps": ["full-population official QA/Summarization results",
                  "complete RQ1 official table",
                  "largest margin left inside the cap for retries and training labels"],
        "gives_up": ["the entire DG component of RQ2"],
        "cannot_claim": "RQ2 cannot be described as covering all three ES-MemEval tasks",
    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/followup_budget_plan_20260918_v1")
    args = parser.parse_args()
    assert_pre_outcome_locked(load_public_only_config(CONFIG))

    ledger = CumulativePaper1ApiBudgetLedger(LEDGER)
    followup = FollowupBudget(ledger, FOLLOWUP_SNAPSHOT)
    dg_cost = read_json(DG_COST_SURFACE)
    dg_rates = dg_seeker_rates(dg_cost)

    report = {
        "protocol": PROTOCOL, "generated_at": utc_now(),
        "status": "QUOTATION_ONLY_NOTHING_SELECTED_NOTHING_SENT",
        "followup_constraint": {
            "target_usd": str(FOLLOWUP_TARGET_USD), "hard_cap_usd": str(FOLLOWUP_HARD_CAP_USD),
            "scope": "every remaining new paid call, including retries",
            "baseline_accounted_usd": str(followup.baseline_accounted_usd),
            "current_status": followup.status().as_dict(),
        },
        "dg_seeker_rates": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in dg_rates.items()},
        "assumptions": {
            "measured": ["official scorer input tokens INCLUDING the real prediction, from the "
                         "completed 1,924 natural-end generations",
                         "Generator answer lengths (QA median 36, Summary median 75 tokens)",
                         "DG scenario prompt tokens", "the single recorded 10-call DG pilot cost"],
            "assumed_not_capped": {
                "prediction_tokens": ASSUMED_PREDICTION_TOKENS,
                "judge_output_tokens": ASSUMED_JUDGE_OUTPUT_TOKENS,
            },
            "unmeasured": ["actual judge reply lengths -- the last big unknown, and the one that "
                           "swings the static bill between about USD 2.2 and USD 8.8 at batch rates",
                           "prompt cache hit rate (no discount assumed)"],
            "warning": ("These are estimates. Real figures require the local generations to exist "
                        "first; halving a synchronous estimate does not guarantee a batch completes "
                        "inside any budget."),
        },
        "cost_drivers": {
            "per_call_batch_usd": {t: money(static_call_usd(t, BATCH)) for t in ["qa", "summary"]},
            "summary_is_the_driver": (
                "One Summary judgement costs about "
                f"{money(static_call_usd('summary', BATCH) / static_call_usd('qa', BATCH))}x a QA one, "
                "because the official Summary judge returns event lists and a justification while QA "
                "returns one line. Summary is roughly 88% of the amount-calibration bill despite being "
                "the smaller task."),
            "disproportion_to_flag": (
                f"The prepared Summary calibration buys {63 * 13} judgements to choose k for a task whose "
                f"entire population is {POPULATION['summary']} targets. That is defensible as a paired "
                "design but is the single most reducible cost in the programme."),
            "levers_that_move_money": [
                "number of RQ2 arms scored",
                "size of the Summary calibration sample",
                "batch instead of synchronous delivery (exactly half)",
                "whether DG is executed at all",
            ],
            "levers_that_must_not_be_used": [
                "shortening Generator answers",
                "capping judge output below the official setting",
                "substituting a local judge for the official scorer",
            ],
        },
        "stages_at_original_scope": stage_rows(dg_rates),
        "candidate_plans": plans(dg_rates),
        "headline": (
            "The original full scope does not fit. RQ1 is free. The paid load is the RQ2 official "
            "scoring, and the DG simulated user dominates it. Amount calibration is affordable by "
            "batch; the formal evaluation is what the cap actually constrains, so k-finding must "
            "not consume the budget first."),
        "not_selected": ("No plan here is chosen, and the scenario counts are illustrations of the "
                         "trade-off, not a drawn sample. Substantive changes to frozen research "
                         "conditions need an explicit decision."),
        "sources_sha256": {p.name: sha256_file(p) for p in [DG_COST_SURFACE, DG_POLICY,
                                                            PACKAGE / "preparation_summary.json"]},
    }
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "followup_budget_plan.json", report)
    print(json.dumps({
        "status": report["status"],
        "followup": {"target": str(FOLLOWUP_TARGET_USD), "cap": str(FOLLOWUP_HARD_CAP_USD),
                     "committed_so_far": report["followup_constraint"]["current_status"][
                         "committed_new_spend_usd"]},
        "stages": [{k: v for k, v in row.items()
                    if k in ["stage", "paid_calls", "usd", "delivery_options",
                             "usd_at_pilot_observed_rate", "verdict"]}
                   for row in report["stages_at_original_scope"]],
        "plans": [{"plan": p["plan"], "total_at_observed_rates_usd": p["total_at_observed_rates_usd"],
                   "total_at_dg_reserve_usd": p["total_at_dg_reserve_usd"]}
                  for p in report["candidate_plans"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
