#!/usr/bin/env python3
"""Build a text-free lineage, retry, rejection, and cost census for the 401 run."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import iter_jsonl, read_json, sha256_file, write_json
from metacom_pm.paper1.api_budget import PAPER1_KNOWN_V9_COST_USD
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory.batch import ordered_public_sessions
from metacom_pm.paper1.multi_view_memory.contracts import AcceptedEventExperienceUnit
from metacom_pm.paper1.multi_view_memory.grounding import (
    prior_profile_sha256,
    source_sha256,
)
from metacom_pm.paper1.multi_view_memory.input_projection import build_session_input
from metacom_pm.paper1.multi_view_memory.runtime import SessionCompilationResult


STAGE = "multi_view_401_compilation_and_validation"
STAGE_CAP = Decimal("1.42149913")


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            PROJECT
            / "data"
            / "paper1_public_memory"
            / "es_memeval_public_sanitized_runtime_artifact_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT / "outputs" / "paper1_multi_view_compiler_v7",
    )
    parser.add_argument(
        "--budget-ledger",
        type=Path,
        default=(
            PROJECT
            / "outputs"
            / "paper1_api_budget"
            / "cumulative_paid_api_budget.jsonl"
        ),
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _args()
    source_path = args.source.resolve()
    output_dir = args.output_dir.resolve()
    results_path = output_dir / "session_results.jsonl"
    report_path = output_dir / "batch_report.json"
    budget_path = args.budget_ledger.resolve()

    users = load_sanitized_runtime_users(source_path)
    ordered = ordered_public_sessions(users)
    rows = tuple(SessionCompilationResult.model_validate(row) for row in iter_jsonl(results_path))
    report = read_json(report_path)

    accepted_by_owner = defaultdict(list)
    memory_ids: list[str] = []
    source_checks = Counter()
    maximum_prior_profile_slots = 0
    empty_accepted_sessions = 0
    for index, row in enumerate(rows):
        expected = ordered[index]
        source = build_session_input(
            owner_id=expected.owner_id,
            session=expected.session,
            strictly_past_units=tuple(accepted_by_owner[expected.owner_id]),
        )
        maximum_prior_profile_slots = max(
            maximum_prior_profile_slots, len(source.prior_current_profile)
        )
        source_checks["ordered_owner_session"] += (
            (row.owner_id, row.session_id)
            == (expected.owner_id, expected.session.session_id)
        )
        source_checks["source_sha256"] += row.source_sha256 == source_sha256(source)
        source_checks["prior_profile_sha256"] += (
            row.prior_profile_sha256 == prior_profile_sha256(source)
        )
        turns = {turn.turn_id: turn for turn in source.turns}
        if not row.accepted_units:
            empty_accepted_sessions += 1
        for unit in row.accepted_units:
            memory_ids.append(unit.memory_id)
            source_checks["unit_owner_session_rank_timestamp"] += (
                unit.owner_id == row.owner_id
                and unit.source_session_id == row.session_id
                and unit.source_session_rank == expected.session.chronological_rank
                and unit.timestamp == expected.session.timestamp
                and unit.compiler_identity_sha256 == report["compiler_identity_sha256"]
            )
            for span in unit.supporting_spans:
                turn = turns.get(span.turn_id)
                source_checks["span_exact_complete_seeker_turn"] += (
                    turn is not None
                    and turn.role == "seeker"
                    and span.turn_index == turn.turn_index
                    and span.exact_text == turn.content
                    and span.start_char == 0
                    and span.end_char == len(turn.content)
                )
        source_checks["all_grounding_valid"] += all(
            bool(item["valid"]) for item in row.grounding
        )
        accepted_by_owner[row.owner_id].extend(row.accepted_units)

    attempts = Counter()
    terminal = Counter()
    active_logical_calls: set[str] = set()
    recovered_retry_calls = 0
    exhausted_failed_calls = 0
    for path in sorted((output_dir / "attempts").glob("*/*.jsonl")):
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        call_key = str(events[0]["call_key"])
        active_logical_calls.add(call_key)
        started = [event for event in events if event["event"] == "STARTED"]
        attempts[path.parent.name] += len(started)
        for event in events:
            if event["event"] in {"SUCCEEDED", "FAILED"}:
                terminal[event["event"]] += 1
        terminal_events = [event["event"] for event in events if event["event"] != "STARTED"]
        recovered_retry_calls += terminal_events == ["FAILED", "SUCCEEDED"]
        exhausted_failed_calls += terminal_events == ["FAILED", "FAILED"]

    stage_cost = Decimal("0")
    active_cost = Decimal("0")
    all_new_cost = Decimal("0")
    unknown_cost = Decimal("0")
    unknown_settlements = 0
    for event in iter_jsonl(budget_path):
        if event.get("event") != "SETTLED":
            continue
        cost = Decimal(str(event["actual_cost_usd"]))
        all_new_cost += cost
        if event.get("stage") == STAGE:
            stage_cost += cost
        if event.get("logical_call_id") in active_logical_calls:
            active_cost += cost
        if event.get("accounting") == "unknown_cost_charged_at_reserved_maximum":
            unknown_settlements += 1
            unknown_cost += cost

    units = [unit for row in rows for unit in row.accepted_units]
    profile_units = [unit for unit in units if not isinstance(unit, AcceptedEventExperienceUnit)]
    event_units = [unit for unit in units if isinstance(unit, AcceptedEventExperienceUnit)]
    violation_counts = Counter(
        violation
        for row in rows
        for rejection in row.schema_rejections
        for violation in rejection.violations
    )
    schema_phase_counts = Counter(
        rejection.phase for row in rows for rejection in row.schema_rejections
    )
    final_profile_slots = sum(
        len(
            {
                unit.profile_slot_key
                for unit in owner_units
                if not isinstance(unit, AcceptedEventExperienceUnit)
            }
        )
        for owner_units in accepted_by_owner.values()
    )

    checks = {
        "exact_401_prefix": len(rows) == len(ordered) == 401,
        "exact_18_owners": len({row.owner_id for row in rows}) == len(users) == 18,
        "batch_report_complete": report["status"] == "COMPLETE",
        "batch_report_result_hash": report["session_results_sha256"]
        == sha256_file(results_path),
        "all_order_source_prior_checks": all(
            source_checks[name] == len(rows)
            for name in (
                "ordered_owner_session",
                "source_sha256",
                "prior_profile_sha256",
                "all_grounding_valid",
            )
        ),
        "all_unit_bindings": source_checks["unit_owner_session_rank_timestamp"]
        == len(units),
        "all_spans_exact_complete_seeker_turns": source_checks[
            "span_exact_complete_seeker_turn"
        ]
        == sum(len(unit.supporting_spans) for unit in units),
        "memory_ids_unique": len(memory_ids) == len(set(memory_ids)),
        "active_logical_calls_complete": len(active_logical_calls) == 802,
        "active_successes_complete": terminal["SUCCEEDED"] == 802,
        "no_exhausted_failed_call": exhausted_failed_calls == 0,
        "active_success_cache_complete": len(
            list((output_dir / "success_cache").glob("*/*.json"))
        )
        == 802,
        "stage_cost_within_researcher_cap": stage_cost <= STAGE_CAP,
        "formal_outcome_calls_zero": report["formal_outcome_calls"] == 0,
        "pm_training_runs_zero": report["pm_training_runs"] == 0,
    }
    closeout = {
        "protocol": "paper1-multi-view-401-closeout-census-v1",
        "status": "COMPLETE_CENSUS_PASS" if all(checks.values()) else "CENSUS_FAIL",
        "checks": checks,
        "identity": {
            "compiler_identity_sha256": report["compiler_identity_sha256"],
            "source_sha256": sha256_file(source_path),
            "session_results_sha256": sha256_file(results_path),
            "batch_report_sha256": sha256_file(report_path),
        },
        "coverage": {
            "owners": len(users),
            "sessions": len(rows),
            "accepted_units": len(units),
            "accepted_MP": len(profile_units),
            "accepted_ME": len(event_units),
            "empty_accepted_sessions": empty_accepted_sessions,
            "final_exact_profile_slot_keys": final_profile_slots,
            "maximum_prior_profile_slots": maximum_prior_profile_slots,
            "MP_type_counts": dict(
                sorted(Counter(unit.profile_field_type.value for unit in profile_units).items())
            ),
            "ME_type_counts": dict(
                sorted(Counter(unit.event_experience_type.value for unit in event_units).items())
            ),
        },
        "rejections_are_retained_results_not_pass_gates": {
            "schema_rejections": sum(len(row.schema_rejections) for row in rows),
            "schema_phase_counts": dict(sorted(schema_phase_counts.items())),
            "violation_counts": dict(sorted(violation_counts.items())),
            "grounding_rejections": sum(
                sum(not bool(item["valid"]) for item in row.grounding) for row in rows
            ),
            "semantic_rejections": sum(len(row.rejected_decisions) for row in rows),
        },
        "attempts": {
            "logical_calls": len(active_logical_calls),
            "physical_attempts": sum(attempts.values()),
            "extractor_physical_attempts": attempts["extractor"],
            "verifier_physical_attempts": attempts["verifier"],
            "successful_terminal_attempts": terminal["SUCCEEDED"],
            "failed_terminal_attempts": terminal["FAILED"],
            "recovered_retry_calls": recovered_retry_calls,
            "exhausted_failed_calls": exhausted_failed_calls,
        },
        "budget_usd": {
            "active_v8_v9_cost": str(active_cost),
            "compiler_stage_all_versions_cost": str(stage_cost),
            "compiler_stage_authorized_cap": str(STAGE_CAP),
            "compiler_stage_remaining": str(STAGE_CAP - stage_cost),
            "unknown_settlements": unknown_settlements,
            "unknown_cost_charged_at_reserved_maximum": str(unknown_cost),
            "all_new_paper1_ledger_cost": str(all_new_cost),
            "opening_v9_cost": str(PAPER1_KNOWN_V9_COST_USD),
            "paper1_accounted_total": str(all_new_cost + PAPER1_KNOWN_V9_COST_USD),
        },
        "method_boundary": {
            "authority_artifact_contains_dialogue_text": False,
            "formal_outcome_calls": 0,
            "pm_training_runs": 0,
            "capability_outcome_used_for_compiler_changes": False,
            "schema_and_semantic_rejections_preserved": True,
        },
        "pre_outcome_transport_amendments": [
            {
                "sequence": "V1",
                "observation": "1024-token extractor response was truncated",
                "resolution": "introduced compact JSON transport",
            },
            {
                "sequence": "V2",
                "observation": "provider uppercased structural JSON keys",
                "resolution": "case-normalized only schema structural keys",
            },
            {
                "sequence": "V3",
                "observation": "JSON-object mode required an explicit JSON instruction",
                "resolution": "added the explicit instruction and message-template hashes",
            },
            {
                "sequence": "V4-V5",
                "observation": "dense sessions still truncated duplicated evidence text",
                "resolution": (
                    "model emits seeker turn IDs; runtime restores exact complete seeker turns"
                ),
            },
            {
                "sequence": "V6-V7",
                "observation": "dense prior-profile context exceeded narrow local allowances",
                "resolution": (
                    "compacted prior-profile transport and widened the outcome-blind context "
                    "allowance"
                ),
            },
            {
                "sequence": "V8-V9",
                "observation": "two independent provider read timeouts",
                "resolution": (
                    "preserved compiler identity and allowed one separately budgeted, "
                    "append-only retry per logical call"
                ),
            },
        ],
    }
    write_json(args.out.resolve(), closeout)
    print(json.dumps(closeout, ensure_ascii=False, indent=2))
    return 0 if closeout["status"] == "COMPLETE_CENSUS_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
