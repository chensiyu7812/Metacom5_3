#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from metacom_pm.contracts import (
    MemorySource,
    StrategyCard,
    StrategyMode,
    canonical_action_id,
    parse_action_id,
)
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
    return {
        key: _round(row[key])
        for key in (
            "n",
            "mean_response_score",
            "mean_misuse_risk",
            "mean_memory_omission_risk",
            "mean_strategy_decision_risk",
            "mean_safety_risk",
            "mean_cost",
            "action_distribution",
        )
    }


def _select_safety_first(rows: list[dict[str, Any]], safety_margin: float) -> dict[str, Any]:
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


def _paired_cis(rows: list[dict[str, Any]], *, prefix: str) -> dict[str, Any]:
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
        key = f"{prefix}_minus_rule_{metric}"
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


def _evaluate_action_map(
    *,
    states,
    validation_card_ids: set[str],
    action_by_card: dict[str, str],
    response,
    memory,
    strategy,
    costs,
) -> dict[str, Any]:
    rows = []
    failures = []
    for card_id in sorted(validation_card_ids):
        action = action_by_card[card_id]
        key = (card_id, action)
        if (
            key not in response
            or key not in memory.misuse_risk
            or key not in memory.omission_risk
            or key not in strategy.risk
            or key not in costs
        ):
            failures.append({
                "card_id": card_id,
                "action_id": action,
                "error": "missing label or cost for guarded action",
            })
            continue
        misuse = float(memory.misuse_risk[key])
        omission = float(memory.omission_risk[key])
        strategy_risk = float(strategy.risk[key])
        rows.append({
            "card_id": card_id,
            "action_id": action,
            "response_score": float(response[key]),
            "misuse_risk": misuse,
            "memory_omission_risk": omission,
            "strategy_decision_risk": strategy_risk,
            "safety_risk": max(misuse, omission, strategy_risk),
            "cost": float(costs[key]),
            "constraint_fallback_used": False,
        })
    if not rows:
        return {"n": 0, "n_failures": len(failures), "rows": [], "failures": failures}
    return {
        "n": len(rows),
        "n_failures": len(failures),
        "mean_response_score": float(mean(row["response_score"] for row in rows)),
        "mean_misuse_risk": float(mean(row["misuse_risk"] for row in rows)),
        "mean_memory_omission_risk": float(mean(row["memory_omission_risk"] for row in rows)),
        "mean_strategy_decision_risk": float(mean(row["strategy_decision_risk"] for row in rows)),
        "mean_safety_risk": float(mean(row["safety_risk"] for row in rows)),
        "mean_cost": float(mean(row["cost"] for row in rows)),
        "constraint_fallback_rate": 0.0,
        "action_distribution": dict(__import__("collections").Counter(row["action_id"] for row in rows)),
        "rows": rows,
        "failures": failures,
    }


def _combine_actions(
    pm_action: str,
    rule_action: str,
    *,
    mode: str,
) -> str:
    pm_sources, pm_strategy = parse_action_id(pm_action)
    rule_sources, rule_strategy = parse_action_id(rule_action)
    if mode == "memory_union":
        sources = pm_sources | rule_sources
        strategy = pm_strategy
    elif mode == "memory_strategy_union":
        sources = pm_sources | rule_sources
        strategy = StrategyMode.RS if StrategyMode.RS in {pm_strategy, rule_strategy} else StrategyMode.R0
    elif mode == "rule_memory_only":
        sources = rule_sources
        strategy = pm_strategy
    else:
        raise ValueError(f"unknown guardrail mode: {mode}")
    return canonical_action_id(frozenset(sources), strategy)


def _rule_for_selection(path: Path) -> RuleConfig:
    selection = json.loads(path.read_text(encoding="utf-8"))
    return RuleConfig(**selection["strong_rule"]["config"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature-mode", default="text_metadata")
    parser.add_argument("--fold-mode", default="user")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--safety-margin", type=float, default=0.02)
    parser.add_argument(
        "--pm-base",
        choices=["response_first", "safety_first"],
        default="response_first",
        help="Which PM operating point should receive the rule coverage guardrail.",
    )
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
        default=ROOT / "outputs/coverage_guardrail_m2b_text_metadata_seed17.json",
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
    retriever = StrategyRetriever(strategy_cards)

    per_fold = []
    paired_rows = []
    for fold, validation_card_ids in sorted(folds.items()):
        checkpoint = (
            args.models_dir
            / f"{args.feature_mode}_{args.fold_mode}_fold{fold}_seed{args.seed}.joblib"
        )
        selection_path = (
            ROOT
            / f"outputs/selection_m2b_{args.feature_mode}_fold{fold}_seed{args.seed}.json"
        )
        if not checkpoint.exists():
            raise FileNotFoundError(checkpoint)
        if not selection_path.exists():
            raise FileNotFoundError(selection_path)

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

        pm_rows = []
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
                pm_rows.append(row)

        response_first = _select_near_best_then_low_risk_cost(
            pm_rows,
            response_margin=0.02,
            misuse_margin=0.02,
        )
        safety_first = _select_safety_first(pm_rows, args.safety_margin)
        base_pm = response_first if args.pm_base == "response_first" else safety_first

        rule_policy = StrongRulePolicy(_rule_for_selection(selection_path), retriever)
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

        pm_by_card = {row["card_id"]: row for row in base_pm["rows"]}
        rule_by_card = {row["card_id"]: row for row in rule_eval["rows"]}
        guarded_evals = {}
        for mode in ("memory_union", "memory_strategy_union", "rule_memory_only"):
            guarded_actions = {
                card_id: _combine_actions(
                    pm_by_card[card_id]["action_id"],
                    rule_by_card[card_id]["action_id"],
                    mode=mode,
                )
                for card_id in validation_card_ids
            }
            guarded_evals[mode] = _evaluate_action_map(
                states=states,
                validation_card_ids=validation_card_ids,
                action_by_card=guarded_actions,
                response=response,
                memory=memory,
                strategy=strategy,
                costs=costs,
            )
            if int(guarded_evals[mode]["n"]) != len(validation_card_ids):
                raise RuntimeError(
                    f"incomplete guarded rows for fold {fold} mode={mode}: "
                    f"{guarded_evals[mode].get('failures')[:3]}"
                )

        for card_id in sorted(validation_card_ids):
            state = states[card_id]
            rule_row = rule_by_card[card_id]
            out = {
                "fold": fold,
                "card_id": card_id,
                "state_id": state.state_id,
                "user_id": state.user_id,
                "semantic_family": state.semantic_family,
                "pm_action": pm_by_card[card_id]["action_id"],
                "rule_action": rule_row["action_id"],
            }
            guarded_by_mode = {
                mode: {row["card_id"]: row for row in eval_row["rows"]}[card_id]
                for mode, eval_row in guarded_evals.items()
            }
            for mode, guarded_row in guarded_by_mode.items():
                out[f"{mode}_action"] = guarded_row["action_id"]
                for metric in (
                    "response_score",
                    "misuse_risk",
                    "memory_omission_risk",
                    "strategy_decision_risk",
                    "safety_risk",
                    "cost",
                ):
                    out[f"{mode}_{metric}"] = guarded_row[metric]
                    out[f"{mode}_minus_rule_{metric}"] = guarded_row[metric] - rule_row[metric]
            paired_rows.append(out)

        per_fold.append({
            "fold": fold,
            "checkpoint": str(checkpoint),
            "base_pm": args.pm_base,
            "n_validation_cards": len(validation_card_ids),
            "n_complete_pm_grid_rows": len(pm_rows),
            "n_score_failures": len(score_failures),
            "base_pm_selection": {
                "config": {
                    key: base_pm[key]
                    for key in ("epsilon", "tau_misuse", "tau_omission", "tau_strategy")
                },
                "metrics": _metric_summary(base_pm),
            },
            "strong_rule": {
                "config": asdict(rule_policy.config),
                "metrics": _metric_summary(rule_eval),
            },
            "guarded": {
                mode: _metric_summary(eval_row)
                for mode, eval_row in guarded_evals.items()
            },
        })

    report = {
        "analysis_type": "development_pm_rule_coverage_guardrail",
        "feature_mode": args.feature_mode,
        "fold_mode": args.fold_mode,
        "seed": args.seed,
        "pm_base": args.pm_base,
        "guardrail_modes": {
            "memory_union": "PM memory sources union strong-rule memory sources; PM strategy retained.",
            "memory_strategy_union": "PM memory sources union strong-rule memory sources; RS if either PM or rule selects RS.",
            "rule_memory_only": "Strong-rule memory sources with PM strategy; isolates whether memory coverage alone explains omission.",
        },
        "per_fold": per_fold,
        "ci_vs_rule": {
            mode: _paired_cis(paired_rows, prefix=mode)
            for mode in ("memory_union", "memory_strategy_union", "rule_memory_only")
        },
        "interpretation": (
            "Diagnostic only. These hybrid policies use the validation-selected "
            "strong rule as a pre-evidence coverage guardrail. They should be "
            "reported as PM+rule variants, not as pure learned PM."
        ),
    }
    write_json(args.out, report)
    print({
        "out": str(args.out),
        "base_pm": args.pm_base,
        "n_rows": len(paired_rows),
        "mode_summaries": {
            mode: {
                "response_delta_ci": report["ci_vs_rule"][mode]["metrics"]["response_score"]["state_cluster_ci"],
                "omission_delta_ci": report["ci_vs_rule"][mode]["metrics"]["memory_omission_risk"]["state_cluster_ci"],
                "safety_delta_ci": report["ci_vs_rule"][mode]["metrics"]["safety_risk"]["state_cluster_ci"],
                "cost_delta_ci": report["ci_vs_rule"][mode]["metrics"]["cost"]["state_cluster_ci"],
            }
            for mode in report["ci_vs_rule"]
        },
    })


if __name__ == "__main__":
    main()
