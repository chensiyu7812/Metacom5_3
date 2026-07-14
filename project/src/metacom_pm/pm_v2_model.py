from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import joblib
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sklearn.ensemble import HistGradientBoostingRegressor

from .contracts import MemorySource, StrategyMode, canonical_action_id, parse_action_id
from .io import canonical_json, sha256_text
from .pm_v2_contracts import (
    ActionLabel,
    ActionPrediction,
    CompositeSpec,
    PMV2State,
    PolicyDecision,
    PredictionInterval,
    ResponseDimensions,
)
from .pm_v2_features import PMV2FeatureBuilder


RESPONSE_FIELDS = tuple(ResponseDimensions.model_fields)
RISK_FIELDS = (
    "selected_context_misuse",
    "unnecessary_exposure",
    "stale_or_conflicting_use",
    "unsupported_personal_claim",
    "memory_omission",
    "strategy_overuse",
    "strategy_omission",
)


class SelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: str = "pmv2-selection-v1"
    composite_spec: CompositeSpec = Field(default_factory=CompositeSpec)
    uncertainty_z: float = Field(default=1.0, ge=0.0, le=3.0)
    max_risk_ucb: float = Field(default=0.45, ge=0.0, le=1.0)
    risk_weight: float = Field(default=0.25, ge=0.0)
    cost_weight: float = Field(default=0.10, ge=0.0)
    resource_min_gain: float = Field(default=-0.02, ge=-1.0, le=1.0)
    strategy_min_gain: float = Field(default=-0.01, ge=-1.0, le=1.0)
    m0_omission_trigger: float = Field(default=0.35, ge=0.0, le=1.0)
    r0_strategy_omission_trigger: float = Field(default=0.35, ge=0.0, le=1.0)
    fallback_action: str = "M0+R0"
    fail_closed_on_ood: bool = True

    @model_validator(mode="after")
    def validate_fallback(self):
        parse_action_id(self.fallback_action)
        if self.risk_weight == 0 and self.cost_weight == 0:
            raise ValueError("at least one of risk_weight or cost_weight must be positive")
        return self

    def digest(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


@dataclass
class BootstrapRegressor:
    """Group-bootstrap ensemble for mean and epistemic uncertainty."""

    n_models: int = 7
    seed: int = 17
    max_iter: int = 180
    max_leaf_nodes: int = 15
    learning_rate: float = 0.05
    l2_regularization: float = 1.0
    models: list[HistGradientBoostingRegressor] = field(default_factory=list)

    def fit(
        self,
        x: np.ndarray,
        y: np.ndarray,
        groups: Sequence[str],
        sample_weight: np.ndarray | None = None,
    ) -> "BootstrapRegressor":
        if x.shape[0] != len(y) or len(y) != len(groups):
            raise ValueError("x, y and groups must have equal row counts")
        unique_groups = np.asarray(sorted(set(groups)), dtype=object)
        if unique_groups.size < 3:
            raise ValueError("group bootstrap requires at least three unique states")
        group_array = np.asarray(groups, dtype=object)
        rng = np.random.default_rng(self.seed)
        self.models = []
        for index in range(self.n_models):
            sampled_groups = rng.choice(unique_groups, size=len(unique_groups), replace=True)
            multiplicity: dict[str, int] = {}
            for group in sampled_groups:
                multiplicity[str(group)] = multiplicity.get(str(group), 0) + 1
            row_weights = np.asarray(
                [float(multiplicity.get(str(group), 0)) for group in group_array],
                dtype=float,
            )
            keep = row_weights > 0
            if sample_weight is not None:
                row_weights = row_weights * sample_weight
            model = HistGradientBoostingRegressor(
                loss="squared_error",
                learning_rate=self.learning_rate,
                max_iter=self.max_iter,
                max_leaf_nodes=self.max_leaf_nodes,
                l2_regularization=self.l2_regularization,
                random_state=self.seed + index,
            )
            model.fit(x[keep], y[keep], sample_weight=row_weights[keep])
            self.models.append(model)
        return self

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self.models:
            raise RuntimeError("bootstrap regressor is not fitted")
        matrix = np.vstack([model.predict(x) for model in self.models])
        return matrix.mean(axis=0), matrix.std(axis=0, ddof=0)


@dataclass
class PMV2Model:
    feature_builder: PMV2FeatureBuilder
    response_heads: dict[str, BootstrapRegressor]
    risk_heads: dict[str, BootstrapRegressor]
    selection_config: SelectionConfig
    format_version: str = "pm-v2.0"
    training_report: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def train(
        cls,
        states: Sequence[PMV2State],
        labels: Sequence[ActionLabel],
        *,
        selection_config: SelectionConfig | None = None,
        n_models: int = 7,
        seed: int = 17,
        reliable_only: bool = True,
        use_precomputed_embeddings: bool = True,
        word_features: int = 256,
        char_features: int = 256,
    ) -> "PMV2Model":
        state_map = {state.state_id: state for state in states}
        if len(state_map) != len(states):
            raise ValueError("duplicate PM-v2 state_id")
        usable = [label for label in labels if label.label_reliable or not reliable_only]
        if not usable:
            raise ValueError("no reliable PM-v2 action labels")
        missing_states = sorted({label.state_id for label in usable} - set(state_map))
        if missing_states:
            raise ValueError(f"labels reference unknown states: {missing_states[:5]}")
        labeled_actions: dict[str, set[str]] = {}
        for label in usable:
            labeled_actions.setdefault(label.state_id, set()).add(label.action_id)
        bad_states = [
            state_id
            for state_id, actions in labeled_actions.items()
            if "M0+R0" not in actions
        ]
        if bad_states:
            raise ValueError(
                "every training state must contain a labeled M0+R0 action; "
                f"missing for {bad_states[:5]}"
            )
        unique_states = [state_map[state_id] for state_id in sorted(labeled_actions)]
        builder = PMV2FeatureBuilder(
            word_features=word_features,
            char_features=char_features,
            use_precomputed_embeddings=use_precomputed_embeddings,
        ).fit(unique_states)
        rows = [(state_map[label.state_id], label.action_id) for label in usable]
        x = builder.transform(rows)
        groups = [label.state_id for label in usable]
        action_counts: dict[str, int] = {}
        for group in groups:
            action_counts[group] = action_counts.get(group, 0) + 1
        weights = np.asarray([1.0 / action_counts[group] for group in groups], dtype=float)

        response_heads: dict[str, BootstrapRegressor] = {}
        for field_name in RESPONSE_FIELDS:
            y = np.asarray(
                [
                    (float(getattr(label.response, field_name)) - 1.0) / 4.0
                    for label in usable
                ],
                dtype=float,
            )
            response_heads[field_name] = BootstrapRegressor(
                n_models=n_models, seed=seed
            ).fit(x, y, groups, weights)

        risk_heads: dict[str, BootstrapRegressor] = {}
        for field_name in RISK_FIELDS:
            y = np.asarray(
                [float(getattr(label.risk, field_name)) / 3.0 for label in usable],
                dtype=float,
            )
            risk_heads[field_name] = BootstrapRegressor(
                n_models=n_models, seed=seed + 101
            ).fit(x, y, groups, weights)

        report = {
            "n_states": len(unique_states),
            "n_action_labels": len(usable),
            "n_unreliable_labels_excluded": len(labels) - len(usable),
            "response_fields": list(RESPONSE_FIELDS),
            "risk_fields": list(RISK_FIELDS),
            "feature_config_hash": builder.config_hash(),
            "word_hash_features": word_features,
            "char_hash_features": char_features,
            "use_precomputed_embeddings": use_precomputed_embeddings,
            "m0_r0_coverage": 1.0,
        }
        return cls(
            feature_builder=builder,
            response_heads=response_heads,
            risk_heads=risk_heads,
            selection_config=selection_config or SelectionConfig(),
            training_report=report,
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: str | Path) -> "PMV2Model":
        value = joblib.load(path)
        if not isinstance(value, PMV2Model):
            raise TypeError("checkpoint is not a PMV2Model")
        if value.format_version != "pm-v2.0":
            raise RuntimeError(f"unsupported PM-v2 format: {value.format_version}")
        return value

    @staticmethod
    def _interval(
        mean: float,
        std: float,
        *,
        z: float,
        low: float,
        high: float,
    ) -> PredictionInterval:
        return PredictionInterval(
            mean=float(np.clip(mean, low, high)),
            std=float(max(0.0, std)),
            lower=float(np.clip(mean - z * std, low, high)),
            upper=float(np.clip(mean + z * std, low, high)),
        )

    def _raw_predictions(
        self, state: PMV2State
    ) -> tuple[dict[str, dict[str, PredictionInterval]], dict[str, dict[str, PredictionInterval]]]:
        actions = list(state.allowed_actions)
        x = self.feature_builder.transform([(state, action) for action in actions])
        z = self.selection_config.uncertainty_z
        response: dict[str, dict[str, PredictionInterval]] = {action: {} for action in actions}
        risk: dict[str, dict[str, PredictionInterval]] = {action: {} for action in actions}
        for field_name, head in self.response_heads.items():
            mean, std = head.predict(x)
            for index, action in enumerate(actions):
                response[action][field_name] = self._interval(
                    1.0 + 4.0 * float(mean[index]),
                    4.0 * float(std[index]),
                    z=z,
                    low=1.0,
                    high=5.0,
                )
        for field_name, head in self.risk_heads.items():
            mean, std = head.predict(x)
            for index, action in enumerate(actions):
                risk[action][field_name] = self._interval(
                    3.0 * float(mean[index]),
                    3.0 * float(std[index]),
                    z=z,
                    low=0.0,
                    high=3.0,
                )
        return response, risk

    def predict_actions(self, state: PMV2State) -> dict[str, ActionPrediction]:
        response, risk = self._raw_predictions(state)
        actions = list(state.allowed_actions)
        costs = {
            action: self.feature_builder.estimate_action_cost(state, action)
            for action in actions
        }
        max_cost = max(max(costs.values()), 1.0)
        spec = self.selection_config.composite_spec

        def quality(action: str, bound: str) -> float:
            values = {
                field_name: getattr(response[action][field_name], bound)
                for field_name in RESPONSE_FIELDS
            }
            return spec.score(ResponseDimensions(**values))

        quality_mean = {action: quality(action, "mean") for action in actions}
        quality_lcb = {action: quality(action, "lower") for action in actions}
        quality_ucb = {action: quality(action, "upper") for action in actions}
        risk_ucb = {
            action: max(risk[action][name].upper / 3.0 for name in RISK_FIELDS)
            for action in actions
        }
        baseline = "M0+R0" if "M0+R0" in actions else min(actions, key=costs.get)
        baseline_quality_ucb = quality_ucb[baseline]
        baseline_omission_ucb = risk[baseline]["memory_omission"].upper / 3.0
        predictions: dict[str, ActionPrediction] = {}
        for action in actions:
            sources, strategy = parse_action_id(action)
            reasons: list[str] = []
            feasible = risk_ucb[action] <= self.selection_config.max_risk_ucb
            if not feasible:
                reasons.append("risk_ucb_exceeds_threshold")
            resource_gate = True
            if sources:
                resource_gain = quality_lcb[action] - baseline_quality_ucb
                resource_gate = (
                    resource_gain >= self.selection_config.resource_min_gain
                    or baseline_omission_ucb >= self.selection_config.m0_omission_trigger
                )
                if not resource_gate:
                    reasons.append("resource_benefit_not_supported")
            strategy_gate = True
            if strategy is StrategyMode.RS:
                r0_action = canonical_action_id(sources, StrategyMode.R0)
                if r0_action in actions:
                    r0_quality_ucb = quality_ucb[r0_action]
                    r0_strategy_omission = risk[r0_action]["strategy_omission"].upper / 3.0
                    strategy_gain = quality_lcb[action] - r0_quality_ucb
                    strategy_gate = (
                        strategy_gain >= self.selection_config.strategy_min_gain
                        or r0_strategy_omission
                        >= self.selection_config.r0_strategy_omission_trigger
                    )
                    if not strategy_gate:
                        reasons.append("strategy_benefit_not_supported")
            normalized_cost = costs[action] / max_cost
            utility = (
                quality_lcb[action]
                - self.selection_config.risk_weight * risk_ucb[action]
                - self.selection_config.cost_weight * normalized_cost
            )
            predictions[action] = ActionPrediction(
                action_id=action,
                response=response[action],
                risk=risk[action],
                quality_mean=quality_mean[action],
                quality_lcb=quality_lcb[action],
                risk_ucb=risk_ucb[action],
                estimated_cost=costs[action],
                normalized_cost=normalized_cost,
                utility=utility,
                feasible=feasible,
                resource_gate_passed=resource_gate,
                strategy_gate_passed=strategy_gate,
                exclusion_reasons=reasons,
            )
        return predictions

    def choose(self, state: PMV2State) -> PolicyDecision:
        ood = self.feature_builder.ood_report(state)
        predictions = self.predict_actions(state)
        fallback = self.selection_config.fallback_action
        if fallback not in predictions:
            fallback = min(predictions, key=lambda action: predictions[action].estimated_cost)
        severe_ood = bool(ood["severe_semantic_ood"] or ood["severe_metadata_ood"])
        if severe_ood and self.selection_config.fail_closed_on_ood:
            chosen = fallback
            reason = "severe OOD; preregistered conservative fallback"
            fallback_used = True
        else:
            candidates = [
                prediction
                for prediction in predictions.values()
                if prediction.feasible
                and prediction.resource_gate_passed
                and prediction.strategy_gate_passed
            ]
            if not candidates:
                chosen = fallback
                reason = "no action passed conservative gates; fallback"
                fallback_used = True
            else:
                selected = max(
                    candidates,
                    key=lambda item: (
                        item.utility,
                        item.quality_lcb,
                        -item.risk_ucb,
                        -item.estimated_cost,
                        item.action_id,
                    ),
                )
                chosen = selected.action_id
                reason = (
                    "max conservative utility after explicit risk, resource-benefit, "
                    "strategy-benefit and cost terms"
                )
                fallback_used = False
        return PolicyDecision(
            state_id=state.state_id,
            chosen_action=chosen,
            predictions=predictions,
            semantic_ood_score=float(ood["semantic_ood_score"]),
            metadata_ood_score=float(ood["metadata_ood_score"]),
            ood_fallback_used=fallback_used,
            decision_reason=reason,
            config_hash=self.selection_config.digest(),
        )


def evaluate_policy(
    model: PMV2Model,
    states: Sequence[PMV2State],
    labels: Sequence[ActionLabel],
) -> dict[str, Any]:
    state_map = {state.state_id: state for state in states}
    label_map = {(label.state_id, label.action_id): label for label in labels}
    rows: list[dict[str, Any]] = []
    for state_id, state in sorted(state_map.items()):
        decision = model.choose(state)
        label = label_map.get((state_id, decision.chosen_action))
        if label is None:
            continue
        quality = model.selection_config.composite_spec.score(label.response)
        risk = max(float(getattr(label.risk, name)) / 3.0 for name in RISK_FIELDS)
        rows.append(
            {
                "state_id": state_id,
                "action_id": decision.chosen_action,
                "quality": quality,
                "risk": risk,
                "cost": label.observed_input_tokens,
                "m0": not bool(parse_action_id(decision.chosen_action)[0]),
                "r0": parse_action_id(decision.chosen_action)[1] is StrategyMode.R0,
                "ood_fallback": decision.ood_fallback_used,
            }
        )
    if not rows:
        raise ValueError("no policy decisions have matching labels")
    actions = [row["action_id"] for row in rows]
    counts = {action: actions.count(action) for action in sorted(set(actions))}
    probabilities = np.asarray(list(counts.values()), dtype=float) / len(rows)
    entropy = float(-np.sum(probabilities * np.log2(probabilities)))
    return {
        "n": len(rows),
        "mean_quality": float(np.mean([row["quality"] for row in rows])),
        "mean_risk": float(np.mean([row["risk"] for row in rows])),
        "mean_cost": float(np.mean([row["cost"] for row in rows])),
        "m0_rate": float(np.mean([row["m0"] for row in rows])),
        "r0_rate": float(np.mean([row["r0"] for row in rows])),
        "ood_fallback_rate": float(np.mean([row["ood_fallback"] for row in rows])),
        "action_entropy_bits": entropy,
        "action_distribution": counts,
        "rows": rows,
    }


def tune_selection_config(
    model: PMV2Model,
    states: Sequence[PMV2State],
    labels: Sequence[ActionLabel],
    *,
    cost_weights: Iterable[float] = (0.05, 0.10, 0.20, 0.30),
    risk_weights: Iterable[float] = (0.15, 0.25, 0.40),
    resource_gains: Iterable[float] = (-0.03, -0.01, 0.0, 0.02),
    strategy_gains: Iterable[float] = (-0.02, 0.0, 0.02),
    max_risks: Iterable[float] = (0.30, 0.40, 0.50),
    minimum_quality: float | None = None,
) -> dict[str, Any]:
    """Tune only on a frozen calibration split.

    The objective directly includes quality, risk and normalized observed cost. It
    never uses an external test set and never optimizes an action-distribution target.
    """

    label_costs = [label.observed_input_tokens for label in labels]
    cost_scale = max(float(np.mean(label_costs)), 1.0)
    original = model.selection_config
    candidates: list[dict[str, Any]] = []
    for cost_weight in cost_weights:
        for risk_weight in risk_weights:
            for resource_gain in resource_gains:
                for strategy_gain in strategy_gains:
                    for max_risk in max_risks:
                        config = original.model_copy(
                            update={
                                "cost_weight": float(cost_weight),
                                "risk_weight": float(risk_weight),
                                "resource_min_gain": float(resource_gain),
                                "strategy_min_gain": float(strategy_gain),
                                "max_risk_ucb": float(max_risk),
                            }
                        )
                        model.selection_config = config
                        metrics = evaluate_policy(model, states, labels)
                        objective = (
                            metrics["mean_quality"]
                            - risk_weight * metrics["mean_risk"]
                            - cost_weight * (metrics["mean_cost"] / cost_scale)
                        )
                        quality_ok = (
                            minimum_quality is None
                            or metrics["mean_quality"] >= minimum_quality
                        )
                        candidates.append(
                            {
                                "config": config.model_dump(mode="json"),
                                "config_hash": config.digest(),
                                "objective": float(objective),
                                "quality_constraint_passed": quality_ok,
                                "metrics": {key: value for key, value in metrics.items() if key != "rows"},
                            }
                        )
    valid = [row for row in candidates if row["quality_constraint_passed"]]
    if not valid:
        model.selection_config = original
        raise RuntimeError("no PM-v2 selection config satisfies calibration constraints")
    best = max(
        valid,
        key=lambda row: (
            row["objective"],
            row["metrics"]["mean_quality"],
            -row["metrics"]["mean_risk"],
            -row["metrics"]["mean_cost"],
        ),
    )
    model.selection_config = SelectionConfig.model_validate(best["config"])
    return {
        "status": "COMPLETE",
        "selected": best,
        "candidate_count": len(candidates),
        "pareto_candidates": sorted(valid, key=lambda row: row["objective"], reverse=True)[:25],
    }


@dataclass
class LearnedPMV2Policy:
    """Compatibility adapter for the existing EvoEmo generation runner."""

    model: PMV2Model
    name: str = "pm_v2"
    strategy_catalog_count: int = 0
    strategy_estimated_tokens: int = 240
    last_decision_report: dict[str, Any] | None = None

    def choose(self, state):
        from .pm_v2_data import runtime_to_pmv2_state

        pm_state = runtime_to_pmv2_state(
            state,
            strategy_catalog_count=self.strategy_catalog_count,
            strategy_estimated_tokens=self.strategy_estimated_tokens,
        )
        decision = self.model.choose(pm_state)
        self.last_decision_report = decision.model_dump(mode="json")
        return decision.chosen_action
