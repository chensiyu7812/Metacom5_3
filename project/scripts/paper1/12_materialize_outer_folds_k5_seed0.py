#!/usr/bin/env python3
"""B30-FINAL Part B: materialize the pre-registered K=5, seed=0 outer folds.

Zero-outcome, Codex-B lane. This is the single point that actually freezes
one (K, seed) pair from the already-built, already-tested structural
packing surface into a target-level manifest. It reuses, unmodified:

- the same 477 ``PREPACK_EXACT_EVIDENCE_COMPONENT`` primary group components
  that ``03_build_public_memory_folds.py`` builds (via
  ``metacom_pm.paper1.splits.build_group_components`` -- identical
  deterministic construction, no new grouping logic);
- ``metacom_pm.paper1.splits.pack_components_into_outer_folds``, which
  ``08_audit_outer_fold_packing_surface.py`` already exercises over
  K=2..10 x seed=0..31 as a diagnostic decision surface without selecting a
  winner (see that script and ``es_memeval_public_outer_fold_packing_
  surface_v1.jsonl``, which already contains this exact (K=5, seed=0) point
  for cross-check).

K=5 and seed=0 are the pre-registered conventional default the zero-outcome
surface already covers -- not a value chosen by looking at any effect,
official-metric, or other outcome (there are none open; outcome_calls stays
0 throughout, and the pre-outcome lock is asserted before anything else).
This is a materialization of one already-diagnosed surface point, not a new
decision surface and not a PASS/FAIL gate: no coverage threshold, no
minimum-N, and no comparison to any other (K, seed) point's quality decides
this choice.

Writes:

- ``es_memeval_public_outer_fold_assignment_k5_seed0_v1.jsonl``: one row per
  target (1586 expected), carrying its ``group_component_id`` (the atomic
  pre-pack unit -- never conflated with the outer fold) and its assigned
  ``outer_fold_index`` (0..4).
- ``es_memeval_public_outer_fold_assignment_k5_seed0_summary_v1.json``:
  per-fold target/task-type/owner counts (via
  ``metacom_pm.paper1.splits.summarize_outer_fold_packing``) plus three
  structural invariants re-verified independently at the target level: every
  target assigned exactly once, every component atomic (all its targets
  share one outer_fold_index), and full coverage (no missing/extra target).

Never reads any outcome/gold/answer/observation/reference-summary field.
Never promotes the shared-session sensitivity grouping into this primary
assignment (AGENTS.md rule 6: sensitivity stays sensitivity-only, and is not
touched by this script at all).

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
    build_group_component_assignments,
    build_group_components,
    pack_components_into_outer_folds,
    summarize_outer_fold_packing,
)
from metacom_pm.paper1.splits.evidence import enumerate_split_evidence  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"
N_OUTER_FOLDS = 5
SEED = 0

PRE_REGISTERED_NOTE = (
    "K=5 and seed=0 are a pre-registered conventional default already "
    "covered as one point on the K=2..10 x seed=0..31 zero-outcome "
    "structural decision surface built by "
    "08_audit_outer_fold_packing_surface.py. No outcome, effect, or "
    "official-metric field was read to choose this point -- see the M2 "
    "decision packet's 'outer_folds' item, which records this materialization "
    "as pending and explicitly disclaims it as 'not a winner chosen from "
    "outcomes or a structural PASS gate'."
)
NO_PASS_FAIL_NOTE = (
    "No PASS/FAIL verdict, coverage threshold, or minimum-N gate is applied "
    "to this materialization or to any individual fold."
)
GROUP_COMPONENT_ID_NOT_FOLD_ID_NOTE = (
    "group_component_id (the atomic pre-pack unit) and outer_fold_index "
    "(0..4, this script's own packing output) are always written as "
    "separate fields; group_component_id is never renamed into, aliased "
    "as, or otherwise treated as an outer_fold_index."
)
SHARED_SESSION_SENSITIVITY_NOTE = (
    "Shared-session connected components "
    "(build_shared_session_sensitivity_components) are not read, computed, "
    "or referenced anywhere in this script -- they remain sensitivity-only "
    "(AGENTS.md rule 6) and never enter this primary outer-fold assignment."
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> str:
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")
    return _sha_text(rendered)


def _verify_structural_invariants(
    rows: list[dict[str, Any]], targets_total: int, components_total: int
) -> dict[str, Any]:
    """Independent re-verification at the target-row level, not just trusting
    pack_components_into_outer_folds' own invariants (defense in depth,
    matching this project's established pattern -- see
    outer_fold_decision_surface.py's identical philosophy)."""

    target_ids = [row["target_id"] for row in rows]
    no_duplicates = len(target_ids) == len(set(target_ids))
    no_missing_or_extra = len(target_ids) == targets_total

    fold_by_component: dict[str, set[int]] = {}
    for row in rows:
        fold_by_component.setdefault(row["group_component_id"], set()).add(row["outer_fold_index"])
    all_atomic = all(len(folds) == 1 for folds in fold_by_component.values())

    return {
        "every_target_assigned_exactly_once": no_duplicates and no_missing_or_extra,
        "no_duplicate_target": no_duplicates,
        "no_missing_or_extra_target": no_missing_or_extra,
        "component_atomicity_preserved": all_atomic,
        "components_observed": len(fold_by_component),
        "components_expected": components_total,
        "component_count_matches": len(fold_by_component) == components_total,
    }


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    if not ARTIFACT_PATH.exists():
        raise RuntimeError(
            f"{ARTIFACT_PATH} does not exist -- run "
            "05_materialize_sanitized_runtime_artifact.py first"
        )
    users = load_sanitized_runtime_users(ARTIFACT_PATH)
    targets = enumerate_targets(users)
    evaluator_users = parse_evaluator_users(load_users(PROJECT / "data" / "external" / "evo_emo.json"))
    evidence_records = enumerate_split_evidence(evaluator_users)

    component_assignments = build_group_component_assignments(targets, evidence_records)
    components = build_group_components(targets, evidence_records)
    outer_fold_by_component = pack_components_into_outer_folds(
        components, n_outer_folds=N_OUTER_FOLDS, seed=SEED
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = [
        {
            "protocol": "pm-paper1-public-memory-outer-fold-assignment-k5-seed0-v1",
            "status": "OUTER_FOLD_ASSIGNMENT_K5_SEED0_MATERIALIZED",
            "target_id": a.target_id,
            "task_type": a.task_type.value,
            "primary_group_key": a.primary_group_key,
            "group_component_id": a.group_component_id,
            "exact_evidence_fingerprint": a.exact_evidence_fingerprint,
            "n_outer_folds": N_OUTER_FOLDS,
            "seed": SEED,
            "outer_fold_index": outer_fold_by_component[a.group_component_id],
            "all_arms_seeds_repeats_bound": a.all_arms_seeds_repeats_bound,
            "target_outcome_excluded_from_fit": a.target_outcome_excluded_from_fit,
        }
        for a in component_assignments
    ]
    rows_path = OUT_DIR / "es_memeval_public_outer_fold_assignment_k5_seed0_v1.jsonl"
    rows_sha256 = _write_jsonl(rows, rows_path)

    invariants = _verify_structural_invariants(rows, len(targets), len(components))
    per_fold = summarize_outer_fold_packing(components, outer_fold_by_component, N_OUTER_FOLDS)

    summary = {
        "protocol": "pm-paper1-outer-fold-assignment-k5-seed0-summary-v1",
        "status": "OUTER_FOLD_ASSIGNMENT_K5_SEED0_MATERIALIZED_NOT_A_PASS_GATE",
        "outcome_calls": 0,
        "n_outer_folds": N_OUTER_FOLDS,
        "seed": SEED,
        "targets_total": len(targets),
        "components_total": len(components),
        "pre_registered_note": PRE_REGISTERED_NOTE,
        "no_pass_fail_note": NO_PASS_FAIL_NOTE,
        "group_component_id_is_not_fold_id_note": GROUP_COMPONENT_ID_NOT_FOLD_ID_NOTE,
        "shared_session_sensitivity_note": SHARED_SESSION_SENSITIVITY_NOTE,
        "structural_invariants": invariants,
        "per_fold": per_fold,
    }
    summary_path = OUT_DIR / "es_memeval_public_outer_fold_assignment_k5_seed0_summary_v1.json"
    summary_rendered = _canonical(summary) + "\n"
    summary_path.write_text(summary_rendered, encoding="utf-8")

    report = {
        "protocol": "pm-paper1-outer-fold-assignment-k5-seed0-build-v1",
        "status": "OUTER_FOLD_ASSIGNMENT_K5_SEED0_MATERIALIZED_NOT_A_PASS_GATE",
        "outcome_calls": 0,
        "n_outer_folds": N_OUTER_FOLDS,
        "seed": SEED,
        "targets_total": len(targets),
        "components_total": len(components),
        "all_structural_invariants_pass": all(
            invariants[k]
            for k in (
                "every_target_assigned_exactly_once",
                "component_atomicity_preserved",
                "component_count_matches",
            )
        ),
        "pre_registered_note": PRE_REGISTERED_NOTE,
        "outputs": {
            "outer_fold_assignment": {
                "path": _relpath(rows_path),
                "rows": len(rows),
                "sha256": rows_sha256,
            },
            "outer_fold_assignment_summary": {
                "path": _relpath(summary_path),
                "sha256": _sha_text(summary_rendered),
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
