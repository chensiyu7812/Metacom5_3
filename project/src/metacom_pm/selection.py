from __future__ import annotations

from dataclasses import asdict
from itertools import product
from pathlib import Path
from typing import Any, Callable
import numpy as np

from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import ActionOutcome, RuntimeState, StrategyCard
from .io import iter_jsonl, sha256_file, write_json
from .labels import action_response_scores, load_memory_labels, load_strategy_labels
from .policies import (
    FixedPolicy,
    LearnedPMPolicy,
    RuleConfig,
    StrongRulePolicy,
    estimated_action_cost,
)
from .retrieval import StrategyRetriever
from .sweep import load_states
from .training import PMModel


def _outcome_costs(path: str | Path) -> dict[tuple[str, str], float]:
    values = {}
    for row in iter_jsonl(path):
        outcome = ActionOutcome.model_validate(row)
        values[(outcome.card_id, outcome.action_id)] = float(
            outcome.cost.total_input_tokens
        )
    return values


def evaluate_policy_on_labels(
    states: dict[str, RuntimeState],
    card_ids: set[str],
    choose: Callable[[RuntimeState], str],
    response_scores: dict[tuple[str, str], float],
    misuse_risks: dict[tuple[str, str], float],
    costs: dict[tuple[str, str], float],
    *,
    omission_risks: dict[tuple[str, str], float] | None = None,
    strategy_risks: dict[tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    omission_risks = omission_risks or {}
    strategy_risks = strategy_risks or {}
    rows = []
    failures = []
    for card_id in sorted(card_ids):
        state = states[card_id]
        try:
            action = choose(state)
        except Exception as exc:
            failures.append({"card_id": card_id, "error": str(exc)})
            continue
        report = getattr(getattr(choose, "__self__", None), "last_decision_report", None)
        fallback_used = bool(report and report.get("constraint_fallback_used"))
        key = (card_id, action)
        if key not in response_scores or key not in misuse_risks or key not in costs:
            continue
        misuse = float(misuse_risks[key])
        omission = float(omission_risks.get(key, 0.0))
        strategy = float(strategy_risks.get(key, 0.0))
        rows.append({
            "card_id": card_id,
            "action_id": action,
            "response_score": response_scores[key],
            "misuse_risk": misuse,
            "memory_omission_risk": omission,
            "strategy_decision_risk": strategy,
            "safety_risk": max(misuse, omission, strategy),
            "cost": costs[key],
            "constraint_fallback_used": fallback_used,
        })
    if not rows:
        return {"n": 0, "failures": failures}
    return {
        "n": len(rows),
        "n_failures": len(failures),
        "mean_response_score": float(np.mean([x["response_score"] for x in rows])),
        "mean_misuse_risk": float(np.mean([x["misuse_risk"] for x in rows])),
        "mean_memory_omission_risk": float(np.mean([x["memory_omission_risk"] for x in rows])),
        "mean_strategy_decision_risk": float(np.mean([x["strategy_decision_risk"] for x in rows])),
        "mean_safety_risk": float(np.mean([x["safety_risk"] for x in rows])),
        "mean_cost": float(np.mean([x["cost"] for x in rows])),
        "constraint_fallback_rate": float(np.mean([
            bool(x["constraint_fallback_used"]) for x in rows
        ])) if rows else 0.0,
        "action_distribution": dict(__import__("collections").Counter(
            x["action_id"] for x in rows
        )),
        "rows": rows,
        "failures": failures,
    }


def _select_near_best_then_low_risk_cost(
    rows: list[dict[str, Any]],
    *,
    response_margin: float = 0.02,
    misuse_margin: float = 0.02,
) -> dict[str, Any]:
    valid = [x for x in rows if x.get("n")]
    if not valid:
        raise ValueError("no valid validation policy rows")
    best_response = max(float(x["mean_response_score"]) for x in valid)
    quality_set = [
        x for x in valid
        if float(x["mean_response_score"]) >= best_response - response_margin
    ]
    best_risk = min(float(x.get("mean_safety_risk", x["mean_misuse_risk"])) for x in quality_set)
    safe_set = [
        x for x in quality_set
        if float(x.get("mean_safety_risk", x["mean_misuse_risk"])) <= best_risk + misuse_margin
    ]
    return min(
        safe_set,
        key=lambda x: (
            float(x["mean_cost"]),
            -float(x["mean_response_score"]),
            float(x.get("mean_safety_risk", x["mean_misuse_risk"])),
            str(x.get("action_id") or x.get("config") or x.get("epsilon")),
        ),
    )


def _compact_policy_result(row: dict[str, Any]) -> dict[str, Any]:
    """Return metrics useful for reporting without per-card rows."""
    return {
        key: value
        for key, value in row.items()
        if key not in {"rows", "failures"}
    }


def _complete_policy_rows(
    rows: list[dict[str, Any]],
    *,
    expected_n: int,
) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if int(row.get("n", 0)) == expected_n
        and int(row.get("n_failures", 0)) == 0
        and float(row.get("constraint_fallback_rate", 0.0)) == 0.0
    ]


def _choose_from_cached_pm_scores(
    state: RuntimeState,
    scores: dict[str, dict[str, float]],
    *,
    epsilon: float,
    tau_misuse: float,
    tau_omission: float,
    tau_strategy: float,
) -> tuple[str, bool]:
    safe = [
        action_id for action_id, value in scores.items()
        if value["misuse_risk"] <= tau_misuse
        and value["memory_omission_risk"] <= tau_omission
        and value["strategy_decision_risk"] <= tau_strategy
    ]
    fallback_used = False
    if safe:
        qmax_safe = max(scores[x]["response_score"] for x in safe)
        candidates = [
            action_id for action_id in safe
            if scores[action_id]["response_score"] >= qmax_safe - epsilon
        ]
    else:
        fallback_used = True

        def violation(value: float, threshold: float) -> float:
            return max(0.0, value - threshold) / max(threshold, 1e-6)

        def violation_tuple(action_id: str):
            value = scores[action_id]
            violations = (
                violation(value["misuse_risk"], tau_misuse),
                violation(value["memory_omission_risk"], tau_omission),
                violation(value["strategy_decision_risk"], tau_strategy),
            )
            return (max(violations), sum(violations))

        best_violation = min(violation_tuple(x) for x in scores)
        candidates = [
            action_id for action_id in scores
            if violation_tuple(action_id) == best_violation
        ]
        qmax = max(scores[x]["response_score"] for x in candidates)
        candidates = [
            x for x in candidates
            if scores[x]["response_score"] >= qmax - epsilon
        ]

    chosen = min(
        candidates,
        key=lambda action_id: (
            estimated_action_cost(state, action_id),
            -scores[action_id]["memory_decision_quality"],
            -scores[action_id]["strategy_decision_quality"],
            -scores[action_id]["response_score"],
            action_id,
        ),
    )
    return chosen, fallback_used


def _evaluate_cached_pm_grid_row(
    states: dict[str, RuntimeState],
    card_ids: set[str],
    score_cache: dict[str, dict[str, dict[str, float]]],
    score_failures: dict[str, str],
    response_scores: dict[tuple[str, str], float],
    misuse_risks: dict[tuple[str, str], float],
    omission_risks: dict[tuple[str, str], float],
    strategy_risks: dict[tuple[str, str], float],
    costs: dict[tuple[str, str], float],
    *,
    epsilon: float,
    tau_misuse: float,
    tau_omission: float,
    tau_strategy: float,
) -> dict[str, Any]:
    rows = []
    failures = [
        {"card_id": card_id, "error": error}
        for card_id, error in sorted(score_failures.items())
        if card_id in card_ids
    ]
    for card_id in sorted(card_ids):
        if card_id in score_failures:
            continue
        state = states[card_id]
        scores = score_cache[card_id]
        try:
            action, fallback_used = _choose_from_cached_pm_scores(
                state,
                scores,
                epsilon=epsilon,
                tau_misuse=tau_misuse,
                tau_omission=tau_omission,
                tau_strategy=tau_strategy,
            )
        except Exception as exc:
            failures.append({"card_id": card_id, "error": str(exc)})
            continue
        key = (card_id, action)
        if key not in response_scores or key not in misuse_risks or key not in costs:
            failures.append({
                "card_id": card_id,
                "action_id": action,
                "error": "missing evaluation label or cost",
            })
            continue
        misuse = float(misuse_risks[key])
        omission = float(omission_risks.get(key, 0.0))
        strategy = float(strategy_risks.get(key, 0.0))
        rows.append({
            "card_id": card_id,
            "action_id": action,
            "response_score": response_scores[key],
            "misuse_risk": misuse,
            "memory_omission_risk": omission,
            "strategy_decision_risk": strategy,
            "safety_risk": max(misuse, omission, strategy),
            "cost": costs[key],
            "constraint_fallback_used": fallback_used,
        })
    if not rows:
        return {"n": 0, "n_failures": len(failures), "failures": failures}
    return {
        "n": len(rows),
        "n_failures": len(failures),
        "mean_response_score": float(np.mean([x["response_score"] for x in rows])),
        "mean_misuse_risk": float(np.mean([x["misuse_risk"] for x in rows])),
        "mean_memory_omission_risk": float(np.mean([x["memory_omission_risk"] for x in rows])),
        "mean_strategy_decision_risk": float(np.mean([x["strategy_decision_risk"] for x in rows])),
        "mean_safety_risk": float(np.mean([x["safety_risk"] for x in rows])),
        "mean_cost": float(np.mean([x["cost"] for x in rows])),
        "constraint_fallback_rate": float(np.mean([
            bool(x["constraint_fallback_used"]) for x in rows
        ])) if rows else 0.0,
        "action_distribution": dict(__import__("collections").Counter(
            x["action_id"] for x in rows
        )),
        "rows": rows,
        "failures": failures,
    }


def tune_validation_policies(
    runtime_path: str | Path,
    outcomes_path: str | Path,
    response_path: str | Path,
    m0_path: str | Path,
    m2_path: str | Path,
    strategy_use_path: str | Path,
    strategy_omission_path: str | Path,
    strategy_bank_path: str | Path,
    checkpoint_path: str | Path,
    validation_card_ids: set[str],
    out_path: str | Path,
    *,
    m2b_path: str | Path | None = None,
    require_m2b: bool = True,
    judging_attestation_path: str | Path | None = None,
    m2b_attestation_path: str | Path | None = None,
    checkpoint_attestation_path: str | Path | None = None,
    outcomes_attestation_path: str | Path | None = None,
    require_checkpoint_attestation: bool = True,
    out_attestation_path: str | Path | None = None,
    response_margin: float = 0.02,
    misuse_margin: float = 0.02,
) -> dict[str, Any]:
    runtime_path = Path(runtime_path).resolve()
    outcomes_path = Path(outcomes_path).resolve()
    response_path = Path(response_path).resolve()
    m0_path = Path(m0_path).resolve()
    m2_path = Path(m2_path).resolve()
    strategy_use_path = Path(strategy_use_path).resolve()
    strategy_omission_path = Path(strategy_omission_path).resolve()
    strategy_bank_path = Path(strategy_bank_path).resolve()
    checkpoint_path = Path(checkpoint_path).resolve()
    out_path = Path(out_path).resolve()
    m2b_path = Path(m2b_path).resolve() if m2b_path is not None else None
    if require_m2b and m2b_path is None:
        raise RuntimeError(
            "M2b selected-set omission labels are required for V3.3 validation "
            "selection. Pass --m2b-path, or explicitly use --allow-no-m2b for "
            "non-reportable debugging."
        )
    judging_attestation_path = Path(
        judging_attestation_path or response_path.parent / "artifact_attestation.json"
    ).resolve()
    judging_verification = require_artifact_attestation(
        judging_attestation_path,
        required_stage="full_judging",
        required_output_paths={
            "response_pairs": response_path,
            "memory_omission": m0_path,
            "memory_use": m2_path,
            "strategy_use": strategy_use_path,
            "strategy_omission": strategy_omission_path,
        },
    )
    outcomes_attestation_path = Path(
        outcomes_attestation_path or outcomes_path.parent / "artifact_attestation.json"
    ).resolve()
    outcomes_verification = require_artifact_attestation(
        outcomes_attestation_path,
        required_stage="action_sweep",
        required_output_paths={"action_outcomes": outcomes_path},
    )
    m2b_verification = None
    if m2b_path is not None:
        m2b_attestation_path = Path(
            m2b_attestation_path or m2b_path.parent / "artifact_attestation.json"
        ).resolve()
        m2b_verification = require_artifact_attestation(
            m2b_attestation_path,
            required_stage="m2b_selected_set_omission",
            required_output_paths={"memory_selected_set_omission": m2b_path},
        )
    checkpoint_verification = None
    checkpoint_attestation_path = Path(
        checkpoint_attestation_path
        or checkpoint_path.with_suffix(checkpoint_path.suffix + ".attestation.json")
    ).resolve()
    if require_checkpoint_attestation or checkpoint_attestation_path.is_file():
        checkpoint_verification = require_artifact_attestation(
            checkpoint_attestation_path,
            required_stage="pm_training",
            required_output_paths={"checkpoint": checkpoint_path},
        )

    states = load_states(runtime_path)
    response = action_response_scores(response_path)
    memory = load_memory_labels(m0_path, m2_path, m2b_path)
    strategy_labels = load_strategy_labels(strategy_use_path, strategy_omission_path)
    if m2b_path is not None:
        expected_m2b_keys = {
            (card_id, action_id)
            for card_id in validation_card_ids
            for action_id in states[card_id].allowed_actions
            if not action_id.startswith("M0+")
        }
        missing_m2b = expected_m2b_keys - set(memory.m2b_omission_keys)
        if missing_m2b:
            raise RuntimeError(
                "M2b selected-set omission supervision is incomplete or stale for "
                "validation selection: "
                f"missing={sorted(missing_m2b)[:10]}"
            )
    risks = memory.misuse_risk
    omission_risks = memory.omission_risk
    strategy_risks = strategy_labels.risk
    costs = _outcome_costs(outcomes_path)
    model = PMModel.load(checkpoint_path)
    strategy_cards = [
        StrategyCard.model_validate(row) for row in iter_jsonl(strategy_bank_path)
    ]
    retriever = StrategyRetriever(strategy_cards)

    # Best fixed is selected across all validation cards with the preregistered
    # fallback: drop unavailable memory sources and retain R0/RS.
    fixed_results = {}
    for action in __import__("metacom_pm.contracts", fromlist=["ALL_ACTION_IDS"]).ALL_ACTION_IDS:
        policy = FixedPolicy(action)
        fixed_results[action] = evaluate_policy_on_labels(
            states, validation_card_ids, policy.choose,
            response, risks, costs,
            omission_risks=omission_risks, strategy_risks=strategy_risks,
        )
    expected_n = len(validation_card_ids)
    complete_fixed_results = {
        action: result
        for action, result in fixed_results.items()
        if int(result.get("n", 0)) == expected_n
        and int(result.get("n_failures", 0)) == 0
    }
    if not complete_fixed_results:
        raise ValueError("no complete fixed-policy validation rows")
    fixed_rows = [
        {"action_id": action, **result}
        for action, result in complete_fixed_results.items()
    ]
    best_fixed_row = _select_near_best_then_low_risk_cost(
        fixed_rows, response_margin=response_margin, misuse_margin=misuse_margin
    )
    best_fixed = str(best_fixed_row["action_id"])

    # Tune PM constraint thresholds without test data.  Fallback is allowed only
    # during grid search so invalid settings can be observed and rejected.
    score_cache: dict[str, dict[str, dict[str, float]]] = {}
    score_failures: dict[str, str] = {}
    for card_id in sorted(validation_card_ids):
        state = states[card_id]
        try:
            score_cache[card_id] = model.score_actions(state, state.allowed_actions)
        except Exception as exc:
            score_failures[card_id] = str(exc)

    pm_grid = []
    pm_grid_all = []
    for epsilon, tau_misuse, tau_omission, tau_strategy in product(
        [0.0, 0.05, 0.10, 0.15, 0.20, 0.30],
        [0.25, 0.35, 0.50, 0.75, 1.0],
        [0.25, 0.35, 0.50, 0.75, 1.0],
        [0.25, 0.35, 0.50, 0.75, 1.0],
    ):
        result = _evaluate_cached_pm_grid_row(
            states,
            validation_card_ids,
            score_cache,
            score_failures,
            response,
            risks,
            omission_risks=omission_risks, strategy_risks=strategy_risks,
            costs=costs,
            epsilon=epsilon,
            tau_misuse=tau_misuse,
            tau_omission=tau_omission,
            tau_strategy=tau_strategy,
        )
        row = {
            "epsilon": epsilon,
            "tau_misuse": tau_misuse,
            "tau_omission": tau_omission,
            "tau_strategy": tau_strategy,
            **result,
        }
        pm_grid_all.append(row)
        if _complete_policy_rows([row], expected_n=expected_n):
            pm_grid.append(row)
    # Constrained validation selection: remain near the best response score,
    # then remain near the safest candidate, then minimize cost.
    best_pm = _select_near_best_then_low_risk_cost(
        pm_grid, response_margin=response_margin, misuse_margin=misuse_margin
    )

    # Budget-matched fixed is selected after PM threshold tuning so the budget
    # actually matches the deployment policy being compared.
    budget_fixed_rows = [
        row for row in fixed_rows
        if float(row["mean_cost"]) <= float(best_pm["mean_cost"])
    ]
    if not budget_fixed_rows:
        budget_fixed_rows = [min(fixed_rows, key=lambda row: float(row["mean_cost"]))]
    budget_fixed_row = _select_near_best_then_low_risk_cost(
        budget_fixed_rows,
        response_margin=response_margin,
        misuse_margin=misuse_margin,
    )
    budget_fixed = str(budget_fixed_row["action_id"])

    # Strong rule grid gets exactly the same visible inventory/catalog access.
    rule_grid = []
    threshold_values = [0.0, 0.04, 0.08, 0.12, 0.18]
    for common_threshold, strategy_threshold, max_sources in product(
        threshold_values, threshold_values, [1, 2, 3]
    ):
        config = RuleConfig(
            mp_threshold=common_threshold,
            ms_threshold=common_threshold,
            me_threshold=common_threshold,
            strategy_threshold=strategy_threshold,
            max_sources=max_sources,
        )
        policy = StrongRulePolicy(config, retriever)
        result = evaluate_policy_on_labels(
            states, validation_card_ids, policy.choose,
            response, risks, costs,
            omission_risks=omission_risks, strategy_risks=strategy_risks,
        )
        rule_grid.append({"config": asdict(config), **result})
    best_rule = _select_near_best_then_low_risk_cost(
        _complete_policy_rows(rule_grid, expected_n=expected_n),
        response_margin=response_margin,
        misuse_margin=misuse_margin,
    )

    result = {
        "best_fixed_action": best_fixed,
        "budget_matched_fixed_action": budget_fixed,
        "pm": {
            "epsilon": best_pm["epsilon"],
            "tau_misuse": best_pm["tau_misuse"],
            "tau_omission": best_pm["tau_omission"],
            "tau_strategy": best_pm["tau_strategy"],
            "confirmatory_allow_constraint_fallback": False,
            "validation_metrics": {
                key: best_pm[key] for key in (
                    "n", "mean_response_score", "mean_misuse_risk",
                    "mean_memory_omission_risk", "mean_strategy_decision_risk", "mean_safety_risk",
                    "mean_cost", "action_distribution"
                )
            },
        },
        "strong_rule": {
            "config": best_rule["config"],
            "validation_metrics": {
                key: best_rule[key] for key in (
                    "n", "mean_response_score", "mean_misuse_risk",
                    "mean_memory_omission_risk", "mean_strategy_decision_risk", "mean_safety_risk",
                    "mean_cost", "action_distribution"
                )
            },
        },
        "fixed_results": {
            action: _compact_policy_result(result)
            for action, result in fixed_results.items()
        },
        "pm_grid_diagnostics": {
            "n_total": len(pm_grid_all),
            "n_complete_no_fallback": len(pm_grid),
            "score_failures": [
                {"card_id": card_id, "error": error}
                for card_id, error in sorted(score_failures.items())
            ],
        },
        "selection_scope": "validation_only",
        "selection_margins": {
            "response_margin": response_margin,
            "safety_margin": misuse_margin,
        },
        "provenance": {
            "runtime_path": str(runtime_path),
            "runtime_sha256": sha256_file(runtime_path),
            "outcomes_path": str(outcomes_path),
            "outcomes_sha256": sha256_file(outcomes_path),
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_sha256": sha256_file(checkpoint_path),
            "strategy_bank_path": str(strategy_bank_path),
            "strategy_bank_sha256": sha256_file(strategy_bank_path),
            "full_judging_attestation": judging_verification,
            "action_sweep_attestation": outcomes_verification,
            "m2b_attestation": m2b_verification,
            "checkpoint_attestation": checkpoint_verification,
            "m2b_required": bool(require_m2b),
            "m2b_enabled": m2b_path is not None,
        },
    }
    write_json(out_path, result)
    out_attestation_path = Path(
        out_attestation_path or out_path.with_suffix(out_path.suffix + ".attestation.json")
    ).resolve()
    create_artifact_attestation(
        out_attestation_path,
        stage="validation_selection",
        inputs={
            "runtime": runtime_path,
            "action_outcomes": outcomes_path,
            "response_pairs": response_path,
            "memory_omission": m0_path,
            "memory_use": m2_path,
            **({"memory_selected_set_omission": m2b_path} if m2b_path is not None else {}),
            "strategy_use": strategy_use_path,
            "strategy_omission": strategy_omission_path,
            "strategy_bank": strategy_bank_path,
            "checkpoint": checkpoint_path,
            "action_sweep_attestation": outcomes_attestation_path,
            "full_judging_attestation": judging_attestation_path,
            **({"m2b_attestation": Path(m2b_attestation_path)} if m2b_verification else {}),
            **({"checkpoint_attestation": checkpoint_attestation_path} if checkpoint_verification else {}),
        },
        outputs={"selection": (out_path, False)},
        parameters={
            "response_margin": response_margin,
            "safety_margin": misuse_margin,
            "require_m2b": bool(require_m2b),
            "m2b_enabled": m2b_path is not None,
            "validation_card_ids": len(validation_card_ids),
        },
        expected={
            "validation_cards": len(validation_card_ids),
            "pm_grid_total": result["pm_grid_diagnostics"]["n_total"],
            "pm_grid_complete_no_fallback": result["pm_grid_diagnostics"]["n_complete_no_fallback"],
        },
    )
    result["selection_attestation"] = str(out_attestation_path)
    return result
