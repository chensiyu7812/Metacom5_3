#!/usr/bin/env python3
"""Build the primary exact-evidence fold assignments and the sensitivity slice.

Zero-outcome, Codex-B lane. Reads the same public
``data/external/evo_emo.json`` targets as
``02_build_public_memory_census.py`` and writes:

- ``es_memeval_public_fold_assignments_v1.jsonl``: the primary mechanical
  fold grouping (QA by ``owner::question_group_id``, Summary/DG one target
  per item) with cross-task union only on a byte-identical canonical
  evidence-set fingerprint.
- ``es_memeval_public_shared_session_sensitivity_v1.jsonl``: the broader
  shared-session connected-component grouping. Sensitivity-only -- never
  used to compute the primary ``fold_id`` above (AGENTS.md rule 6).

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
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.data.es_memeval import enumerate_targets, load_users, parse_users  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.splits import (  # noqa: E402
    build_fold_assignments,
    build_shared_session_sensitivity_components,
)
from metacom_pm.paper1.splits.evidence import enumerate_split_evidence  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> str:
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")
    return _sha_text(rendered)


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    users = parse_users(load_users(PROJECT / "data" / "external" / "evo_emo.json"))
    targets = enumerate_targets(users)
    # B8: evidence is read once, here, via the splits-only evidence module,
    # and threaded through by target_id -- candidates/features never see it.
    evidence_records = enumerate_split_evidence(users)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fold_assignments = build_fold_assignments(targets, evidence_records)
    fold_rows = [
        {
            "protocol": "pm-paper1-public-memory-fold-assignment-v1",
            "target_id": a.target_id,
            "task_type": a.task_type.value,
            "fold_id": a.fold_id,
            "primary_group_key": a.primary_group_key,
            "exact_evidence_fingerprint": a.exact_evidence_fingerprint,
            "all_arms_seeds_repeats_bound": a.all_arms_seeds_repeats_bound,
            "target_outcome_excluded_from_fit": a.target_outcome_excluded_from_fit,
        }
        for a in fold_assignments
    ]
    folds_path = OUT_DIR / "es_memeval_public_fold_assignments_v1.jsonl"
    folds_sha256 = _write_jsonl(fold_rows, folds_path)

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

    n_primary_folds = len({row["fold_id"] for row in fold_rows})
    n_cross_task_unions = sum(
        1
        for fold_id in {row["fold_id"] for row in fold_rows}
        if len({r["task_type"] for r in fold_rows if r["fold_id"] == fold_id}) > 1
    )

    report = {
        "protocol": "pm-paper1-public-memory-folds-build-v1",
        "status": "PRIMARY_EXACT_EVIDENCE_FOLDS_AND_SENSITIVITY_BUILT",
        "outcome_calls": 0,
        "targets_total": len(targets),
        "primary_group_keys_total": len({t.primary_group_key for t in targets}),
        "primary_folds_total": n_primary_folds,
        "primary_folds_spanning_multiple_task_types": n_cross_task_unions,
        "sensitivity_components_total": len(sensitivity_rows),
        "outputs": {
            "fold_assignments": {"path": str(folds_path), "rows": len(fold_rows), "sha256": folds_sha256},
            "shared_session_sensitivity": {
                "path": str(sensitivity_path),
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
