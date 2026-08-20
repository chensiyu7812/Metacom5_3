#!/usr/bin/env python3
"""Analyze complete two-human/candidate ESC qualification ratings, fail closed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.evaluator_qualification import (  # noqa: E402
    DIMENSIONS,
    analyze_candidate,
    assert_blind_payload,
    blocked_result,
    grouped_residual_bias,
    human_reliability,
    validate_scores,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _complete_human(rows: list[dict[str, Any]]) -> bool:
    try:
        return bool(rows) and all(
            row.get("human_completed") is True and validate_scores(row["scores"])
            for row in rows
        )
    except (KeyError, ValueError, TypeError):
        return False


def _complete_adjudication(rows: list[dict[str, Any]]) -> bool:
    try:
        return bool(rows) and all(
            row.get("adjudication_completed") is True
            and row.get("adjudicator_id")
            and validate_scores(row["scores"])
            for row in rows
        )
    except (KeyError, ValueError, TypeError):
        return False


def _complete_judges(rows: list[dict[str, Any]]) -> bool:
    try:
        if not rows:
            return False
        for row in rows:
            if not row.get("candidate_id") or not row.get("model_identity_sha256"):
                return False
            if not isinstance(row.get("parse_valid"), bool):
                return False
            if not isinstance(row.get("latency_seconds"), (int, float)) or row["latency_seconds"] < 0:
                return False
            if not isinstance(row.get("cost_usd"), (int, float)) or row["cost_usd"] < 0:
                return False
            if row["parse_valid"]:
                validate_scores(row["scores"])
            elif any(value is not None for value in row["scores"].values()):
                return False
        return True
    except (KeyError, ValueError, TypeError):
        return False


def main() -> int:
    base = PROJECT / "data" / "paper1_authority"
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=Path, default=base / "paper1_esc_evaluator_qualification_set_20260820_v1.jsonl")
    parser.add_argument("--pairs", type=Path, default=base / "paper1_esc_evaluator_qualification_pairs_20260820_v1.jsonl")
    parser.add_argument("--audit", type=Path, default=base / "paper1_esc_evaluator_qualification_audit_mapping_20260820_v1.json")
    parser.add_argument("--rater-a", type=Path, default=base / "paper1_esc_evaluator_human_blind_sheet_rater_a_20260820_v1.jsonl")
    parser.add_argument("--rater-b", type=Path, default=base / "paper1_esc_evaluator_human_blind_sheet_rater_b_20260820_v1.jsonl")
    parser.add_argument("--adjudicated", type=Path, default=base / "paper1_esc_evaluator_human_adjudication_template_20260820_v1.jsonl")
    parser.add_argument("--judge-rows", type=Path, default=base / "paper1_esc_evaluator_judge_output_template_20260820_v1.jsonl")
    parser.add_argument("--registry", type=Path, default=base / "paper1_esc_evaluator_candidate_identity_registry_20260820_v1.json")
    parser.add_argument("--runtime-report", type=Path)
    parser.add_argument("--out", type=Path, default=base / "paper1_esc_evaluator_qualification_results_20260820_v1.json")
    args = parser.parse_args()

    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    items = _read_jsonl(args.items)
    pairs = _read_jsonl(args.pairs)
    audit = _read_json(args.audit)
    rater_a = _read_jsonl(args.rater_a)
    rater_b = _read_jsonl(args.rater_b)
    adjudicated = _read_jsonl(args.adjudicated)
    judge_rows = _read_jsonl(args.judge_rows)
    registry = _read_json(args.registry)
    for payload in (items, pairs, rater_a, rater_b, adjudicated, judge_rows):
        assert_blind_payload(payload)

    blockers = []
    if not _complete_human(rater_a) or not _complete_human(rater_b):
        blockers.append("two independent blind human rating sheets are incomplete")
    if not _complete_adjudication(adjudicated):
        blockers.append("blind human adjudication is incomplete")
    if not _complete_judges(judge_rows):
        blockers.append("candidate evaluator score traces are incomplete")
    identity_blocked = [
        row["candidate_id"]
        for row in registry["candidates"]
        if row["status"].startswith("BLOCKED")
    ]
    if identity_blocked:
        blockers.append("exact researcher-frozen candidate identities missing: " + ", ".join(identity_blocked))
    frozen_identity = {
        row["candidate_id"]: row.get("identity_sha256") for row in registry["candidates"]
    }
    if _complete_judges(judge_rows):
        drifted = sorted(
            {
                row["candidate_id"]
                for row in judge_rows
                if not frozen_identity.get(row["candidate_id"])
                or row["model_identity_sha256"] != frozen_identity[row["candidate_id"]]
            }
        )
        if drifted:
            blockers.append("candidate score identity mismatch: " + ", ".join(drifted))
    runtime = _read_json(args.runtime_report) if args.runtime_report and args.runtime_report.is_file() else None
    if runtime is None or runtime.get("status") != "READY":
        blockers.append("pinned ESC-RANK >=24 GiB runtime qualification report is absent or not READY")

    if blockers:
        result = blocked_result(
            blockers=blockers,
            evidence={
                "qualification_items": len(items),
                "natural_public_baseline_items": sum(row.get("item_kind") == "natural_public_baseline" for row in items),
                "controlled_bias_probe_items": sum(row.get("item_kind") == "controlled_bias_probe" for row in items),
                "human_rows_complete": False,
                "judge_calls": 0,
                "local_gpu": "NVIDIA GeForce RTX 2070 8192 MiB; below required 24576 MiB",
            },
        )
        _write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    item_ids = [row["blind_item_id"] for row in items]
    reliability = human_reliability(rater_a + rater_b, item_ids)
    candidate_ids = sorted({row["candidate_id"] for row in judge_rows})
    analyses = {
        candidate_id: analyze_candidate(
            candidate_id=candidate_id,
            item_rows=items,
            adjudicated_rows=adjudicated,
            candidate_rows=judge_rows,
            pair_rows=pairs,
        )
        for candidate_id in candidate_ids
    }
    reference = {row["blind_item_id"]: validate_scores(row["scores"]) for row in adjudicated}
    family_mapping = {row["blind_item_id"]: row["system_family"] for row in audit["natural"]}
    for candidate_id in candidate_ids:
        candidate = {
            row["blind_item_id"]: validate_scores(row["scores"])
            for row in judge_rows
            if row["candidate_id"] == candidate_id and row["parse_valid"] is True
        }
        analyses[candidate_id]["hidden_system_family_residual_bias"] = grouped_residual_bias(
            reference_scores=reference,
            candidate_scores=candidate,
            item_groups=family_mapping,
        )
    result = {
        "protocol": "pm-paper1-esc-evaluator-qualification-results-v1",
        "status": "READY_FOR_RESEARCHER_EVALUATOR_SELECTION",
        "human_reliability": reliability,
        "candidates": analyses,
        "recommendation": None,
        "recommendation_note": "Apply validity/agreement, then bias/sensitivity, then cost/latency; researcher freezes winner.",
        "formal_ESC_Eval": False,
        "formal_outcome_calls": 0,
    }
    _write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
