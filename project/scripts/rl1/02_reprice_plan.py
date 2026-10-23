#!/usr/bin/env python3
"""Offline quotation: input evidence measured, future response lengths scenarios.

No external request is sent. Assumed output lengths are NOT generation caps.
Prices checked against official GPT-4o/Batch pages on 2026-09-28.
"""
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import iter_jsonl, read_json, sha256_file
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.followup_budget import FollowupBudget
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.rl1.data import build_prefixes

OUT = PROJECT / "outputs/pm_rl1/engineering_20260928_v1"


def cost(inputs: int, outputs: int, calls: int, batch=False):
    amount = (Decimal(inputs) * Decimal("2.5") + Decimal(outputs * calls) * Decimal("10")) / Decimal(1000000)
    return float(amount / (2 if batch else 1))


def main():
    import tiktoken
    enc = tiktoken.encoding_for_model("gpt-4o")
    users = load_sanitized_runtime_users(PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json")
    prefixes, _ = build_prefixes(users)
    user_map = {u.owner_id: u for u in users}
    evidence_lengths = []
    for p in prefixes:
        past = "\n\n".join(s.timestamp + "\n" + "\n".join(f"{t.role}: {t.content}" for t in s.turns)
                            for s in user_map[p.owner_id].sessions if s.chronological_rank < p.cutoff_rank)
        evidence_lengths.append(len(enc.encode(past + "\n\n" + p.query)))
    ordered = sorted(evidence_lengths)
    # Expected evaluation payload includes complete allowed history, rubric,
    # formatting and two replies. Only the history/prefix component is measured.
    input_scenarios = {"median_history": int(statistics.median(ordered)) + 2048,
                       "p95_history": ordered[int(.95 * len(ordered))] + 2048,
                       "max_history": ordered[-1] + 2048}
    independent = []
    for label, per_input in input_scenarios.items():
        for outputs in (256, 512, 1024, 16384):
            independent.append(dict(scenario=label, calls=36, input_per_call=per_input,
                assumed_output_per_call=outputs, assumption_is_output_cap=False,
                interpretation="native output liability scenario" if outputs == 16384 else "length forecast only",
                sync_usd=cost(per_input * 36, outputs, 36), batch_usd=cost(per_input * 36, outputs, 36, True)))
    # Recount old exact scorer payloads rather than pricing 1,924 duplicates.
    payloads = {r["call_hash"]: r for r in iter_jsonl(PROJECT / "outputs/paper1_calibration/static_official_scoring_20260917_v1/requests.jsonl")}
    lengths = {key: sum(len(enc.encode(m["content"])) + 32 for m in row["body"]["messages"]) + 32
               for key, row in payloads.items()}
    if any(lengths[k] != r["estimated_input_tokens_with_framing_reserve"] for k, r in payloads.items()):
        raise ValueError("legacy payload token recount disagrees with original framing reserve")
    by_task = Counter(r["task"] for r in payloads.values())
    qa_inputs = [lengths[k] for k, r in payloads.items() if r["task"] == "qa"]
    qa_input_forecast = round(statistics.mean(qa_inputs))
    optional_qa = [dict(calls=192, measured_legacy_mean_input=qa_input_forecast,
                       assumed_output_per_call=out, assumption_is_output_cap=False,
                       sync_usd=cost(192 * qa_input_forecast, out, 192),
                       batch_usd=cost(192 * qa_input_forecast, out, 192, True)) for out in (8, 64, 16384)]
    legacy_output_forecast = sum(8 if r["task"] == "qa" else 1024 for r in payloads.values())
    ledger_path = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
    boundary = PROJECT / "outputs/paper1_api_budget/followup_budget_boundary_20260918_v1.json"
    if not boundary.exists():
        raise RuntimeError("do not create/reset the historical budget boundary")
    batch_states = sorted((PROJECT / "outputs/paper1_calibration").rglob("batches.json"))
    liability_by_id = {}
    for path in batch_states:
        for row in read_json(path)["batches"]:
            previous = liability_by_id.get(row["batch_id"])
            if previous is not None and previous != row:
                raise ValueError("conflicting recorded batch liability; reconcile before quoting balance")
            liability_by_id[row["batch_id"]] = row
    budget = FollowupBudget(CumulativePaper1ApiBudgetLedger(ledger_path), boundary).status(list(liability_by_id.values())).as_dict()
    core = dict(executor_data=2160, initialization=1440, rl_training=1536,
                dev_evaluation=576, formal_execution=864, formal_policy_cross=1920)
    report = dict(protocol="pm-rl1-repricing-v1", checked_date="2026-09-28",
        price_source="https://developers.openai.com/api/docs/models/gpt-4o",
        batch_source="https://developers.openai.com/api/docs/guides/batch",
        pricing_model_scenario="gpt-4o; not a reward-model selection or paid-call authorization",
        rates_usd_per_million=dict(sync_input=2.5, sync_output=10, batch_input=1.25, batch_output=5),
        budget=budget, budget_ledger_sha256=sha256_file(ledger_path),
        known_batch_state_files={str(p): sha256_file(p) for p in batch_states},
        core_local_calls=core, core_local_call_total=sum(core.values()),
        off_additional_call_reserve=672, measurement_score_calls=60,
        nominal_known_call_ceiling=9228,
        ceiling_note="8496 + 672 + 60; not a full project bound: measurement replies, SFT diagnostics, retries, independent review and timing excluded; exact cache dedup can reduce",
        local_core_api_usd=0,
        excluded_default_extras=dict(optional_executor_data_extension=1728,
                                     optional_all_formal_esc_rank_dimensions=9744,
                                     optional_latency_generations=144),
        measured_legal_evidence_tokens=dict(n=len(ordered), min=ordered[0], median=statistics.median(ordered),
                                          p95=ordered[int(.95 * len(ordered))], max=ordered[-1]),
        independent_review=dict(calls="12 measurement pairs + 24 final pairs = 36 single presentations",
            assumed_extra_input_tokens=2048,
            caveat="rubric and two response sizes not yet measured; price exact complete payloads before sending; reversal duplicates this line",
            scenarios=independent),
        optional_official_qa=dict(note="192 answers; current answers not yet generated; legacy input length is a forecast anchor", scenarios=optional_qa),
        old_scoring_separate=dict(unique_calls=len(payloads), task_counts=dict(by_task), measured_input_tokens_with_framing_reserve=sum(lengths.values()),
            assumed_outputs="QA 8; Summary 1024 (length scenarios, not caps)",
            forecast_sync_usd=cost(sum(lengths.values()), legacy_output_forecast, 1),
            forecast_batch_usd=cost(sum(lengths.values()), legacy_output_forecast, 1, True),
            native_batch_liability_usd=cost(sum(lengths.values()), 16384, len(payloads), True),
            pm_rl1_prerequisite=False),
        compute=dict(executor_teacher_and_repair_calls=1080, executor_verification_calls=1080,
            downstream_generator_calls=3168, downstream_joint_judge_calls=3168,
            formula_seconds="1080*t_teacher + 1080*t_verifier + 3168*t_G + 3168*t_J + OFF + measurement + embeddings + loads + LoRA + PPO + retries",
            price_usd="local ownership/electricity/rental rate not supplied; do not equate zero API spend with zero compute cost",
            wall_clock="requires measured G/J throughput and scheduling; no total-hours promise"),
        paid_calls_sent=0)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cost_reassessment.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(budget=budget, evidence=report["measured_legal_evidence_tokens"],
                         review_scenarios=independent, optional_qa=optional_qa,
                         old_scoring=report["old_scoring_separate"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
