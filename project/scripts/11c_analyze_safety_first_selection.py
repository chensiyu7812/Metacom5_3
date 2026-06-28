#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from metacom_pm.contracts import StrategyCard
from metacom_pm.io import iter_jsonl, write_json
from metacom_pm.labels import action_response_scores, load_memory_labels, load_strategy_labels
from metacom_pm.policies import RuleConfig, StrongRulePolicy
from metacom_pm.retrieval import StrategyRetriever
from metacom_pm.selection import (
    _complete_policy_rows,
    _evaluate_cached_pm_grid_row,
    _outcome_costs,
    _select_near_best_then_low_risk_cost,
    evaluate_policy_on_labels,
)
from metacom_pm.stats import cluster_bootstrap_ci, one_sample_cluster_signflip_test
from metacom_pm.sweep import load_states
from metacom_pm.training import PMModel


ROOT = Path(__file__).resolve().parents[1]


def _round(value: Any) -> Any:
    return round(value, 6) if isinstance(value, float) else value


def _metric_summary(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "n",
        "mean_response_score",
        "mean_misuse_risk",
        "mean_memory_omission_risk",
        "mean_strategy_decision_risk",
        "mean_safety_risk",
        "mean_cost",
        "action_distribution",
    )
    return {key: _round(row[key]) for key in keys}


def _select_safety_first(
    rows: list[dict[str, Any]],
    *,
    safety_margin: float,
) -> dict[str, Any]:
    """Select the safest complete PM row, then prefer response and cost.

    This is a diagnostic policy-selection variant.  It asks whether the learned
    PM has any conservative operating point at all; it is not the primary
    response-first selector used by scripts/11_tune_validation.py.
    """
    if not rows:
        raise ValueError("no complete PM rows")
    best_safety = min(float(row["mean_safety_risk"]) for row in rows)
    safe_set = [
        row for row in rows
        if float(row["mean_safety_risk"]) <= best_safety + safety_margin
    ]
    return min(
        safe_set,
        key=lambda row: (
            -float(row["mean_response_score"]),
            float(row["mean_cost"]),
            float(row["mean_misuse_risk"]),
            str((row["epsilon"], row["tau_misuse"], row["tau_omission"], row["tau_strategy"])),
        ),
    )


def _selection_cis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = (
        "response_score",
        "misuse_risk",
        "memory_omission_risk",
        "strategy_decision_risk",
        "safety_risk",
        "cost",
    )
    report = {
        "n_rows": len(rows),
        "n_states": len({row["state_id"] for row in rows}),
        "n_users": len({row["user_id"] for row in rows}),
        "metrics": {},
    }
    for metric in metrics:
        key = f"delta_{metric}"
        report["metrics"][metric] = {
            "mean_delta": float(mean(row[key] for row in rows)),
            "state_cluster_ci": cluster_bootstrap_ci(
                rows,
                cluster_key="state_id",
                value_key=key,
                n_resamples=10000,
                seed=1729,
            ).as_dict(),
            "user_cluster_ci": cluster_bootstrap_ci(
                rows,
                cluster_key="user_id",
                value_key=key,
                n_resamples=10000,
                seed=1729,
            ).as_dict(),
            "state_cluster_signflip": one_sample_cluster_signflip_test(
                rows,
                cluster_key="state_id",
                value_key=key,
                null_value=0.0,
                n_permutations=10000,
                seed=1729,
            ),
            "user_cluster_signflip": one_sample_cluster_signflip_test(
                rows,
                cluster_key="user_id",
                value_key=key,
                null_value=0.0,
                n_permutations=10000,
                seed=1729,
            ),
        }
    return report


def _rule_for_selection(selection_path: Path) -> RuleConfig:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    return RuleConfig(**selection["strong_rule"]["config"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-mode", default="text_metadata")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--fold-mode", default="user")
    parser.add_argument("--safety-margin", type=float, default=0.02)
    parser.add_argument("--models-dir", type=Path, default=ROOT / "outputs/models_cv_m2b")
    parser.add_argument("--judging-dir", type=Path, default=ROOT / "outputs/full_judging_gemini_flash_lite_v3")
    parser.add_argument(
        "--m2b-path",
        type=Path,
        default=ROOT / "outputs/m2b_selected_set_omission_gemini_flash_lite_v3/memory_selected_set_omission_judgments.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs/safety_first_selection_m2b_text_metadata_seed17.json",
    )
    args = parser.parse_args()

    states = load_states(ROOT / "data/synthetic/runtime_states.jsonl")
    folds = {
        int(row["fold"]): set(row["validation_card_ids"])
        for row in iter_jsonl(ROOT / "data/synthetic/folds.jsonl")
        if row["mode"] == args.fold_mode
    }
    response = action_response_scores(args.judging_dir / "response_pair_judgments.jsonl")
    memory = load_memory_labels(
        args.judging_dir / "memory_omission_judgments.jsonl",
        args.judging_dir / "memory_use_judgments.jsonl",
        args.m2b_path,
    )
    strategy = load_strategy_labels(
        args.judging_dir / "strategy_use_judgments.jsonl",
        args.judging_dir / "strategy_omission_judgments.jsonl",
    )
    costs = _outcome_costs(ROOT / "outputs/synthetic_sweep/action_outcomes.jsonl")
    strategy_cards = [
        StrategyCard.model_validate(row)
        for row in iter_jsonl(ROOT / "data/strategy/strategy_cards.jsonl")
    ]
    strategy_retriever = StrategyRetriever(strategy_cards)

    per_fold = []
    paired_rows = []
    for fold, validation_card_ids in sorted(folds.items()):
        checkpoint = (
            args.models_dir
            / f"{args.feature_mode}_{args.fold_mode}_fold{fold}_seed{args.seed}.joblib"
        )
        if not checkpoint.exists():
            raise FileNotFoundError(checkpoint)
        selection_path = (
            ROOT
            / f"outputs/selection_m2b_{args.feature_mode}_fold{fold}_seed{args.seed}.json"
        )
        if not selection_path.exists():
            raise FileNotFoundError(
                f"Run scripts/11_tune_validation.py first: {selection_path}"
            )

        model = PMModel.load(checkpoint)
        score_cache: dict[str, dict[str, dict[str, float]]] = {}
        score_failures: dict[str, str] = {}
        for card_id in sorted(validation_card_ids):
            try:
                score_cache[card_id] = model.score_actions(
                    states[card_id],
                    states[card_id].allowed_actions,
                )
            except Exception as exc:
                score_failures[card_id] = str(exc)

        complete_pm_rows = []
        for epsilon, tau_misuse, tau_omission, tau_strategy in product(
            [0.0, 0.05, 0.10, 0.15, 0.20, 0.30],
            [0.25, 0.35, 0.50, 0.75, 1.0],
            [0.25, 0.35, 0.50, 0.75, 1.0],
            [0.25, 0.35, 0.50, 0.75, 1.0],
        ):
            row = _evaluate_cached_pm_grid_row(
                states,
                validation_card_ids,
                score_cache,
                score_failures,
                response,
                memory.misuse_risk,
                memory.omission_risk,
                strategy.risk,
                costs,
                epsilon=epsilon,
                tau_misuse=tau_misuse,
                tau_omission=tau_omission,
                tau_strategy=tau_strategy,
            )
            row.update(
                epsilon=epsilon,
                tau_misuse=tau_misuse,
                tau_omission=tau_omission,
                tau_strategy=tau_strategy,
            )
            if _complete_policy_rows([row], expected_n=len(validation_card_ids)):
                complete_pm_rows.append(row)

        response_first = _select_near_best_then_low_risk_cost(
            complete_pm_rows,
            response_margin=0.02,
            misuse_margin=0.02,
        )
        safety_first = _select_safety_first(
            complete_pm_rows,
            safety_margin=args.safety_margin,
        )

        rule_policy = StrongRulePolicy(
            _rule_for_selection(selection_path),
            strategy_retriever,
        )
        rule_eval = evaluate_policy_on_labels(
            states,
            validation_card_ids,
            rule_policy.choose,
            response,
            memory.misuse_risk,
            costs,
            omission_risks=memory.omission_risk,
            strategy_risks=strategy.risk,
        )
        if int(rule_eval["n"]) != len(validation_card_ids):
            raise RuntimeError(f"incomplete rule rows for fold {fold}")

        rule_by_card = {row["card_id"]: row for row in rule_eval["rows"]}
        safe_by_card = {row["card_id"]: row for row in safety_first["rows"]}
        for card_id in sorted(validation_card_ids):
            state = states[card_id]
            pm_row = safe_by_card[card_id]
            rule_row = rule_by_card[card_id]
            out = {
                "fold": fold,
                "card_id": card_id,
                "state_id": state.state_id,
                "user_id": state.user_id,
                "semantic_family": state.semantic_family,
                "pm_action": pm_row["action_id"],
                "rule_action": rule_row["action_id"],
            }
            for metric in (
                "response_score",
                "misuse_risk",
                "memory_omission_risk",
                "strategy_decision_risk",
                "safety_risk",
                "cost",
            ):
                out[f"pm_{metric}"] = pm_row[metric]
                out[f"rule_{metric}"] = rule_row[metric]
                out[f"delta_{metric}"] = pm_row[metric] - rule_row[metric]
            paired_rows.append(out)

        per_fold.append({
            "fold": fold,
            "checkpoint": str(checkpoint),
            "n_validation_cards": len(validation_card_ids),
            "n_complete_pm_grid_rows": len(complete_pm_rows),
            "n_score_failures": len(score_failures),
            "response_first": {
                "config": {
                    key: response_first[key]
                    for key in ("epsilon", "tau_misuse", "tau_omission", "tau_strategy")
                },
                "metrics": _metric_summary(response_first),
            },
            "safety_first": {
                "config": {
                    key: safety_first[key]
                    for key in ("epsilon", "tau_misuse", "tau_omission", "tau_strategy")
                },
                "metrics": _metric_summary(safety_first),
            },
            "strong_rule": {
                "config": asdict(rule_policy.config),
                "metrics": _metric_summary(rule_eval),
            },
        })

    report = {
        "analysis_type": "development_safety_first_selection",
        "feature_mode": args.feature_mode,
        "seed": args.seed,
        "fold_mode": args.fold_mode,
        "safety_margin": args.safety_margin,
        "per_fold": per_fold,
        "safety_first_vs_rule_ci": _selection_cis(paired_rows),
        "interpretation": (
            "Diagnostic only. This evaluates whether the trained PM has a "
            "conservative operating point under the same validation labels; it "
            "does not change full judging labels or external evaluation."
        ),
    }
    write_json(args.out, report)
    print({
        "out": str(args.out),
        "n_folds": len(per_fold),
        "n_rows": report["safety_first_vs_rule_ci"]["n_rows"],
        "response_delta_ci": report["safety_first_vs_rule_ci"]["metrics"]["response_score"]["state_cluster_ci"],
        "safety_delta_ci": report["safety_first_vs_rule_ci"]["metrics"]["safety_risk"]["state_cluster_ci"],
        "cost_delta_ci": report["safety_first_vs_rule_ci"]["metrics"]["cost"]["state_cluster_ci"],
    })


if __name__ == "__main__":
    main()
