#!/usr/bin/env python3
"""Freeze the researcher-approved outcome-blind ESC/RQ2 structures.

This script selects only the two structures explicitly approved on
2026-08-20: ESC ``large_52`` and RQ2 outer folds ``K=5, seed=0``.  It
materializes exact assignments, binds their bytes, and verifies that all four
scoped outcome locks remain closed.  It never reads a response, score, gold
answer, target outcome, or future dialogue content.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.data.es_memeval import load_users  # noqa: E402
from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users  # noqa: E402
from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)
from metacom_pm.paper1.splits import (  # noqa: E402
    build_group_component_assignments,
    build_group_components,
    pack_components_into_outer_folds,
)
from metacom_pm.paper1.splits.evidence import enumerate_split_evidence  # noqa: E402

AUTHORITY_DIR = PROJECT / "data" / "paper1_authority"
MEMORY_DIR = PROJECT / "data" / "paper1_public_memory"
ESC_FEASIBILITY = AUTHORITY_DIR / "paper1_esc_split_feasibility_20260820_v1.json"
RQ2_FEASIBILITY = AUTHORITY_DIR / "paper1_rq2_fold_feasibility_20260820_v1.json"
ESC_ASSIGNMENTS = AUTHORITY_DIR / "paper1_esc_split_large52_frozen_v1.jsonl"
RQ2_ASSIGNMENTS = MEMORY_DIR / "es_memeval_public_outer_fold_assignments_k5_seed0_v1.jsonl"
FREEZE_MANIFEST = AUTHORITY_DIR / "paper1_structural_split_fold_freeze_20260820_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    payload = "".join(_canonical(row) + "\n" for row in rows).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def _freeze_esc() -> dict[str, Any]:
    source = json.loads(ESC_FEASIBILITY.read_text(encoding="utf-8"))
    if source.get("outcome_calls") != 0:
        raise RuntimeError("ESC feasibility source is not zero-outcome")
    if source.get("calibration_outcome_lock") != "CLOSED":
        raise RuntimeError("ESC feasibility calibration lock is not CLOSED")
    if source.get("confirmatory_outcome_lock") != "CLOSED":
        raise RuntimeError("ESC feasibility confirmatory lock is not CLOSED")
    scenario = source["scenarios"]["large_52"]
    if scenario.get("seed") != 0:
        raise RuntimeError("approved ESC large_52 seed drift")
    if scenario.get("calibration_cards") != 52 or scenario.get("confirmatory_cards") != 121:
        raise RuntimeError("approved ESC large_52 cardinality drift")

    rows: list[dict[str, Any]] = []
    for assignment in sorted(scenario["assignments"], key=lambda row: row["card_key"]):
        if assignment.get("overlap_slice") != "primary_non_esconv_transfer":
            raise RuntimeError("ESC large_52 contains a non-primary overlap slice")
        rows.append(
            {
                "protocol": "pm-paper1-esc-large52-frozen-assignment-v1",
                "selected_scenario": "large_52",
                "seed": 0,
                "card_key": assignment["card_key"],
                "official_file_index": assignment["official_file_index"],
                "role_card_sha256": assignment["role_card_sha256"],
                "source": assignment["source"],
                "category": assignment["category"],
                "overlap_slice": assignment["overlap_slice"],
                "split": assignment["split"],
            }
        )
    if len(rows) != 173 or len({row["card_key"] for row in rows}) != 173:
        raise RuntimeError("ESC large_52 assignments are not exactly 173 unique cards")
    if sum(row["split"] == "calibration" for row in rows) != 52:
        raise RuntimeError("ESC large_52 calibration count drift")
    if sum(row["split"] == "confirmatory" for row in rows) != 121:
        raise RuntimeError("ESC large_52 confirmatory count drift")
    assignment_sha = _write_jsonl(ESC_ASSIGNMENTS, rows)
    return {
        "decision": "ESC_large_52",
        "status": "FROZEN",
        "seed": 0,
        "seed_change_forbidden": True,
        "calibration_cards": 52,
        "confirmatory_cards": 121,
        "population": 173,
        "assignment_source_sha256": scenario["assignment_sha256"],
        "feasibility_artifact": {
            "path": _repo_path(ESC_FEASIBILITY),
            "sha256": _sha256_file(ESC_FEASIBILITY),
        },
        "frozen_assignments": {
            "path": _repo_path(ESC_ASSIGNMENTS),
            "rows": len(rows),
            "sha256": assignment_sha,
        },
        "outcome_fields_read": 0,
    }


def _freeze_rq2() -> dict[str, Any]:
    feasibility = json.loads(RQ2_FEASIBILITY.read_text(encoding="utf-8"))
    if feasibility.get("outcome_calls") != 0:
        raise RuntimeError("RQ2 feasibility source is not zero-outcome")
    requested = feasibility["requested_primary_structure"]
    if requested.get("n_outer_folds") != 5 or requested.get("seed") != 0:
        raise RuntimeError("approved RQ2 K=5 seed=0 feasibility point is missing")

    users = load_sanitized_runtime_users(
        MEMORY_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"
    )
    targets = enumerate_targets(users)
    evaluator_users = parse_evaluator_users(
        load_users(PROJECT / "data" / "external" / "evo_emo.json")
    )
    evidence_records = enumerate_split_evidence(evaluator_users)
    components = build_group_components(targets, evidence_records)
    component_to_fold = pack_components_into_outer_folds(
        components, n_outer_folds=5, seed=0
    )
    component_assignments = build_group_component_assignments(targets, evidence_records)
    target_by_id = {target.target_id: target for target in targets}

    rows: list[dict[str, Any]] = []
    for assignment in sorted(component_assignments, key=lambda row: row.target_id):
        target = target_by_id[assignment.target_id]
        rows.append(
            {
                "protocol": "pm-paper1-rq2-outer-fold-assignment-k5-seed0-v1",
                **asdict(assignment),
                "task_type": assignment.task_type.value,
                "owner_id": target.owner_id,
                "outer_fold": component_to_fold[assignment.group_component_id],
                "n_outer_folds": 5,
                "seed": 0,
            }
        )
    target_ids = [row["target_id"] for row in rows]
    if len(rows) != 1586 or len(set(target_ids)) != 1586:
        raise RuntimeError("RQ2 frozen assignments do not cover 1586 targets exactly once")
    component_folds: dict[str, set[int]] = {}
    for row in rows:
        component_folds.setdefault(row["group_component_id"], set()).add(row["outer_fold"])
    if any(len(folds) != 1 for folds in component_folds.values()):
        raise RuntimeError("an exact-evidence component was split across outer folds")
    fold_counts = {
        str(fold): sum(row["outer_fold"] == fold for row in rows) for fold in range(5)
    }
    if sorted(fold_counts.values()) != [317, 317, 317, 317, 318]:
        raise RuntimeError(f"RQ2 K5 seed0 target balance drift: {fold_counts}")
    assignment_sha = _write_jsonl(RQ2_ASSIGNMENTS, rows)
    return {
        "decision": "RQ2_outer_folds_K5_seed0",
        "status": "FROZEN",
        "n_outer_folds": 5,
        "seed": 0,
        "seed_change_forbidden": True,
        "targets": len(rows),
        "exact_evidence_components": len(component_folds),
        "fold_target_counts": fold_counts,
        "all_targets_assigned_exactly_once": True,
        "all_components_atomic": True,
        "target_outcome_reads": 0,
        "feasibility_artifact": {
            "path": _repo_path(RQ2_FEASIBILITY),
            "sha256": _sha256_file(RQ2_FEASIBILITY),
        },
        "component_source": feasibility["source_identity"],
        "frozen_assignments": {
            "path": _repo_path(RQ2_ASSIGNMENTS),
            "rows": len(rows),
            "sha256": assignment_sha,
        },
    }


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    manifest = {
        "protocol": "pm-paper1-structural-split-fold-freeze-20260820-v1",
        "status": "FROZEN",
        "researcher_approval": {
            "date": "2026-08-20",
            "approved_decisions": ["ESC_large_52", "RQ2_outer_folds_K5_seed0"],
        },
        "scope": "outcome_blind_structural_split_and_outer_fold_identity_only",
        "ESC": _freeze_esc(),
        "RQ2": _freeze_rq2(),
        "outcome_locks": {
            "RQ1_RS_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ1_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
            "RQ2_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
        },
        "formal_unlock": False,
        "formal_outcome_calls": 0,
        "PM_training_runs": 0,
        "seed_shopping": "FORBIDDEN",
    }
    FREEZE_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    print(json.dumps(build(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
