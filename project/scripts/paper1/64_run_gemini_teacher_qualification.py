#!/usr/bin/env python3
"""Prepare, preflight, or execute exactly the frozen 96 teacher requests.

The default is offline. Live generation requires a separate authorization bound
to this execution plan, including the disclosed joint-human-reference amendment.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, write_json
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.evaluation.gemini_teacher import (
    MODEL, count_requests, run_requests, validate_requests,
)
from metacom_pm.paper1.evaluation.human_reference import read_rating_json
from metacom_pm.paper1.evaluation.pairwise_teacher import pairwise_teacher_identity_payload
from metacom_pm.paper1.evaluation.teacher_diagnostics import (
    clustered_agreement_interval, index_presentations, reference_comparison,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config


def plan_for(project: Path, output: Path):
    authority = project / "data/paper1_authority"
    identity_path = authority / "paper1_gemini_pairwise_teacher_identity_20260908_v2.json"
    identity = read_rating_json(identity_path)
    source_manifest = read_rating_json(authority / "paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json")
    if sha256_file(identity_path) != source_manifest["teacher_identity_sha256"]:
        raise ValueError("teacher identity hash changed")
    if sha256_file(project / "src/metacom_pm/paper1/evaluation/pairwise_teacher.py") != identity["parser"]["source_sha256"]:
        raise ValueError("frozen teacher parser source changed")
    for key, value in pairwise_teacher_identity_payload().items():
        if identity["prompt_identity"][key] != value:
            raise ValueError("frozen teacher prompt/parser schema changed")
    request_path = project / identity["exact_request_manifest"]["path"]
    if sha256_file(request_path) != identity["exact_request_manifest"]["sha256"]:
        raise ValueError("frozen teacher request manifest changed")
    rows = [json.loads(line) for line in request_path.read_text().splitlines() if line.strip()]
    validate_requests(rows, identity)
    review = project / "outputs/paper1_pairwise_teacher/review_closeout_20260917_v1"
    intake = read_rating_json(review / "intake_result.json")
    closeout_path = authority / "paper1_human_review_closeout_20260917_v1.json"
    if intake["closeout_sha256"] != sha256_file(closeout_path):
        raise ValueError("reference closeout changed after intake")
    if not intake["teacher_request_preflight"]["English_payload_matches_sealed_sheets"]:
        raise ValueError("reference intake not validated")
    for source in intake["sources"].values():
        if sha256_file(source["path"]) != source["sha256"]:
            raise ValueError("sealed original submission changed")
    trace_path = review / "reference_trace.json"
    references = read_json(trace_path)
    if index_presentations(references).keys() != index_presentations(rows).keys():
        raise ValueError("reference/request presentation sets differ")
    originals = index_presentations(read_rating_json(Path(intake["sources"]["human_A"]["path"]))["items"])
    followup = index_presentations(read_rating_json(Path(intake["sources"]["six_case_followup"]["path"]))["items"])
    closeout = index_presentations(read_rating_json(closeout_path)["cases"])
    blind_path = authority / "paper1_pairwise_teacher_blind_key_20260904_v1.jsonl"
    base_path = authority / "paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"
    for path, key in ((blind_path, "blind_key"), (base_path, "base_pairs")):
        if sha256_file(path) != source_manifest["source_sha256"][key]:
            raise ValueError("base/reversal source binding changed")
    blind = index_presentations([json.loads(line) for line in blind_path.read_text().splitlines()])
    bases = {r["base_pair_id"]: r for r in (json.loads(line) for line in base_path.read_text().splitlines())}
    for row in references:
        pid = row["presentation_id"]
        if row["reference_verdict"] != originals[pid]["verdict"] or row["reference_rationale"] != originals[pid]["rationale"]:
            raise ValueError("reference trace differs from original A")
        if row["task"] != originals[pid]["task"] or row["item_number_A"] != originals[pid]["item_number"]:
            raise ValueError("reference task/item identity mismatch")
        if row.get("followup") != followup.get(pid) or row.get("closeout") != closeout.get(pid):
            raise ValueError("reference posthoc annotation changed")
        for key in ("base_pair_id", "A_arm", "reverse_duplicate"):
            if row[key] != blind[pid][key]:
                raise ValueError("reference base/orientation mismatch")
        row["cluster_id"] = bases[row["base_pair_id"]]["owner_or_dialogue_group"]
    implementation = [
        "scripts/paper1/64_run_gemini_teacher_qualification.py",
        "src/metacom_pm/paper1/evaluation/gemini_teacher.py",
        "src/metacom_pm/paper1/evaluation/pairwise_teacher.py",
        "src/metacom_pm/paper1/evaluation/teacher_diagnostics.py",
        "src/metacom_pm/paper1/api_budget.py",
    ]
    provider_path = output / "provider_preflight.json"
    repair_path = authority / "paper1_gemini_usage_accounting_repair_20260917_v1.json"
    plan = {
        "protocol": "paper1-gemini-teacher-execution-plan-v1",
        "status": "PROPOSED_EXECUTION_NOT_AUTHORIZED", "model": MODEL,
        "identity_sha256": sha256_file(identity_path),
        "requests_path": str(request_path.relative_to(project)),
        "requests_sha256": sha256_file(request_path), "presentations": len(rows),
        "base_pairs": 80, "reversal_presentations": 16,
        "base_pair_source_sha256": sha256_file(base_path),
        "reference_trace_sha256": sha256_file(trace_path),
        "intake_sha256": sha256_file(review / "intake_result.json"),
        "closeout_sha256": sha256_file(closeout_path),
        "implementation_sha256": {p: sha256_file(project / p) for p in implementation},
        "usage_accounting_repair_sha256": sha256_file(repair_path) if repair_path.exists() else None,
        "provider_usage_policy": "Keep thinkingBudget=0 requests; record nonzero reported thinking as a provider discrepancy and charge it within the combined 256-token output cap. Do not claim observed zero thinking.",
        "provider_preflight_sha256": sha256_file(provider_path) if provider_path.exists() else None,
        "reference_protocol_change": {
            "status": "PROPOSED RESEARCH CHANGE — NOT AUTHORIZED",
            "changes": "Use original A as the recorded joint-human reference; posthoc six-case and assistant views are sensitivity only; AI B stays exploratory.",
            "reason": "Actual joint review is complete; researcher requested no further human sheets.",
            "superseded_claim": "Completion of 192 independent primary human judgements and independent inter-human agreement.",
            "reruns": "No rerating or regeneration of the existing 142 responses. Run the still-unexecuted candidate qualification with disclosed provenance.",
            "paper_claim_change": "No change to official RQ1/RQ2 capability metrics or PM claim; qualification agreement is against a joint reference.",
        },
        "stage_hard_cap_usd": "0.10", "cumulative_hard_cap_usd": "50.00",
        "max_physical_attempts_per_presentation": 2, "concurrency": 1,
        "input_accounting_allowance_tokens": 256,
        "input_accounting_note": "Provider countTokens on full request plus a fixed billing allowance; usage outside the reserved envelope stops execution for reconciliation.",
        "pricing_checked_date": "2026-09-17", "pricing_source": "https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-lite",
        "post_run": "offline taskwise agreement, order stability, equivalent recall, position diagnostics, parsing, cost and clustered uncertainty; no prompt tuning on this sample",
        "uncertainty": {"method": "cluster percentile bootstrap of exact agreement and supported-class macro recall",
                        "unit": "memory owner / ESC source dialogue", "replicates": 2000, "seed": 20260917,
                        "undefined_replicates": "report valid count; do not invent zero scores for absent classes"},
        "new_generator_calls": 0, "formal_outcomes": 0, "PM_training": 0,
        "outcome_locks": "ALL_CLOSED",
    }
    return plan, rows, references


def require_authorization(approval: dict, plan: dict) -> None:
    if approval.get("status") != "AUTHORIZED" or approval.get("researcher_approved") is not True:
        raise PermissionError("paid teacher calls await explicit researcher approval")
    if approval.get("reference_protocol_amendment_approved") is not True:
        raise PermissionError("actual joint-reference protocol has not been approved")
    if approval.get("execution_plan_sha256") != sha256_text(canonical_json(plan)):
        raise PermissionError("approval is not bound to the exact current execution plan")
    if not plan["provider_preflight_sha256"]:
        raise PermissionError("provider metadata and token preflight are required before paid execution")


def write_comparisons(output: Path, references: list[dict], results: list[dict]):
    returned = index_presentations(results)
    if not returned.keys() <= index_presentations(references).keys():
        raise ValueError("unexpected result presentation")
    views = {}
    for name in ("original_A", "human_followup", "assistant_fact_review_sensitivity"):
        rows = []
        for reference in references:
            r = dict(reference)
            result = returned.get(r["presentation_id"], {})
            r["candidate_verdict"] = result.get("parsed_verdict")
            if name == "human_followup" and "followup" in r:
                r["reference_verdict"] = r["followup"]["verdict"]
            if name == "assistant_fact_review_sensitivity" and "closeout" in r:
                r["reference_verdict"] = r["closeout"]["assistant_sensitivity_verdict"]
            rows.append(r)
        views[name] = reference_comparison(rows)
        views[name]["uncertainty_by_task"] = {
            task: clustered_agreement_interval([r for r in rows if r["task"] == task])
            for task in sorted({r["task"] for r in rows})
        }
    views["operational"] = {
        "scheduled": len(references), "completed_presentations": len(results),
        "successful_parses": sum(r["status"] == "SUCCEEDED" for r in results),
        "operational_failures": sum(r["status"] == "OPERATIONAL_FAILURE" for r in results),
        "unattempted": len(references) - len(results),
        "operational_failures_are_not_genuine_uncertain_verdicts": True,
    }
    write_json(output / "reference_comparisons.json", views)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "provider-preflight", "live"), default="offline")
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    assert_pre_outcome_locked(load_public_only_config(PROJECT / "configs/paper1_public_only.yaml"))
    output = PROJECT / "outputs/paper1_pairwise_teacher/gemini_qualification_v2"
    plan, rows, references = plan_for(PROJECT, output)
    if args.mode == "offline":
        write_json(output / "execution_plan.json", plan)
        write_json(output / "prepared_reference_trace.json", references)
        write_json(output / "authorization.pending.json", {
            "status": "PENDING", "researcher_approved": False,
            "reference_protocol_amendment_approved": False,
            "execution_plan_sha256": sha256_text(canonical_json(plan)),
        })
        print(json.dumps({"status": "OFFLINE_PLAN_READY", "plan_sha256": sha256_text(canonical_json(plan)),
                          "presentations": len(rows), "stage_hard_cap_usd": "0.10"}))
        return 0
    if args.mode == "live":
        if args.authorization is None:
            raise PermissionError("--authorization is required for live execution")
        require_authorization(read_rating_json(args.authorization), plan)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is absent; no provider request made")
    with httpx.Client(headers={"x-goog-api-key": key}, timeout=60, follow_redirects=False) as client:
        if args.mode == "provider-preflight":
            result = count_requests(client, rows, output)
            plan, _, _ = plan_for(PROJECT, output)
            write_json(output / "execution_plan.json", plan)
            print(json.dumps({"status": "PROVIDER_PREFLIGHT_COMPLETE", "token_counts": result["completed_counts"],
                              "first_attempt_reservation_sum_usd": result["first_attempt_reservation_sum_usd"],
                              "generateContent_calls": 0}))
            return 0
        ledger_path = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
        if not ledger_path.exists():
            raise RuntimeError("existing cumulative budget ledger is required")
        with ledger_path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            ledger = CumulativePaper1ApiBudgetLedger(ledger_path)
            repair_path = PROJECT / "data/paper1_authority/paper1_gemini_usage_accounting_repair_20260917_v1.json"
            repair = read_rating_json(repair_path) if repair_path.exists() else {}
            try:
                results = run_requests(client, rows, read_rating_json(output / "provider_preflight.json"),
                                       ledger, output, authorized=True,
                                       saved_settlement_reconciliations=repair.get("saved_settlement_reconciliations", {}))
            finally:
                # Preserve a partial diagnostic report even after an operational stop.
                results_path = output / "results.json"
                if results_path.exists():
                    write_comparisons(output, references, read_json(results_path))
            print(json.dumps({"status": "COMPLETED", "presentations": len(results),
                              "accounted_stage_cost_usd": str(ledger.accounted_stage_cost_usd("pairwise_teacher_qualification_v2")),
                              "accounted_total_usd": str(ledger.accounted_cost_usd)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, PermissionError, OSError) as exc:
        print(json.dumps({"status": "STOPPED", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
