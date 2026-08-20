#!/usr/bin/env python3
"""Build zero-outcome memory precision, MS-audit and held-out plans."""

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

from metacom_pm.io import canonical_json, sha256_file, sha256_text  # noqa: E402
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.semantic_memory.artifact import load_accepted_semantic_units  # noqa: E402
from metacom_pm.paper1.semantic_memory.precision_qualification import (  # noqa: E402
    MEPrecisionDecision,
    MPPrecisionDecision,
    MSSemanticAuditDecision,
    PRECISION_EXTRACTOR_PROMPT_SHA256,
    PRECISION_EXTRACTOR_SYSTEM_PROMPT,
    PRECISION_GROUNDING_VERSION,
    PRECISION_SCHEMA_VERSION,
    PRECISION_VERIFIER_PROMPT_SHA256,
    PRECISION_VERIFIER_SYSTEM_PROMPT,
)
from metacom_pm.paper1.semantic_memory.versioning import resolve_memory_versions  # noqa: E402


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _schema_hash(model: type) -> str:
    return sha256_text(canonical_json(model.model_json_schema()))


def _expected_gate(reason: str, memory_class: str) -> list[str]:
    lowered = reason.lower()
    gates: list[str] = []
    if "third-party" in lowered:
        gates.append("owner_subject_direct/action_is_owner")
    if "future" in lowered:
        gates.append("future_plan")
    if any(word in lowered for word in ("situational", "temporary", "event is ms", "memorial")):
        gates.append("episodic_or_transient")
    if any(word in lowered for word in ("prior", "inferred")):
        gates.append("requires_prior_inference")
    if "mislabeled" in lowered:
        gates.append("field_type_mismatch")
    if "panic" in lowered or "duplicated as both" in lowered:
        gates.append("same_predicate")
    if "not the claimed" in lowered or "no action-to-result" in lowered:
        gates.append("direct_entailment_or_experience_linkage")
    if not gates and memory_class == "MP":
        gates.append("direct_entailment_durability_current_validity")
    if not gates and memory_class == "ME":
        gates.append("agentive_action_user_observed_outcome_same_lineage")
    return sorted(set(gates))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-results", type=Path, required=True)
    parser.add_argument(
        "--runtime",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
    )
    parser.add_argument(
        "--old-dev-audit",
        type=Path,
        default=PROJECT / "data/paper1_authority/paper1_precalibration_memory_candidate_audit_20260820_v1.json",
    )
    args = parser.parse_args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    precision_path = PROJECT / "data/paper1_authority/paper1_semantic_memory_precision_repair_v7_20260820.json"
    regression_path = PROJECT / "data/paper1_authority/paper1_semantic_memory_old_dev_regression_v7_20260820.json"
    ms_path = PROJECT / "data/paper1_authority/paper1_ms_semantic_audit_packet_20260820_v1.json"
    plan_path = PROJECT / "data/paper1_authority/paper1_memory_heldout_requalification_plan_20260820_v1.json"

    schema_identity = {
        "MPPrecisionDecision": _schema_hash(MPPrecisionDecision),
        "MEPrecisionDecision": _schema_hash(MEPrecisionDecision),
        "MSSemanticAuditDecision": _schema_hash(MSSemanticAuditDecision),
    }
    precision = {
        "protocol": "pm-paper1-semantic-memory-precision-repair-v7",
        "status": "IMPLEMENTATION_PENDING",
        "interpretation": (
            "General prompt/schema/deterministic gates are implemented and unit-tested, but the live v6 "
            "runtime is intentionally not relabeled. Runtime migration, new authorization and held-out "
            "Qwen qualification remain required before any repaired catalog can be called READY."
        ),
        "preserved": {
            "model": "qwen3-235b-a22b-instruct-2507",
            "ontology": ["MP", "MS", "ME"],
            "quantity_target": None,
            "sample_blacklist": False,
        },
        "versions": {
            "schema": PRECISION_SCHEMA_VERSION,
            "grounding": PRECISION_GROUNDING_VERSION,
        },
        "prompt": {
            "extractor_system": PRECISION_EXTRACTOR_SYSTEM_PROMPT,
            "extractor_sha256": PRECISION_EXTRACTOR_PROMPT_SHA256,
            "verifier_system": PRECISION_VERIFIER_SYSTEM_PROMPT,
            "verifier_sha256": PRECISION_VERIFIER_PROMPT_SHA256,
        },
        "schemas": {
            "sha256": schema_identity,
            "MPPrecisionDecision": MPPrecisionDecision.model_json_schema(),
            "MEPrecisionDecision": MEPrecisionDecision.model_json_schema(),
            "MSSemanticAuditDecision": MSSemanticAuditDecision.model_json_schema(),
        },
        "MP_general_rules": [
            "direct current seeker-span entailment; prior is disambiguation only",
            "owner subject direct; reject third-party profile",
            "reject transient episodic narration and future plans",
            "health requires recurrent diagnosed or currently-persistent evidence",
            "stable social role requires direct current role evidence",
            "occupation and education remain separate closed fields",
            "other_durable_profile is fail-closed without direct durability/current-validity evidence",
        ],
        "ME_general_rules": [
            "completed agentive owner action",
            "semantically distinct later user-observed outcome",
            "same experience lineage",
            "reject same-predicate symptom duplicated as action and outcome",
            "reject third-party future hypothetical purpose prediction and unresolved lineage",
        ],
        "MS_general_rules": [
            "strict-past owner episodic or continuity event/state/change",
            "traceable event/thread",
            "exclude profile greeting trivia future current and malformed ME",
        ],
        "outcome_calls": 0,
    }
    _write(precision_path, precision)

    old = json.loads(args.old_dev_audit.read_text(encoding="utf-8"))
    replay_rows = []
    for memory_class in ("MP", "ME"):
        for row in old["fixed_seed_stratified_examples"][memory_class]["examples"]:
            old_verdict = row["precalibration_human_audit_verdict"]
            replay_rows.append(
                {
                    "memory_id": row["memory_id"],
                    "memory_class": memory_class,
                    "old_dev_verdict": old_verdict,
                    "old_dev_reason": row["precalibration_human_audit_reason"],
                    "expected_v7_disposition": "ACCEPT" if old_verdict == "PASS" else "REJECT_FAIL_CLOSED",
                    "general_gate_coverage": _expected_gate(
                        row["precalibration_human_audit_reason"], memory_class
                    ),
                    "live_qwen_v7_result": None,
                }
            )
    regression = {
        "protocol": "pm-paper1-semantic-memory-old-dev-regression-v7",
        "status": "READY",
        "scope": "DEV_EXPECTATION_AND_GENERIC_GATE_COVERAGE_ONLY_NOT_HELDOUT_QUALIFICATION",
        "source_audit_sha256": sha256_file(args.old_dev_audit),
        "counts": {
            "MP": Counter(row["old_dev_verdict"] for row in replay_rows if row["memory_class"] == "MP"),
            "ME": Counter(row["old_dev_verdict"] for row in replay_rows if row["memory_class"] == "ME"),
            "total": len(replay_rows),
        },
        "important_limit": (
            "These 32 previously inspected items only verify that the new general fields/gates express "
            "the known failure modes. No v7 Qwen response has been generated, so this is not evidence "
            "that Qwen now classifies them correctly and not final qualification."
        ),
        "rows": replay_rows,
        "outcome_calls": 0,
    }
    _write(regression_path, regression)

    users = load_sanitized_runtime_users(args.runtime)
    units = load_accepted_semantic_units(args.semantic_results, users=users)
    active_ids: set[str] = set()
    for user in users:
        owner_units = tuple(unit for unit in units if unit.owner_id == user.owner_id)
        active_ids.update(
            state.memory_id
            for state in resolve_memory_versions(
                owner_units,
                target_owner_id=user.owner_id,
                target_session_rank=len(user.sessions),
            )
            if state.active_for_candidate
        )
    active_ms = [
        unit for unit in units if unit.memory_id in active_ids and unit.memory_class.value == "MS"
    ]
    session_by_key = {
        (user.owner_id, session.session_id): session
        for user in users
        for session in user.sessions
    }
    owner_session_counts = {user.owner_id: len(user.sessions) for user in users}
    strata: dict[str, list[Any]] = defaultdict(list)
    for unit in active_ms:
        stratum = f"{unit.continuity_type.value}__{unit.timestamp_status.value}"
        strata[stratum].append(unit)
    selected = []
    seed = "paper1-ms-semantic-dev-audit-seed-20260820-v1"
    for stratum in sorted(strata):
        ranked = sorted(
            strata[stratum],
            key=lambda unit: hashlib.sha256(f"{seed}|{unit.memory_id}".encode()).hexdigest(),
        )
        selected.extend(ranked[:12])
    rows = []
    for unit in selected:
        session = session_by_key[(unit.owner_id, unit.source_session_id)]
        turns = {f"{session.session_id}:turn:{turn.idx}": turn for turn in session.turns}
        rows.append(
            {
                "audit_item_id": "ms_audit_" + sha256_text(seed + "|" + unit.memory_id)[:24],
                "memory_id": unit.memory_id,
                "owner_id": unit.owner_id,
                "source_session_id": unit.source_session_id,
                "source_session_rank": unit.source_session_rank,
                "source_timestamp": unit.timestamp,
                "continuity_type": unit.continuity_type.value,
                "timestamp_status": unit.timestamp_status.value,
                "strict_past_proof": {
                    "audit_target_cutoff_rank": owner_session_counts[unit.owner_id],
                    "source_rank_lt_cutoff": unit.source_session_rank < owner_session_counts[unit.owner_id],
                },
                "exact_source_turns": [
                    {
                        "turn_id": span.turn_id,
                        "role": str(turns[span.turn_id].role),
                        "full_turn_text": turns[span.turn_id].content,
                        "exact_supporting_span": span.exact_text,
                    }
                    for span in unit.supporting_spans
                ],
                "rendered_candidate": unit.rendered_candidate_content,
                "linked_prior_relations": [link.model_dump(mode="json") for link in unit.linked_prior_relations],
                "human_labels": None,
            }
        )
    ms_packet = {
        "protocol": "pm-paper1-ms-semantic-audit-packet-v1",
        "status": "AUDIT_REQUIRED",
        "scope": "DEV_SEMANTIC_AUDIT_PACKET_NOT_HELDOUT_QUALIFICATION",
        "source": {
            "semantic_results_sha256": sha256_file(args.semantic_results),
            "runtime_sha256": sha256_file(args.runtime),
            "active_MS_units": len(active_ms),
        },
        "sampling": {
            "seed": seed,
            "rule": "SHA256(seed,memory_id), up to 12 per observed continuity_type x timestamp_status stratum",
            "population_by_stratum": dict(Counter(f"{u.continuity_type.value}__{u.timestamp_status.value}" for u in active_ms)),
            "sample_by_stratum": dict(Counter(f"{u.continuity_type.value}__{u.timestamp_status.value}" for u in selected)),
        },
        "rubric": {
            "accept_only_if": [
                "owner-authored event/state/change",
                "strictly prior at target",
                "traceable event or continuity thread",
                "not profile greeting trivia future current or malformed ME",
            ],
            "labels": ["VALID_MS", "WRONG_CLASS", "NOT_TRACEABLE", "CURRENT_OR_FUTURE", "TRIVIA_OR_GREETING", "MALFORMED_ME", "UNCERTAIN"],
            "LLM_may_replace_human": False,
        },
        "rows": rows,
        "outcome_calls": 0,
    }
    _write(ms_path, ms_packet)

    old_dev_ids = [row["memory_id"] for row in replay_rows]
    heldout_plan = {
        "protocol": "pm-paper1-memory-heldout-requalification-plan-v1",
        "status": "READY",
        "qualification_ids_status": "IMPLEMENTATION_PENDING_UNTIL_V7_RUNTIME_REPAIR_IS_BOUND_AND_COMPILE_COMPLETES",
        "selection_timing": "freeze IDs only after repaired catalog exists",
        "exclusions": {
            "old_seed0_dev_memory_ids": old_dev_ids,
            "old_seed0_dev_count": len(old_dev_ids),
            "synthetic_items": "forbidden",
        },
        "lanes": {
            "MP": {
                "planned_N": 60,
                "strata": "6 per each of 10 closed profile_field_type values when naturally available; shortfall reported, never synthetically filled",
                "future_seed": "paper1-memory-heldout-mp-v7-seed0-after-catalog-hash",
                "schema": PRECISION_SCHEMA_VERSION,
                "acceptance_criterion": "zero critical wrong-owner/future/prior-only facts and human macro precision >=0.90; report Wilson intervals and every subtype",
                "review": "two blind humans on all items; adjudicate disagreements; optional LLM is annotation aid only",
            },
            "MS": {
                "planned_N": 72,
                "strata": "continuity_type event/state/change x observed status x owner coverage; natural shortfall reported",
                "future_seed": "paper1-memory-heldout-ms-v7-seed0-after-catalog-hash",
                "schema": PRECISION_SCHEMA_VERSION,
                "acceptance_criterion": "zero current/future/profile leakage and human macro precision >=0.90 across event/state/change",
                "review": "two blind humans on all items; adjudicate disagreements; optional LLM is annotation aid only",
            },
            "ME": {
                "planned_N": "all repaired accepted ME when <=120; otherwise stratified 120 plus every rare outcome type",
                "strata": "outcome type x single-turn/multi-turn lineage x linked/unlinked prior; all critical edge cases",
                "future_seed": "paper1-memory-heldout-me-v7-seed0-after-catalog-hash",
                "schema": PRECISION_SCHEMA_VERSION,
                "acceptance_criterion": "zero third-party/future/purpose/prediction/same-predicate critical errors and human precision >=0.90",
                "review": "two blind humans on all selected ME because current natural inventory is sparse; optional LLM cannot cast final vote",
            },
        },
        "estimated_cost": {
            "Qwen_recompile_sessions": 401,
            "Qwen_calls_nominal": 802,
            "Qwen_hard_cap_usd_proposal": 5.0,
            "Qwen_budget_status": "RESEARCHER_APPROVAL_REQUIRED_BEFORE_NEW_LIVE_RUN",
            "human_reviews": "MP120 + MS144 + ME up to 240 individual blind reviews, before adjudication",
            "LLM_review_calls": 0,
            "outcome_calls": 0,
        },
        "locks": {key: config[key]["status"] for key in config if key.endswith("OUTCOME_LOCK")},
    }
    _write(plan_path, heldout_plan)
    print(json.dumps({"precision": str(precision_path), "regression": str(regression_path), "ms": str(ms_path), "plan": str(plan_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
