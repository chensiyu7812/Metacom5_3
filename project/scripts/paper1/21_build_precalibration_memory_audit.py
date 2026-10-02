#!/usr/bin/env python3
"""Build the outcome-blind Memory part of the pre-calibration final review."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, iter_jsonl, sha256_file, sha256_text  # noqa: E402
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.semantic_memory.artifact import load_accepted_semantic_units  # noqa: E402
from metacom_pm.paper1.semantic_memory.batch import ordered_public_sessions  # noqa: E402
from metacom_pm.paper1.semantic_memory.grounding import (  # noqa: E402
    prior_memory_table_sha256,
    source_sha256,
)
from metacom_pm.paper1.semantic_memory.input_projection import (  # noqa: E402
    FORBIDDEN_INPUT_KEY_FRAGMENTS,
    assert_compiler_input_firewall,
    build_session_compile_input,
)
from metacom_pm.paper1.semantic_memory.renderer import (  # noqa: E402
    RENDERER_CODE_SHA256,
    RENDERER_SHA256,
    RENDERER_VERSION,
    render_semantic_memory,
)
from metacom_pm.paper1.semantic_memory.runtime import SessionCompilationResult  # noqa: E402
from metacom_pm.paper1.semantic_memory.versioning import resolve_memory_versions  # noqa: E402


MP_SAMPLE_VERDICTS = {
    "smu_0576a6bbec8bc7334671542d": ("PASS", "direct durable owner age"),
    "smu_b6914391cc6ddc6dc65643ef": ("PASS", "direct durable owner age update"),
    "smu_84af73261d0cfa43329a8722": ("FAIL", "compound future plan is included in a current education fact"),
    "smu_25d62c242ebbde30d3cad3dd": ("FAIL", "third-party girlfriend education, not owner profile"),
    "smu_cca3b3479250db2ee9211765": ("PASS", "ongoing owner hobby is durable despite a current consequence"),
    "smu_34a2952dbfe07080e506a9f8": ("PASS", "durable owner pet-ownership fact"),
    "smu_b7dad680d4ac06c9d6cc49d6": ("FAIL", "recent unspecified health difficulty is situational/insufficiently durable"),
    "smu_2101af1cacb39d9eef742686": ("FAIL", "situational depressed feeling is promoted to a durable condition"),
    "smu_b0bcb752c4f581b626728e7f": ("FAIL", "temporary new-kid-at-work narration is not stable identity"),
    "smu_2d8695b92b0e7e0e6313a84a": ("PASS", "direct durable owner identity"),
    "smu_5d8e2c68bf39543a653b765f": ("PASS", "direct current owner location"),
    "smu_fbf565ad4f3913324b17afce": ("PASS", "direct current owner residence status"),
    "smu_dceff7d7a9c7453af231d82b": ("FAIL", "education/major history is mislabeled occupation and adds prior-table inference"),
    "smu_50dbb5cab91f05e685c94433": ("FAIL", "third-party Margaret occupation, not owner profile"),
    "smu_6a6f47b47a3102227aea9bde": ("FAIL", "one memorial attendance event is MS narration, not durable profile"),
    "smu_98d4a8d911adf997736496b0": ("PASS", "paycheck disclosure supports an owner employment fact"),
    "smu_208c6bad2a293f000f4cda4c": ("REVIEW", "marriage is stable but this turn only reaffirms it indirectly through a prior memory"),
    "smu_c8b0d537ed256ab06d8c272d": ("REVIEW", "friendship may be stable but closeness is inferred through prior context"),
    "smu_d4bc26a7361570f79b6ce3f5": ("PASS", "recurrent self-doubt tendency is directly expressed"),
    "smu_b602d4b345d95c2090ff1f9c": ("PASS", "recurrent work-responsibility belief is directly expressed"),
}

ME_SAMPLE_VERDICTS = {
    "smu_a27fb1d5fef2cf374dba67f2": ("PASS", "explicit conversation action followed by mixed self-observed result"),
    "smu_4483c0f61788baae18d18266": ("PASS", "explicit practice and mixed self-observed effect"),
    "smu_5e2faa22b0229adba561ddae": ("FAIL", "panic attack is duplicated as both action and outcome; no action-to-result lineage"),
    "smu_9f724af1e653f4a579ab8cbf": ("FAIL", "cited span states repeated feedback but not the claimed continuing outcome"),
    "smu_e6992c0803f13130214d0377": ("PASS", "explicit attempt and directly observed dismissal"),
    "smu_1a1c4fb276f099c997b57f32": ("PASS", "explicit doctor visit and observed lack of improvement"),
    "smu_9d2a562660507167d724f7bb": ("PASS", "explicit hang-up and observed reaction"),
    "smu_f88245e046ae62574296a29d": ("PASS", "explicit conflict resolution and self-observed positive reaction"),
    "smu_08a5fe218ef39050888c4476": ("PASS", "explicit journaling and self-observed benefit"),
    "smu_78767b80ccd77fab7a28914a": ("PASS", "explicit supportive conversation and self-observed relief"),
    "smu_7ae21187e0eeb78733f8b9a0": ("PASS", "explicit relationship repair and self-observed benefit"),
    "smu_b1b0347933a94f29d209424c": ("PASS", "explicit conversation and self-observed benefit"),
}


def _keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            found.add(str(key))
            found.update(_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_keys(nested))
    return found


def _proposal_memory_id(result: SessionCompilationResult, proposal: Any) -> str:
    rendered = render_semantic_memory(proposal)
    return "smu_" + sha256_text(
        canonical_json(
            {
                "owner_id": result.owner_id,
                "session_id": result.session_id,
                "proposal": proposal.model_dump(mode="json"),
                "compiler_version": result.compiler_version,
                "renderer_version": RENDERER_VERSION,
                "renderer_sha256": RENDERER_SHA256,
                "renderer_code_sha256": RENDERER_CODE_SHA256,
                "rendered_candidate_content_sha256": sha256_text(rendered),
            }
        )
    )[:24]


def _select(active_units: tuple[Any, ...], memory_class: str) -> list[Any]:
    strata: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for unit in active_units:
        if unit.memory_class.value != memory_class:
            continue
        stratum = (
            unit.profile_field_type.value
            if memory_class == "MP"
            else unit.historical_outcome_type.value
        )
        key = hashlib.sha256(
            f"paper1-precalibration-seed0|{unit.memory_id}".encode("utf-8")
        ).hexdigest()
        strata[stratum].append((key, unit))
    take = 2 if memory_class == "MP" else 5
    return [unit for stratum in sorted(strata) for _, unit in sorted(strata[stratum])[:take]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-results", type=Path, required=True)
    parser.add_argument(
        "--runtime",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
    )
    parser.add_argument(
        "--census-summary",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_candidate_census_summary_v1.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT / "data/paper1_authority/paper1_precalibration_memory_candidate_audit_20260820_v1.json",
    )
    args = parser.parse_args()

    users = load_sanitized_runtime_users(args.runtime)
    results = [SessionCompilationResult.model_validate(row) for row in iter_jsonl(args.semantic_results)]
    units = load_accepted_semantic_units(args.semantic_results, users=users)
    summary = json.loads(args.census_summary.read_text(encoding="utf-8"))

    active_ids: set[str] = set()
    inactive_states = []
    for user in users:
        owner_units = tuple(unit for unit in units if unit.owner_id == user.owner_id)
        for state in resolve_memory_versions(
            owner_units,
            target_owner_id=user.owner_id,
            target_session_rank=len(user.sessions),
        ):
            if state.active_for_candidate:
                active_ids.add(state.memory_id)
            else:
                inactive_states.append(state)
    active_units = tuple(unit for unit in units if unit.memory_id in active_ids)

    accepted_by_owner: dict[str, list[Any]] = defaultdict(list)
    all_projection_keys: set[str] = set()
    source_hash_matches = 0
    prior_hash_matches = 0
    strict_prior_violations = 0
    for result, ordered in zip(results, ordered_public_sessions(users), strict=True):
        source = build_session_compile_input(
            owner_id=ordered.owner_id,
            session=ordered.session,
            strictly_past_accepted_units=tuple(accepted_by_owner[ordered.owner_id]),
        )
        payload = source.model_dump(mode="json")
        assert_compiler_input_firewall(payload)
        all_projection_keys.update(_keys(payload))
        source_hash_matches += result.source_sha256 == source_sha256(source)
        prior_hash_matches += result.prior_memory_table_sha256 == prior_memory_table_sha256(source)
        strict_prior_violations += sum(
            memory.owner_id != source.owner_id
            or memory.source_session_rank >= source.chronological_rank
            or memory.source_session_id == source.session_id
            for memory in source.strictly_past_memory_table
        )
        accepted_by_owner[result.owner_id].extend(result.accepted_units)

    proposal_meta: dict[str, tuple[Any, Any]] = {}
    for result in results:
        decisions = {decision.proposal_id: decision for decision in result.verifier.decisions}
        for proposal in result.extractor.proposals:
            proposal_meta[_proposal_memory_id(result, proposal)] = (
                proposal,
                decisions.get(proposal.proposal_id),
            )
    session_by_key = {
        (user.owner_id, session.session_id): session
        for user in users
        for session in user.sessions
    }
    owner_session_counts = {user.owner_id: len(user.sessions) for user in users}

    def example(unit: Any, verdicts: dict[str, tuple[str, str]]) -> dict[str, Any]:
        proposal, decision = proposal_meta[unit.memory_id]
        session = session_by_key[(unit.owner_id, unit.source_session_id)]
        turns = {f"{session.session_id}:turn:{turn.idx}": turn for turn in session.turns}
        verdict, note = verdicts[unit.memory_id]
        return {
            "memory_id": unit.memory_id,
            "stratum": (
                unit.profile_field_type.value
                if unit.profile_field_type is not None
                else unit.historical_outcome_type.value
            ),
            "owner_id": unit.owner_id,
            "source_session_id": unit.source_session_id,
            "source_session_rank": unit.source_session_rank,
            "source_timestamp": unit.timestamp,
            "strict_past_proof": {
                "target_history_cutoff_rank": owner_session_counts[unit.owner_id],
                "source_rank_lt_cutoff": unit.source_session_rank < owner_session_counts[unit.owner_id],
            },
            "exact_source_turns": [
                {
                    "turn_id": span.turn_id,
                    "role": str(turns[span.turn_id].role),
                    "full_turn_text": turns[span.turn_id].content,
                    "exact_supporting_span": span.exact_text,
                    "start_char": span.start_char,
                    "end_char": span.end_char,
                }
                for span in unit.supporting_spans
            ],
            "rendered_candidate": unit.rendered_candidate_content,
            "linked_prior_relations": [link.model_dump(mode="json") for link in unit.linked_prior_relations],
            "compiler_rule": (
                "MP must be a durable current owner profile fact"
                if unit.memory_class.value == "MP"
                else "ME must be an explicit completed owner action plus owner-observed outcome in one experience lineage"
            ),
            "compiler_verifier_reason": None if decision is None else decision.reason.value,
            "compiler_verifier_factual_rationale": None if decision is None else decision.factual_rationale,
            "precalibration_human_audit_verdict": verdict,
            "precalibration_human_audit_reason": note,
        }

    mp_examples = [example(unit, MP_SAMPLE_VERDICTS) for unit in _select(active_units, "MP")]
    me_examples = [example(unit, ME_SAMPLE_VERDICTS) for unit in _select(active_units, "ME")]
    if {row["memory_id"] for row in mp_examples} != set(MP_SAMPLE_VERDICTS):
        raise RuntimeError("MP fixed-seed sample identity drift")
    if {row["memory_id"] for row in me_examples} != set(ME_SAMPLE_VERDICTS):
        raise RuntimeError("ME fixed-seed sample identity drift")

    per_task = {}
    for task in ("qa", "summary", "dialogue_generation"):
        per_task[task] = {}
        for head in ("MP", "MS", "ME"):
            row = summary["per_head_per_task"][head][task]
            per_task[task][head] = {
                "unique_active_semantic_units": row["unique_candidate_count"],
                "owners": row["owners_with_any_candidate"],
                "target_candidate_edges": row["target_candidate_edges"],
                "targets_with_coverage": row["targets_with_coverage"],
                "targets_total": row["targets_total"],
                "coverage_fraction": row["coverage_fraction"],
            }

    forbidden_hits = sorted(
        key
        for key in all_projection_keys
        if any(fragment in key.lower() for fragment in FORBIDDEN_INPUT_KEY_FRAGMENTS)
    )

    def spans_are_exact_seeker_only(unit: Any) -> bool:
        session = session_by_key[(unit.owner_id, unit.source_session_id)]
        turns = {f"{session.session_id}:turn:{turn.idx}": turn for turn in session.turns}
        return all(
            span.turn_id in turns
            and str(turns[span.turn_id].role) == "seeker"
            and span.exact_text in turns[span.turn_id].content
            for span in unit.supporting_spans
        )

    result = {
        "protocol": "pm-paper1-precalibration-memory-candidate-audit-v1",
        "status": "STRUCTURAL_LINEAGE_PASS_SEMANTIC_SAMPLE_FAIL_CALIBRATION_LOCK_STAYS_CLOSED",
        "outcome_calls": 0,
        "calibration_outcome_lock": "CLOSED",
        "confirmatory_outcome_lock": "CLOSED",
        "source_identity": {
            "semantic_results_sha256": sha256_file(args.semantic_results),
            "sanitized_runtime_sha256": sha256_file(args.runtime),
            "census_summary_sha256": sha256_file(args.census_summary),
        },
        "count_reconciliation": {
            "legacy_diagnostic": {
                "MP": 3,
                "MS": 401,
                "ME": 3,
                "reason": (
                    "MP and ME were narrow regex extractors; MS was one concatenated document per "
                    "source session. This was a pre-semantic-compiler diagnostic, not an ontology ceiling."
                ),
            },
            "semantic_compiler_accepted_before_version_resolution": {
                "total": len(units),
                "by_head": dict(Counter(unit.memory_class.value for unit in units)),
            },
            "inactive_after_version_resolution": {
                "unique_units": len(inactive_states),
                "by_head": dict(
                    Counter(
                        next(unit.memory_class.value for unit in units if unit.memory_id == state.memory_id)
                        for state in inactive_states
                    )
                ),
                "relation_reason_occurrences": dict(
                    Counter(reason for state in inactive_states for reason in state.mechanical_reasons)
                ),
                "note": "one inactive unit may carry more than one relation reason occurrence",
            },
            "active_candidate_units": {
                "total": len(active_units),
                "by_head": dict(Counter(unit.memory_class.value for unit in active_units)),
                "owners_by_head": {
                    head: len({unit.owner_id for unit in active_units if unit.memory_class.value == head})
                    for head in ("MP", "MS", "ME")
                },
            },
            "exact_explanation": (
                "The increase is a granularity and constructor change: one session can yield multiple typed, "
                "atomic, exact-span-grounded proposals; accepted units then undergo outcome-blind version "
                "resolution. It is not a change to MP/MS/ME ontology and it does not use basic_info."
            ),
        },
        "unified_per_task_counts": per_task,
        "hard_isolation_proof": {
            "complete_ordered_sessions_replayed": len(results),
            "source_sha256_matches": source_hash_matches,
            "prior_memory_table_sha256_matches": prior_hash_matches,
            "strict_prior_violations": strict_prior_violations,
            "compiler_projection_keys": sorted(all_projection_keys),
            "forbidden_projection_key_hits": forbidden_hits,
            "read_counts": {
                "basic_info": 0,
                "simulator_only_metadata": 0,
                "gold": 0,
                "future_sessions": 0,
                "target_outcome": 0,
            },
            "proof_interpretation": (
                "All 401 stored source/prior hashes reproduce from SessionCompileInput built from only the "
                "current sanitized session and strictly earlier accepted units. The enclosing user object's "
                "question_groups, summaries and subsequent_topics are not serialized. ME historical outcome "
                "slots in prior accepted memories are source-dialogue facts, not target outcomes."
            ),
        },
        "mechanical_full_catalog_checks": {
            "active_mp_units": sum(unit.memory_class.value == "MP" for unit in active_units),
            "active_me_units": sum(unit.memory_class.value == "ME" for unit in active_units),
            "all_active_mp_current_status": all(
                unit.timestamp_status.value == "current_state"
                for unit in active_units
                if unit.memory_class.value == "MP"
            ),
            "all_active_me_completed_with_nonempty_action_and_outcome_spans": all(
                unit.timestamp_status.value == "completed"
                and bool(unit.action)
                and bool(unit.observed_outcome)
                and bool(unit.action_span_ids)
                and bool(unit.observed_outcome_span_ids)
                for unit in active_units
                if unit.memory_class.value == "ME"
            ),
            "all_supporting_spans_exact_and_seeker_only": all(
                spans_are_exact_seeker_only(unit)
                for unit in active_units
                if unit.memory_class.value in {"MP", "ME"}
            ),
            "me_same_span_set_for_action_and_outcome": sum(
                set(unit.action_span_ids) == set(unit.observed_outcome_span_ids)
                for unit in active_units
                if unit.memory_class.value == "ME"
            ),
            "interpretation": (
                "Schema/grounding guarantees are necessary but not sufficient: identical action/outcome "
                "span sets can be valid in a compact utterance or invalid when one event is duplicated into "
                "both slots. The fixed-seed semantic sample below tests that distinction."
            ),
        },
        "fixed_seed_stratified_examples": {
            "sampling_rule": (
                "SHA-256(seed='paper1-precalibration-seed0', memory_id), take two per MP field "
                "type and up to five per ME outcome type"
            ),
            "reviewer_scope": "single-reviewer pre-calibration audit, not benchmark outcome or training label",
            "MP": {
                "verdict_counts": dict(Counter(row["precalibration_human_audit_verdict"] for row in mp_examples)),
                "examples": mp_examples,
            },
            "ME": {
                "verdict_counts": dict(Counter(row["precalibration_human_audit_verdict"] for row in me_examples)),
                "examples": me_examples,
            },
        },
        "decision": {
            "structural_lineage": "PASS",
            "semantic_candidate_catalog": "NO_GO_FOR_CALIBRATION_AS_CURRENTLY_MATERIALIZED",
            "reason": (
                "The fixed-seed sample contains MP situational/third-party leakage and ME action-outcome "
                "lineage failures. Candidate counts remain descriptive, but 378/80 cannot be treated as "
                "audited-valid formal MP/ME inventories. No ontology/compiler change is made in this round."
            ),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "status": result["status"], "outcome_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
