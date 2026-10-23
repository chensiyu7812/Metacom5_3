#!/usr/bin/env python3
"""Promote the completed 401 result and build a zero-outcome MP/ME/MS census."""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import read_json, sha256_file, sha256_text, write_json, write_jsonl
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle
from metacom_pm.paper1.contracts import CandidateRecord, Head, TaskType
from metacom_pm.paper1.data.memory_source import (
    MemorySourceUser,
    Target,
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.llama_tokenizer import (
    LLAMA_TOKENIZER_JSON_SHA256,
    LLAMA_TOKENIZER_REPO,
    LLAMA_TOKENIZER_REVISION,
    build_llama_token_counter,
)
from metacom_pm.paper1.multi_view_memory import (
    AcceptedEventExperienceUnit,
    AcceptedProfileViewUnit,
    load_accepted_multi_view_units,
)


HEAD_ORDER = (Head.MP, Head.MS, Head.ME)


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
        "--session-results",
        type=Path,
        default=(
            PROJECT
            / "outputs"
            / "paper1_multi_view_compiler_v7"
            / "session_results.jsonl"
        ),
    )
    parser.add_argument(
        "--closeout",
        type=Path,
        default=(
            PROJECT
            / "data"
            / "paper1_authority"
            / "paper1_multi_view_401_closeout_20260903_v1.json"
        ),
    )
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT / "data" / "paper1_public_memory",
    )
    return parser.parse_args()


def _nearest_rank(values: list[int], probability: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _distribution(values: Iterable[int]) -> dict[str, int | float | None]:
    rows = list(values)
    return {
        "count": len(rows),
        "sum": sum(rows),
        "min": min(rows, default=None),
        "median": statistics.median(rows) if rows else None,
        "p95_nearest_rank": _nearest_rank(rows, 0.95),
        "max": max(rows, default=None),
    }


def _coverage(
    targets: tuple[Target, ...],
    bundles: dict[str, dict[Head, tuple[CandidateRecord, ...]]],
) -> dict[str, Any]:
    def aggregate(rows: list[Target], head: Head) -> dict[str, Any]:
        counts = [len(bundles[target.owner_id][head]) for target in rows]
        covered = sum(count > 0 for count in counts)
        return {
            "targets": len(rows),
            "targets_with_candidates": covered,
            "coverage_fraction": covered / len(rows) if rows else None,
            "candidate_count": _distribution(counts),
            "full_pool_token_count": _distribution(
                sum(candidate.token_count for candidate in bundles[target.owner_id][head])
                for target in rows
            ),
        }

    return {
        "per_head": {
            head.value: aggregate(list(targets), head) for head in HEAD_ORDER
        },
        "per_head_per_task": {
            head.value: {
                task.value: aggregate(
                    [target for target in targets if target.task_type is task], head
                )
                for task in TaskType
                if task is not TaskType.ESC_RESPONSE
            }
            for head in HEAD_ORDER
        },
    }


def _profile_revision_census(
    units: tuple[AcceptedProfileViewUnit | AcceptedEventExperienceUnit, ...],
) -> dict[str, Any]:
    profiles = [unit for unit in units if isinstance(unit, AcceptedProfileViewUnit)]
    by_slot: dict[tuple[str, str], list[AcceptedProfileViewUnit]] = defaultdict(list)
    for unit in profiles:
        by_slot[(unit.owner_id, unit.profile_slot_key)].append(unit)

    multi_observation = 0
    value_change = 0
    repeated_same_value = 0
    any_same_rank_collision = 0
    current_same_rank_collision = 0
    current_candidates = 0
    superseded_units = 0
    for slot_units in by_slot.values():
        if len(slot_units) > 1:
            multi_observation += 1
        distinct_values = {unit.normalized_value for unit in slot_units}
        if len(distinct_values) > 1:
            value_change += 1
        elif len(slot_units) > 1:
            repeated_same_value += 1
        by_rank: dict[int, set[str]] = defaultdict(set)
        for unit in slot_units:
            by_rank[unit.source_session_rank].add(unit.normalized_value)
        any_same_rank_collision += any(len(values) > 1 for values in by_rank.values())
        latest_rank = max(by_rank)
        latest_units = [
            unit for unit in slot_units if unit.source_session_rank == latest_rank
        ]
        current_candidates += len(latest_units)
        superseded_units += len(slot_units) - len(latest_units)
        current_same_rank_collision += len(by_rank[latest_rank]) > 1

    return {
        "definition": (
            "exact owner_id + profile_slot_key; latest source_session_rank is the "
            "target-time current view, with no semantic merging"
        ),
        "accepted_historical_MP_units": len(profiles),
        "exact_owner_slot_keys": len(by_slot),
        "current_view_MP_candidates": current_candidates,
        "historical_units_not_in_current_view": superseded_units,
        "slots_with_multiple_observations": multi_observation,
        "slots_with_multiple_distinct_values": value_change,
        "slots_with_repeated_same_value_only": repeated_same_value,
        "slots_with_any_same_rank_distinct_value_collision": any_same_rank_collision,
        "current_view_same_rank_distinct_value_collision_slots": (
            current_same_rank_collision
        ),
    }


def _lineage_census(
    bundles: dict[str, dict[Head, tuple[CandidateRecord, ...]]],
    units: tuple[AcceptedProfileViewUnit | AcceptedEventExperienceUnit, ...],
) -> dict[str, Any]:
    by_head = {
        head: [candidate for bundle in bundles.values() for candidate in bundle[head]]
        for head in HEAD_ORDER
    }
    span_ids: dict[Head, set[str]] = {Head.MP: set(), Head.ME: set(), Head.MS: set()}
    source_sessions: dict[Head, set[tuple[str, str]]] = {
        head: set() for head in HEAD_ORDER
    }
    owner_binding_valid = True
    for owner_id, bundle in bundles.items():
        for head in HEAD_ORDER:
            owner_binding_valid = owner_binding_valid and all(
                candidate.lineage.owner_id == owner_id for candidate in bundle[head]
            )
    for head, candidates in by_head.items():
        for candidate in candidates:
            ids = candidate.lineage.source_record_ids
            if head is Head.MS:
                source_sessions[head].add((candidate.lineage.owner_id, ids[0]))
            else:
                source_sessions[head].add((candidate.lineage.owner_id, ids[1]))
                span_ids[head].update(ids[2:])
    source_turns = {
        Head.MP: {
            (unit.owner_id, unit.source_session_id, span.turn_id)
            for unit in units
            if isinstance(unit, AcceptedProfileViewUnit)
            for span in unit.supporting_spans
        },
        Head.ME: {
            (unit.owner_id, unit.source_session_id, span.turn_id)
            for unit in units
            if isinstance(unit, AcceptedEventExperienceUnit)
            for span in unit.supporting_spans
        },
    }
    all_candidates = [candidate for rows in by_head.values() for candidate in rows]
    return {
        "candidate_ids_unique": len({row.candidate_id for row in all_candidates})
        == len(all_candidates),
        "all_owner_bound": owner_binding_valid,
        "all_strict_past": all(row.lineage.strict_past is True for row in all_candidates),
        "all_content_hashes_match": all(
            sha256_text(row.content) == row.lineage.content_sha256
            for row in all_candidates
        ),
        "distinct_source_sessions": {
            head.value: len(source_sessions[head]) for head in HEAD_ORDER
        },
        "distinct_current_candidate_lineage_span_ids": {
            Head.MP.value: len(span_ids[Head.MP]),
            Head.ME.value: len(span_ids[Head.ME]),
        },
        "distinct_accepted_unit_grounded_source_turns": {
            Head.MP.value: len(source_turns[Head.MP]),
            Head.ME.value: len(source_turns[Head.ME]),
        },
        "MP_ME_shared_grounded_source_turns": len(
            source_turns[Head.MP] & source_turns[Head.ME]
        ),
    }


def main() -> int:
    args = _args()
    source_path = args.source.resolve()
    results_path = args.session_results.resolve()
    closeout_path = args.closeout.resolve()
    out_dir = args.out_dir.resolve()
    closeout = read_json(closeout_path)
    if closeout["status"] != "COMPLETE_CENSUS_PASS":
        raise RuntimeError("the 401-session compiler closeout is not complete")
    if sha256_file(results_path) != closeout["identity"]["session_results_sha256"]:
        raise RuntimeError("session result bytes do not match the frozen closeout")

    users = load_sanitized_runtime_users(source_path)
    targets = enumerate_targets(users)
    units = load_accepted_multi_view_units(results_path, users=users)
    token_counter = build_llama_token_counter(args.tokenizer_json.resolve())
    users_by_owner: dict[str, MemorySourceUser] = {
        user.owner_id: user for user in users
    }
    targets_by_owner: dict[str, list[Target]] = defaultdict(list)
    for target in targets:
        targets_by_owner[target.owner_id].append(target)
    units_by_owner: dict[str, list[Any]] = defaultdict(list)
    for unit in units:
        units_by_owner[unit.owner_id].append(unit)

    bundles: dict[str, dict[Head, tuple[CandidateRecord, ...]]] = {}
    for owner_id, user in users_by_owner.items():
        owner_targets = targets_by_owner[owner_id]
        if not owner_targets:
            raise RuntimeError(f"owner has no evaluation targets: {owner_id}")
        if any(target.cutoff_rank != len(user.sessions) for target in owner_targets):
            raise RuntimeError("target cutoff does not equal the official full-history boundary")
        bundles[owner_id] = compile_multi_view_candidate_bundle(
            tuple(units_by_owner[owner_id]),
            user,
            owner_targets[0],
            token_counter=token_counter,
        )

    promoted_path = out_dir / "es_memeval_public_multi_view_session_results_v1.jsonl"
    promoted_path.parent.mkdir(parents=True, exist_ok=True)
    result_bytes = results_path.read_bytes()
    if not promoted_path.exists() or promoted_path.read_bytes() != result_bytes:
        promoted_path.write_bytes(result_bytes)

    pool_rows = []
    for owner_id in sorted(bundles):
        for head in HEAD_ORDER:
            for candidate in bundles[owner_id][head]:
                pool_rows.append(
                    {
                        "protocol": "paper1-multi-view-eligible-candidate-v1",
                        "candidate_id": candidate.candidate_id,
                        "head": head.value,
                        "owner_id": owner_id,
                        "token_count": candidate.token_count,
                        "observed_at": candidate.lineage.observed_at,
                        "content_sha256": candidate.lineage.content_sha256,
                        "source_record_ids": candidate.lineage.source_record_ids,
                        "strict_past": candidate.lineage.strict_past,
                        "raw_descriptors": candidate.raw_descriptors,
                    }
                )
    pool_path = out_dir / "es_memeval_public_multi_view_candidate_pool_v1.jsonl"
    write_jsonl(pool_path, pool_rows)

    target_rows = [
        {
            "protocol": "paper1-multi-view-target-head-coverage-v1",
            "target_id": target.target_id,
            "task_type": target.task_type.value,
            "owner_id": target.owner_id,
            "head": head.value,
            "candidate_count": len(bundles[target.owner_id][head]),
            "coverage": bool(bundles[target.owner_id][head]),
        }
        for target in targets
        for head in HEAD_ORDER
    ]
    target_path = out_dir / "es_memeval_public_multi_view_target_head_census_v1.jsonl"
    write_jsonl(target_path, target_rows)

    candidate_rows_by_head = {
        head: [
            candidate
            for bundle in bundles.values()
            for candidate in bundle[head]
        ]
        for head in HEAD_ORDER
    }
    summary = {
        "protocol": "paper1-multi-view-candidate-census-v1",
        "status": "ZERO_OUTCOME_MULTI_VIEW_CANDIDATE_CENSUS_COMPLETE",
        "source": {
            "sanitized_runtime_sha256": sha256_file(source_path),
            "compiler_closeout_sha256": sha256_file(closeout_path),
            "promoted_session_results_filename": promoted_path.name,
            "promoted_session_results_sha256": sha256_file(promoted_path),
            "accepted_units": len(units),
        },
        "tokenizer": {
            "repo_id": LLAMA_TOKENIZER_REPO,
            "revision": LLAMA_TOKENIZER_REVISION,
            "tokenizer_json_sha256": LLAMA_TOKENIZER_JSON_SHA256,
            "counting_surface": "candidate content only; no chat template",
            "p95_method": "nearest-rank",
        },
        "population": {
            "owners": len(users),
            "sessions": sum(len(user.sessions) for user in users),
            "targets": len(targets),
            "targets_by_task": dict(
                sorted(Counter(target.task_type.value for target in targets).items())
            ),
        },
        "eligible_pool": {
            head.value: {
                "candidates": len(candidate_rows_by_head[head]),
                "owners_with_candidates": sum(
                    bool(bundle[head]) for bundle in bundles.values()
                ),
                "candidate_token_count": _distribution(
                    candidate.token_count for candidate in candidate_rows_by_head[head]
                ),
                "owner_full_pool_token_count": _distribution(
                    sum(candidate.token_count for candidate in bundle[head])
                    for bundle in bundles.values()
                ),
            }
            for head in HEAD_ORDER
        },
        "target_coverage": _coverage(targets, bundles),
        "profile_exact_slot_revision_census": _profile_revision_census(units),
        "source_lineage_census": _lineage_census(bundles, units),
        "artifacts": {
            "candidate_pool": {
                "filename": pool_path.name,
                "rows": len(pool_rows),
                "sha256": sha256_file(pool_path),
                "contains_candidate_text": False,
            },
            "target_head_census": {
                "filename": target_path.name,
                "rows": len(target_rows),
                "sha256": sha256_file(target_path),
                "contains_query_or_candidate_text": False,
            },
        },
        "method_boundary": {
            "formal_outcome_calls": 0,
            "pm_training_runs": 0,
            "paid_api_calls": 0,
            "top_k_or_final_bundle_selected": False,
            "compiler_retuning_from_census_forbidden": True,
            "full_eligible_pool_tokens_are_not_deployment_prompt_tokens": True,
            "promoted_result_contains_public_dialogue_derived_text": True,
            "evaluation_gold_or_capability_outcome_present": False,
        },
    }
    summary_path = out_dir / "es_memeval_public_multi_view_candidate_census_summary_v1.json"
    write_json(summary_path, summary)
    build_report = {
        "protocol": "paper1-multi-view-candidate-census-build-report-v1",
        "status": summary["status"],
        "summary_filename": summary_path.name,
        "summary_sha256": sha256_file(summary_path),
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "paid_api_calls": 0,
    }
    write_json(
        out_dir / "es_memeval_public_multi_view_candidate_census_build_report_v1.json",
        build_report,
    )
    print(summary_path)
    print(summary["eligible_pool"])
    print(summary["profile_exact_slot_revision_census"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
