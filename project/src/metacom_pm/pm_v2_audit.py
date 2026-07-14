from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Sequence

import numpy as np

from .contracts import MemorySource, StrategyMode, parse_action_id
from .pm_v2_contracts import ActionLabel, CompositeSpec, PMV2State, ResourceNeedRegime


EXPECTED_REGIME_CHECKS = {
    ResourceNeedRegime.CONTEXT_ONLY.value: "m0",
    ResourceNeedRegime.PROFILE_NEEDED.value: "mp",
    ResourceNeedRegime.SUMMARY_NEEDED.value: "ms",
    ResourceNeedRegime.EVENT_NEEDED.value: "me",
    ResourceNeedRegime.MULTI_SOURCE_NEEDED.value: "multi",
    ResourceNeedRegime.MEMORY_HARMFUL.value: "m0",
    ResourceNeedRegime.STRATEGY_HELPFUL.value: "rs",
    ResourceNeedRegime.STRATEGY_HARMFUL.value: "r0",
    ResourceNeedRegime.AMBIGUOUS.value: "ambiguous",
}


def _quality(label: ActionLabel, spec: CompositeSpec) -> float:
    return spec.score(label.response)


def _risk(label: ActionLabel) -> float:
    values = label.risk.model_dump()
    return max(float(value) / 3.0 for value in values.values())


def _regime_pass(regime: str, action_id: str, quality_gap: float) -> bool:
    sources, strategy = parse_action_id(action_id)
    check = EXPECTED_REGIME_CHECKS.get(regime)
    if check == "m0":
        return not sources
    if check == "mp":
        return MemorySource.MP in sources
    if check == "ms":
        return MemorySource.MS in sources
    if check == "me":
        return MemorySource.ME in sources
    if check == "multi":
        return len(sources) >= 2
    if check == "rs":
        return strategy is StrategyMode.RS
    if check == "r0":
        return strategy is StrategyMode.R0
    if check == "ambiguous":
        return quality_gap <= 0.05
    return True


def audit_training_labels(
    states: Sequence[PMV2State],
    labels: Sequence[ActionLabel],
    *,
    risk_weight: float = 0.25,
    cost_weight: float = 0.10,
    maximum_single_action_share: float = 0.35,
    minimum_m0_share: float = 0.10,
    minimum_r0_share: float = 0.15,
    minimum_rs_share: float = 0.15,
    minimum_distinct_actions: int = 6,
    minimum_regime_pass_rate: float = 0.60,
    minimum_reliable_rate: float = 0.80,
) -> dict[str, Any]:
    """Fail closed when generated labels do not contain learnable policy diversity."""

    state_map = {state.state_id: state for state in states}
    by_state: dict[str, list[ActionLabel]] = defaultdict(list)
    for label in labels:
        if label.state_id in state_map:
            by_state[label.state_id].append(label)
    missing_states = sorted(set(state_map) - set(by_state))
    incomplete: list[dict[str, Any]] = []
    for state_id, state in state_map.items():
        observed = {label.action_id for label in by_state.get(state_id, [])}
        expected = set(state.allowed_actions)
        if observed != expected:
            incomplete.append(
                {
                    "state_id": state_id,
                    "missing": sorted(expected - observed),
                    "extra": sorted(observed - expected),
                }
            )
    if missing_states or incomplete:
        raise RuntimeError(
            "PM-v2 label table is incomplete: "
            f"missing_states={missing_states[:5]}, incomplete={incomplete[:5]}"
        )
    spec = CompositeSpec()
    reliable_rate = float(np.mean([label.label_reliable for label in labels]))
    cost_scale = max(float(np.mean([label.observed_input_tokens for label in labels])), 1.0)
    rows: list[dict[str, Any]] = []
    best_actions: list[str] = []
    regime_stats: dict[str, list[bool]] = defaultdict(list)
    for state_id, state_labels in sorted(by_state.items()):
        state = state_map[state_id]
        scored = []
        for label in state_labels:
            quality = _quality(label, spec)
            risk = _risk(label)
            utility = (
                quality
                - risk_weight * risk
                - cost_weight * (float(label.observed_input_tokens) / cost_scale)
            )
            scored.append((utility, quality, -risk, -label.observed_input_tokens, label.action_id))
        ranked = sorted(scored, reverse=True)
        best = ranked[0]
        best_action = best[-1]
        best_actions.append(best_action)
        quality_ranking = sorted((row[1], row[-1]) for row in ranked)[::-1]
        quality_gap = (
            float(quality_ranking[0][0] - quality_ranking[1][0])
            if len(quality_ranking) > 1
            else 0.0
        )
        regime = str(state.provenance.get("regime") or "unknown")
        passed = _regime_pass(regime, best_action, quality_gap)
        regime_stats[regime].append(passed)
        rows.append(
            {
                "state_id": state_id,
                "regime": regime,
                "best_action": best_action,
                "best_utility": float(best[0]),
                "top_quality_gap": quality_gap,
                "regime_expectation_passed": passed,
            }
        )
    counts = Counter(best_actions)
    n = max(len(best_actions), 1)
    m0_share = float(np.mean([not bool(parse_action_id(action)[0]) for action in best_actions]))
    r0_share = float(
        np.mean([parse_action_id(action)[1] is StrategyMode.R0 for action in best_actions])
    )
    rs_share = 1.0 - r0_share
    maximum_share = max(counts.values(), default=0) / n
    regime_summary = {
        regime: {
            "n": len(values),
            "pass_rate": float(np.mean(values)) if values else 0.0,
        }
        for regime, values in sorted(regime_stats.items())
    }
    failures: list[str] = []
    if reliable_rate < minimum_reliable_rate:
        failures.append("reliable_label_rate")
    if len(counts) < minimum_distinct_actions:
        failures.append("distinct_oracle_actions")
    if maximum_share > maximum_single_action_share:
        failures.append("single_action_dominance")
    if m0_share < minimum_m0_share:
        failures.append("m0_oracle_coverage")
    if r0_share < minimum_r0_share:
        failures.append("r0_oracle_coverage")
    if rs_share < minimum_rs_share:
        failures.append("rs_oracle_coverage")
    required_regimes = set(EXPECTED_REGIME_CHECKS)
    missing_regimes = sorted(required_regimes - set(regime_summary))
    if missing_regimes:
        failures.append("missing_regimes")
    low_regimes = [
        regime
        for regime, data in regime_summary.items()
        if regime in required_regimes and data["pass_rate"] < minimum_regime_pass_rate
    ]
    if low_regimes:
        failures.append("regime_alignment")
    report = {
        "status": "FAIL" if failures else "PASS",
        "n_states": len(by_state),
        "n_labels": len(labels),
        "reliable_label_rate": reliable_rate,
        "oracle_action_distribution": dict(counts),
        "oracle_distinct_actions": len(counts),
        "maximum_single_action_share": maximum_share,
        "m0_oracle_share": m0_share,
        "r0_oracle_share": r0_share,
        "rs_oracle_share": rs_share,
        "regime_summary": regime_summary,
        "missing_regimes": missing_regimes,
        "low_pass_regimes": low_regimes,
        "thresholds": {
            "maximum_single_action_share": maximum_single_action_share,
            "minimum_m0_share": minimum_m0_share,
            "minimum_r0_share": minimum_r0_share,
            "minimum_rs_share": minimum_rs_share,
            "minimum_distinct_actions": minimum_distinct_actions,
            "minimum_regime_pass_rate": minimum_regime_pass_rate,
            "minimum_reliable_rate": minimum_reliable_rate,
            "risk_weight": risk_weight,
            "cost_weight": cost_weight,
        },
        "failures": failures,
        "rows": rows,
    }
    if failures:
        raise RuntimeError("PM-v2 data/label diversity gate failed: " + str(report))
    return report
