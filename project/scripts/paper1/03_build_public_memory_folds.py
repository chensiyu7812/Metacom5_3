#!/usr/bin/env python3
"""Build primary exact-evidence group components and the sensitivity slice.

Zero-outcome, Codex-B lane. Reads the same sanitized runtime artifact for
target identity as ``02_build_public_memory_census.py`` (B18: via
``metacom_pm.paper1.data.memory_source.load_sanitized_runtime_users``, never
``data/external/evo_emo.json`` directly for that part) -- and, separately,
reads raw ``data/external/evo_emo.json`` through the evaluator/split-only
``metacom_pm.paper1.data.es_memeval`` loader purely to feed the evidence-only
join below (B18's other legitimate raw reader). Writes:

- ``es_memeval_public_group_component_assignments_v1.jsonl`` (B14: renamed
  from ``es_memeval_public_fold_assignments_v1.jsonl``, which is deleted):
  the primary mechanical group-component grouping (QA by
  ``owner::question_group_id``, Summary/DG one target per item) with
  cross-task union only on a byte-identical, owner-namespaced canonical
  evidence-set fingerprint. ``group_component_id`` is built by
  ``GroupComponentAssignment``, a type this lane owns outright -- it is
  never written into the shared, frozen ``contracts.FoldAssignment.fold_id``
  field. Status ``PREPACK_EXACT_EVIDENCE_COMPONENT``. This is *not* an outer
  cross-validation fold: see
  ``metacom_pm.paper1.splits.exact_evidence_folds`` module docstring.
  Outer-fold packing (``pack_components_into_outer_folds``) is implemented
  and tested but deliberately not invoked here -- this script does not
  choose n_outer_folds or a seed this round (status
  ``OUTER_FOLD_PACKING_PENDING_M2_FREEZE``).
- ``es_memeval_public_shared_session_sensitivity_v1.jsonl``: the broader
  shared-session connected-component grouping. Sensitivity-only -- never
  used to compute the primary group component above (AGENTS.md rule 6).

Evidence usage: this is the *only* build script that reads QA/Summary
``evidence`` (via ``metacom_pm.paper1.splits.evidence``, B8's sole reader).
``02_build_public_memory_census.py`` never touches it.

Asserts the pre-outcome lock is engaged before doing anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.splits import (  # noqa: E402
    GROUP_COMPONENT_STATUS,
    OUTER_FOLD_PACKING_STATUS,
    build_group_component_assignments,
    build_shared_session_sensitivity_components,
)
from metacom_pm.paper1.splits.evidence import enumerate_split_evidence  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"
LEGACY_FOLD_ASSIGNMENTS_PATH = OUT_DIR / "es_memeval_public_fold_assignments_v1.jsonl"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relpath(path: Path) -> str:
    """Repo-relative POSIX path -- B10: never an absolute or worktree-specific path."""

    return path.resolve().relative_to(REPO).as_posix()


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> str:
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")
    return _sha_text(rendered)


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    if not ARTIFACT_PATH.exists():
        raise RuntimeError(
            f"{ARTIFACT_PATH} does not exist -- run "
            "05_materialize_sanitized_runtime_artifact.py first"
        )
    # B12/B18: `users` (sanitized, from the already-materialized artifact)
    # drives target identity, exactly like 02_build_public_memory_census.py;
    # `evaluator_users` (raw evo_emo.json, via the evaluator/split-only
    # es_memeval loader) is parsed only to feed the splits-only evidence
    # reader below and is never passed to anything that also touches
    # candidates/features.
    users = load_sanitized_runtime_users(ARTIFACT_PATH)
    evaluator_users = parse_evaluator_users(load_users(PROJECT / "data" / "external" / "evo_emo.json"))
    targets = enumerate_targets(users)
    # B8: evidence is read once, here, via the splits-only evidence module,
    # and threaded through by target_id -- candidates/features never see it.
    evidence_records = enumerate_split_evidence(evaluator_users)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # B14: delete the legacy fold_assignments artifact if a previous run
    # left it behind -- it is replaced by group_component_assignments below,
    # not kept alongside it.
    if LEGACY_FOLD_ASSIGNMENTS_PATH.exists():
        LEGACY_FOLD_ASSIGNMENTS_PATH.unlink()

    component_assignments = build_group_component_assignments(targets, evidence_records)
    component_rows = [
        {
            "protocol": "pm-paper1-public-memory-group-component-assignment-v1",
            "status": GROUP_COMPONENT_STATUS,
            "target_id": a.target_id,
            "task_type": a.task_type.value,
            "group_component_id": a.group_component_id,
            "primary_group_key": a.primary_group_key,
            "exact_evidence_fingerprint": a.exact_evidence_fingerprint,
            "all_arms_seeds_repeats_bound": a.all_arms_seeds_repeats_bound,
            "target_outcome_excluded_from_fit": a.target_outcome_excluded_from_fit,
        }
        for a in component_assignments
    ]
    components_path = OUT_DIR / "es_memeval_public_group_component_assignments_v1.jsonl"
    components_sha256 = _write_jsonl(component_rows, components_path)

    sensitivity = build_shared_session_sensitivity_components(targets, users, evidence_records)
    sensitivity_rows = [
        {
            "protocol": "pm-paper1-public-memory-shared-session-sensitivity-v1",
            "status": "SENSITIVITY_ONLY_NOT_PRIMARY_FOLD",
            "component_id": c.component_id,
            "target_ids": list(c.target_ids),
        }
        for c in sensitivity
    ]
    sensitivity_path = OUT_DIR / "es_memeval_public_shared_session_sensitivity_v1.jsonl"
    sensitivity_sha256 = _write_jsonl(sensitivity_rows, sensitivity_path)

    n_group_components = len({row["group_component_id"] for row in component_rows})
    n_cross_task_unions = sum(
        1
        for gcid in {row["group_component_id"] for row in component_rows}
        if len({r["task_type"] for r in component_rows if r["group_component_id"] == gcid}) > 1
    )

    report = {
        "protocol": "pm-paper1-public-memory-group-component-assignments-build-v1",
        "status": "PRIMARY_GROUP_COMPONENTS_AND_SENSITIVITY_BUILT",
        "outcome_calls": 0,
        "evidence_usage": (
            "THIS_SCRIPT_IS_THE_ONLY_BUILD_SCRIPT_THAT_READS_QA_SUMMARY_EVIDENCE"
            "_VIA_SPLITS_EVIDENCE_ENUMERATE_SPLIT_EVIDENCE"
        ),
        "group_component_status": GROUP_COMPONENT_STATUS,
        "outer_fold_packing_status": OUTER_FOLD_PACKING_STATUS,
        "outer_fold_packing_note": (
            "pack_components_into_outer_folds is implemented and unit-tested "
            "(see tests/test_paper1_splits_folds.py) but not invoked by this "
            "script: n_outer_folds and seed are M2-freeze decisions, not "
            "self-selected this round."
        ),
        "legacy_fold_assignments_artifact_removed": (
            "es_memeval_public_fold_assignments_v1.jsonl (B14: renamed to "
            "es_memeval_public_group_component_assignments_v1.jsonl, the old "
            "fold_id-named artifact is deleted, not kept alongside)"
        ),
        "targets_total": len(targets),
        "primary_group_keys_total": len({t.primary_group_key for t in targets}),
        "group_components_total": n_group_components,
        "group_components_spanning_multiple_task_types": n_cross_task_unions,
        "sensitivity_components_total": len(sensitivity_rows),
        "outputs": {
            "group_component_assignments": {
                "path": _relpath(components_path),
                "rows": len(component_rows),
                "sha256": components_sha256,
            },
            "shared_session_sensitivity": {
                "path": _relpath(sensitivity_path),
                "rows": len(sensitivity_rows),
                "sha256": sensitivity_sha256,
                "status": "SENSITIVITY_ONLY",
            },
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build()
    rendered = _canonical(report) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
