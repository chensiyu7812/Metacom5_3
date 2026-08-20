#!/usr/bin/env python3
"""Build outcome-blind ESC split and RQ2 fold feasibility deliverables."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

EXPECTED_ESC_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
EXPECTED_CARDS_SHA256 = "2c63cf0f65cbe159b38837e0da368667201d34e42c6e5ea1bedbcf35cb7ab4e8"
SPLIT_SCENARIOS = {"small_24": 24, "medium_36": 36, "large_52": 52}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _allocate_quotas(strata: dict[tuple[str, str], list[dict[str, Any]]], total: int) -> dict[tuple[str, str], int]:
    population = sum(len(rows) for rows in strata.values())
    exact = {key: total * len(rows) / population for key, rows in strata.items()}
    quotas = {key: int(value) for key, value in exact.items()}
    # Every represented source/category cell receives one calibration card
    # when the requested total permits it.  Remaining seats use largest
    # remainder with deterministic stratum tie-breaks.
    if total >= len(strata):
        for key in quotas:
            quotas[key] = max(1, quotas[key])
    while sum(quotas.values()) > total:
        candidates = [key for key in quotas if quotas[key] > 1]
        key = min(candidates, key=lambda item: (exact[item] - quotas[item], item))
        quotas[key] -= 1
    while sum(quotas.values()) < total:
        candidates = [key for key, rows in strata.items() if quotas[key] < len(rows)]
        key = max(candidates, key=lambda item: (exact[item] - quotas[item], tuple(reversed(item))))
        quotas[key] += 1
    return quotas


def _balance(rows: list[dict[str, Any]], split: str) -> dict[str, Any]:
    selected = [row for row in rows if row["split"] == split]
    n = len(selected)
    return {
        "cards": n,
        "source_counts": dict(sorted(Counter(row["source"] for row in selected).items())),
        "category_counts": dict(sorted(Counter(row["category"] for row in selected).items())),
        "source_category_counts": {
            f"{source}::{category}": count
            for (source, category), count in sorted(
                Counter((row["source"], row["category"]) for row in selected).items()
            )
        },
        "source_fractions": {
            key: value / n for key, value in sorted(Counter(row["source"] for row in selected).items())
        },
        "category_fractions": {
            key: value / n for key, value in sorted(Counter(row["category"] for row in selected).items())
        },
    }


def _max_fraction_gap(
    sample: dict[str, Any], population_rows: list[dict[str, Any]], field: str
) -> float:
    population_counts = Counter(row[field] for row in population_rows)
    sample_fractions = sample[f"{field}_fractions"]
    population_n = len(population_rows)
    return max(
        abs(sample_fractions.get(key, 0.0) - count / population_n)
        for key, count in population_counts.items()
    )


def build_esc_split_feasibility(cards_path: Path, overlap_path: Path) -> dict[str, Any]:
    if _sha_file(cards_path) != EXPECTED_CARDS_SHA256:
        raise RuntimeError("official ESC-Eval English cards hash drifted")
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    overlap = _read_jsonl(overlap_path)
    if len(cards) != 331 or len(overlap) != 331:
        raise RuntimeError("expected 331 ESC-Eval English cards and overlap rows")
    overlap_by_index = {row["official_file_index"]: row for row in overlap}

    metadata: list[dict[str, Any]] = []
    for index, card in enumerate(cards):
        row = overlap_by_index[index]
        if card["source"] != row["source"] or _sha_text(card["base"]) != row["role_card_sha256"]:
            raise RuntimeError("ESC source-overlap manifest does not match official cards")
        metadata.append(
            {
                "official_file_index": index,
                "card_key": row["card_key"],
                "role_card_sha256": row["role_card_sha256"],
                "source": row["source"],
                "category": card["res"],
                "overlap_slice": row["analysis_slice"],
            }
        )

    primary = [row for row in metadata if row["overlap_slice"] == "primary_non_esconv_transfer"]
    strata: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in primary:
        strata[(row["source"], row["category"])].append(row)
    for rows in strata.values():
        rows.sort(key=lambda row: (_sha_text("seed=0|" + row["card_key"]), row["card_key"]))

    scenarios: dict[str, Any] = {}
    for name, calibration_size in SPLIT_SCENARIOS.items():
        quotas = _allocate_quotas(strata, calibration_size)
        calibration_keys = {
            row["card_key"]
            for key, rows in strata.items()
            for row in rows[: quotas[key]]
        }
        assignments = [
            {
                "protocol": "pm-paper1-esc-calibration-confirmatory-split-feasibility-row-v1",
                **row,
                "split": "calibration" if row["card_key"] in calibration_keys else "confirmatory",
            }
            for row in sorted(primary, key=lambda row: row["official_file_index"])
        ]
        calibration_balance = _balance(assignments, "calibration")
        confirmatory_balance = _balance(assignments, "confirmatory")
        calibration_balance["max_abs_source_fraction_gap_vs_population"] = _max_fraction_gap(
            calibration_balance, primary, "source"
        )
        calibration_balance["max_abs_category_fraction_gap_vs_population"] = _max_fraction_gap(
            calibration_balance, primary, "category"
        )
        confirmatory_balance["max_abs_source_fraction_gap_vs_population"] = _max_fraction_gap(
            confirmatory_balance, primary, "source"
        )
        confirmatory_balance["max_abs_category_fraction_gap_vs_population"] = _max_fraction_gap(
            confirmatory_balance, primary, "category"
        )
        population_balance = {
            "cards": len(primary),
            "source_counts": dict(sorted(Counter(row["source"] for row in primary).items())),
            "category_counts": dict(sorted(Counter(row["category"] for row in primary).items())),
        }
        scenarios[name] = {
            "status": "FEASIBILITY_ONLY_RATIO_NOT_SELECTED",
            "seed": 0,
            "calibration_cards": calibration_size,
            "confirmatory_cards": len(primary) - calibration_size,
            "population_balance": population_balance,
            "calibration_balance": calibration_balance,
            "confirmatory_balance": confirmatory_balance,
            "assignment_sha256": _sha_text(_canonical(assignments)),
            "assignments": assignments,
        }

    return {
        "protocol": "pm-paper1-esc-split-feasibility-v1",
        "status": "OUTCOME_BLIND_FEASIBILITY_RATIO_NOT_FROZEN",
        "outcome_calls": 0,
        "calibration_outcome_lock": "CLOSED",
        "confirmatory_outcome_lock": "CLOSED",
        "source_identity": {
            "official_cards_sha256": _sha_file(cards_path),
            "overlap_manifest_sha256": _sha_file(overlap_path),
        },
        "rules": {
            "primary_population": "source != ESconv",
            "stratification": ["source", "category(res)", "overlap_slice"],
            "allocation_seed": 0,
            "outcomes_read": False,
            "ratio_selected": False,
            "esconv_158_role": "overlap sensitivity only; not consumed by these split scenarios",
        },
        "scenarios": scenarios,
    }


def build_evaluator_plan(esc_repo: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=esc_repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    if commit != EXPECTED_ESC_COMMIT:
        raise RuntimeError("ESC-Eval checkout is not at the authority-pinned commit")
    files = [
        "score.py",
        "evaluate.py",
        "data/card_high_en.json",
        "data/test_en.json",
        "score/llama3_en.json",
        "score/Qwen_7B_en.json",
    ]
    inventory = {
        relative: {"sha256": _sha_file(esc_repo / relative)} for relative in files
    }
    test_cards = json.loads((esc_repo / "data" / "test_en.json").read_text(encoding="utf-8"))
    llama_scores = json.loads((esc_repo / "score" / "llama3_en.json").read_text(encoding="utf-8"))
    qwen_scores = json.loads((esc_repo / "score" / "Qwen_7B_en.json").read_text(encoding="utf-8"))
    return {
        "protocol": "pm-paper1-esc-evaluator-qualification-plan-v1",
        "status": "PLAN_ONLY_REFERENCE_ASSET_BLOCKER_AND_CANDIDATE_CHOICE_PENDING",
        "outcome_calls": 0,
        "calibration_outcome_lock": "CLOSED",
        "confirmatory_outcome_lock": "CLOSED",
        "official_asset_audit": {
            "esc_eval_commit": commit,
            "files": inventory,
            "official_example_role_cards": len(test_cards),
            "official_example_score_rows": {
                "llama3_en": len(llama_scores),
                "Qwen_7B_en": len(qwen_scores),
            },
            "raw_item_level_human_validation_labels_found": False,
            "raw_train_validation_test_assignment_found": False,
            "interpretation": (
                "The pinned public repository provides scorer code, 331 English role cards, "
                "three example trajectories and three-row example score files, but not the "
                "item-level human annotations needed to recompute weighted kappa, Spearman, "
                "MAD, or ranking consistency. Example score rows are not a qualification set."
            ),
        },
        "blocker": {
            "label": "IMPLEMENTATION BLOCKER — RESEARCHER DECISION REQUIRED",
            "missing_public_evidence": "item-level, dimension-level human ratings paired to candidate evaluator scores",
            "smallest_scientifically_valid_alternatives": [
                "obtain the authors' held-out human validation labels and immutable split identities",
                "commission a new independent blinded calibration set with at least two raters plus adjudication and freeze it before evaluator comparison",
            ],
        },
        "blindness": {
            "reference_raters_and_candidate_evaluators_receive": [
                "role-card context required by the official rubric",
                "dialogue trajectory",
                "official dimension rubric",
                "random opaque item id",
            ],
            "withheld": [
                "PM identity",
                "arm name",
                "ON/OFF status",
                "k or token budget",
                "Ours/baseline label",
                "retrieval scores and head decisions",
            ],
            "randomization": "candidate order and system aliases fixed before scoring",
        },
        "candidate_set": {
            "mandatory_official_candidate": "ESC-RANK at pinned adapters + InternLM2-chat-7B base",
            "additional_candidate_slots": "RESEARCHER_NOMINATION_REQUIRED_BEFORE_ANY_CALL",
            "no_silent_selection": True,
        },
        "comparison": {
            "unit": "same dialogue x same dimension scored by human reference and every candidate evaluator",
            "dimensions": ["Fluency", "Expression", "Empathy", "Information", "Skillful", "Humanoid", "Overall"],
            "metrics": [
                "quadratic weighted kappa with clustered bootstrap CI",
                "Spearman rho with clustered bootstrap CI",
                "mean absolute deviation on the official 0-4 scale",
                "pairwise system-ranking consistency with clustered bootstrap CI",
                "valid parse rate and missingness",
                "USD and GPU-hours per scored dialogue and per seven-dimension vector",
            ],
            "thresholds": "RESEARCHER_DECISION_REQUIRED_AND_MUST_BE_FROZEN_BEFORE_SCORING",
            "selection_order": [
                "validity and agreement against blinded human reference",
                "robustness across all seven official dimensions",
                "cost among evaluators that remain validity-qualified",
            ],
            "forbidden_selection_basis": "which evaluator gives Learned RS-PM or any Ours-labelled arm a higher score",
        },
        "qualification_outputs": [
            "immutable item and blindness manifest",
            "human-reference reliability report",
            "per-candidate agreement report with confidence intervals",
            "cost ledger",
            "researcher-signed evaluator freeze or explicit nonselection",
        ],
    }


def build_rq2_fold_feasibility(surface_path: Path, surface_summary_path: Path) -> dict[str, Any]:
    rows = _read_jsonl(surface_path)
    summary = json.loads(surface_summary_path.read_text(encoding="utf-8"))
    if _sha_file(surface_path) != summary["surface_points_sha256"]:
        raise RuntimeError("outer-fold surface hash does not match summary")
    selected: dict[str, Any] = {}
    for k in (4, 5, 6):
        matches = [row for row in rows if row["n_outer_folds"] == k and row["seed"] == 0]
        if len(matches) != 1:
            raise RuntimeError(f"expected one K={k}, seed=0 surface point")
        row = matches[0]
        if not (
            row["all_targets_assigned_exactly_once"]
            and row["all_components_atomic"]
            and row["no_missing_or_duplicate_targets"]
        ):
            raise RuntimeError(f"K={k}, seed=0 failed structural integrity")
        selected[f"k{k}_seed0"] = row
    return {
        "protocol": "pm-paper1-rq2-outer-fold-feasibility-v1",
        "status": "K5_SEED0_STRUCTURAL_REPORT_ALTERNATIVE_K_NO_OUTCOME_COMPARISON",
        "outcome_calls": 0,
        "calibration_outcome_lock": "CLOSED",
        "confirmatory_outcome_lock": "CLOSED",
        "source_identity": {
            "surface_path": surface_path.relative_to(PROJECT).as_posix(),
            "surface_sha256": _sha_file(surface_path),
            "surface_summary_sha256": _sha_file(surface_summary_path),
            "primary_grouping": "477 PREPACK_EXACT_EVIDENCE_COMPONENTS",
        },
        "requested_primary_structure": selected["k5_seed0"],
        "no_outcome_alternative_k_comparison": {
            "purpose": "structural feasibility only; not seed shopping and not an outcome-based winner search",
            "k4_seed0": selected["k4_seed0"],
            "k6_seed0": selected["k6_seed0"],
        },
        "rules": {
            "seed": 0,
            "seed_shopping": "FORBIDDEN",
            "shared_session_semantic_components": "SENSITIVITY_ONLY_NOT_PRIMARY",
            "resource_budget_selection": (
                "performed only inside each outer training/calibration partition; held-out outer "
                "target outcomes remain inaccessible until that fold's global budget is frozen"
            ),
            "confirmatory_target_outcome_isolation": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-repo", type=Path, required=True)
    parser.add_argument(
        "--overlap-manifest",
        type=Path,
        default=PROJECT / "data" / "paper1_authority" / "esc_eval_english331_source_overlap_v1.jsonl",
    )
    parser.add_argument(
        "--fold-surface",
        type=Path,
        default=PROJECT / "data" / "paper1_public_memory" / "es_memeval_public_outer_fold_packing_surface_v1.jsonl",
    )
    parser.add_argument(
        "--fold-summary",
        type=Path,
        default=PROJECT / "data" / "paper1_public_memory" / "es_memeval_public_outer_fold_packing_surface_summary_v1.json",
    )
    parser.add_argument(
        "--esc-plan-out",
        type=Path,
        default=PROJECT / "data" / "paper1_authority" / "paper1_esc_evaluator_qualification_plan_20260820_v1.json",
    )
    parser.add_argument(
        "--esc-split-out",
        type=Path,
        default=PROJECT / "data" / "paper1_authority" / "paper1_esc_split_feasibility_20260820_v1.json",
    )
    parser.add_argument(
        "--rq2-fold-out",
        type=Path,
        default=PROJECT / "data" / "paper1_authority" / "paper1_rq2_fold_feasibility_20260820_v1.json",
    )
    args = parser.parse_args()

    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    esc_split = build_esc_split_feasibility(
        args.esc_repo / "data" / "card_high_en.json", args.overlap_manifest
    )
    evaluator_plan = build_evaluator_plan(args.esc_repo)
    rq2_fold = build_rq2_fold_feasibility(args.fold_surface, args.fold_summary)
    _write_json(args.esc_plan_out, evaluator_plan)
    _write_json(args.esc_split_out, esc_split)
    _write_json(args.rq2_fold_out, rq2_fold)
    print(
        json.dumps(
            {
                "esc_plan": args.esc_plan_out.relative_to(REPO).as_posix(),
                "esc_split": args.esc_split_out.relative_to(REPO).as_posix(),
                "rq2_fold": args.rq2_fold_out.relative_to(REPO).as_posix(),
                "outcome_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
