from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import MemorySource, StrategyMode, canonical_action_id
from .io import canonical_json, sha256_text
from .pm_v2_contracts import ActionPrediction, PMV2State, PolicyDecision
from .pm_v2_features import PMV2FeatureBuilder
from .pm_v2_model import (
    LEARNED_SELECTION_REASON,
    SelectionConfig,
    evaluate_policy,
    estimated_action_cost_profile,
)


RULE_ROUTER_PROTOCOL = "pm-v1.5-transparent-step0-rule-router-v2"


@dataclass
class FixedActionBaselineRouter:
    """Step-0-free baseline used only by the no-Step-0 residual ablation."""

    action_id: str = "M0+R0"

    def choose_action(self, state: PMV2State) -> str:
        if self.action_id not in state.allowed_actions:
            raise RuntimeError(
                f"fixed residual baseline {self.action_id} is illegal for {state.state_id}"
            )
        return self.action_id


class TransparentRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    protocol: str = RULE_ROUTER_PROTOCOL
    source_similarity_weight: float = Field(ge=0.0)
    source_age_penalty: float = Field(ge=0.0)
    source_cost_penalty: float = Field(ge=0.0)
    source_minimum_score: float
    maximum_memory_sources: int = Field(ge=0, le=3)
    strategy_family_similarity_weight: float = Field(ge=0.0)
    strategy_readiness_alignment_weight: float = Field(ge=0.0)
    question_bonus: float = Field(ge=0.0)
    strategy_cost_penalty: float = Field(ge=0.0)
    strategy_minimum_score: float

    @model_validator(mode="after")
    def valid_protocol(self):
        if self.protocol != RULE_ROUTER_PROTOCOL:
            raise ValueError("unsupported transparent rule-router protocol")
        return self

    def digest(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


@dataclass
class TransparentRuleRouter:
    """Low-capacity, auditable router using exactly the formal Step-0 scalars."""

    config: TransparentRuleConfig
    selection_config: SelectionConfig
    feature_builder: PMV2FeatureBuilder
    format_version: str = RULE_ROUTER_PROTOCOL

    @classmethod
    def create(
        cls,
        config: TransparentRuleConfig,
        selection_config: SelectionConfig,
    ) -> "TransparentRuleRouter":
        return cls(
            config=config,
            selection_config=selection_config,
            feature_builder=PMV2FeatureBuilder(
                word_features=8,
                char_features=8,
                use_precomputed_embeddings=False,
            ),
        )

    def _memory_scores(self, state: PMV2State) -> dict[MemorySource, float]:
        if state.step0_observation is None:
            raise RuntimeError("transparent rule router requires formal Step-0")
        observations = state.step0_observation.memory_sources
        token_scale = max(
            max(row.expected_retrieval_tokens for row in observations.values()),
            1,
        )
        scores: dict[MemorySource, float] = {}
        for source in MemorySource:
            row = observations[source]
            if not row.available or not row.representation_valid:
                scores[source] = float("-inf")
                continue
            age_ratio = min(
                float(row.median_age_sessions or 0.0) / max(state.session_index, 1),
                1.0,
            )
            cost_ratio = row.expected_retrieval_tokens / token_scale
            scores[source] = (
                self.config.source_similarity_weight
                * row.query_to_source_similarity
                - self.config.source_age_penalty * age_ratio
                - self.config.source_cost_penalty * cost_ratio
            )
        return scores

    def choose_action(self, state: PMV2State) -> str:
        if state.step0_observation is None:
            raise RuntimeError("transparent rule router requires formal Step-0")
        source_scores = self._memory_scores(state)
        ranked_sources = sorted(
            (
                (score, source)
                for source, score in source_scores.items()
                if score >= self.config.source_minimum_score
            ),
            key=lambda item: (item[0], item[1].value),
            reverse=True,
        )
        sources = {
            source
            for _, source in ranked_sources[: self.config.maximum_memory_sources]
        }

        strategy = state.step0_observation.strategy
        family = strategy.family_similarities
        readiness = strategy.advice_readiness_similarities
        stage_fits = {
            "listen_only": (
                max(
                    family["reflection"],
                    family["restatement"],
                    family["affirmation_reassurance"],
                ),
                readiness["listen_only"],
            ),
            "explore_first": (
                max(family["question"], family["reflection"], family["restatement"]),
                readiness["explore_first"],
            ),
            "light_suggestion": (
                max(family["suggestion"], family["information"], family["question"]),
                readiness["light_suggestion"],
            ),
            "structured_plan": (
                max(family["suggestion"], family["information"]),
                readiness["structured_plan"],
            ),
            "ambiguous": (
                max(family.values(), default=0.0),
                readiness["ambiguous"],
            ),
        }
        maximum_stage_fit = max(
            self.config.strategy_family_similarity_weight * family_score
            + self.config.strategy_readiness_alignment_weight * readiness_score
            for family_score, readiness_score in stage_fits.values()
        )
        strategy_cost_ratio = min(
            strategy.expected_retrieval_tokens / 768.0,
            1.0,
        )
        strategy_score = (
            maximum_stage_fit
            + self.config.question_bonus * float(strategy.question_present)
            - self.config.strategy_cost_penalty * strategy_cost_ratio
        )
        strategy_mode = (
            StrategyMode.RS
            if strategy.available
            and strategy_score >= self.config.strategy_minimum_score
            else StrategyMode.R0
        )
        action_id = canonical_action_id(sources, strategy_mode)
        if action_id not in state.allowed_actions:
            raise RuntimeError(
                f"transparent rule produced illegal action {action_id} for {state.state_id}"
            )
        return action_id

    def choose(self, state: PMV2State) -> PolicyDecision:
        chosen = self.choose_action(state)
        profile = estimated_action_cost_profile(self.feature_builder, state)
        predictions = {
            action_id: ActionPrediction(
                action_id=action_id,
                response={},
                risk={},
                quality_mean=0.0,
                quality_lcb=0.0,
                risk_ucb=0.0,
                estimated_cost=float(row["estimated_resource_cost"]),
                normalized_cost=float(row["normalized_estimated_resource_cost"]),
                utility=-self.selection_config.cost_weight
                * float(row["normalized_estimated_resource_cost"]),
                feasible=True,
                resource_gate_passed=True,
                strategy_gate_passed=True,
            )
            for action_id, row in profile.items()
        }
        return PolicyDecision(
            state_id=state.state_id,
            chosen_action=chosen,
            predictions=predictions,
            semantic_ood_score=0.0,
            metadata_ood_score=0.0,
            ood_fallback_used=False,
            decision_reason=LEARNED_SELECTION_REASON,
            config_hash=self.config.digest(),
        )


def transparent_rule_candidates(
    grid: Mapping[str, Sequence[float | int]],
) -> list[TransparentRuleConfig]:
    required = (
        "source_similarity_weights",
        "source_age_penalties",
        "source_cost_penalties",
        "source_minimum_scores",
        "maximum_memory_sources",
        "strategy_family_similarity_weights",
        "strategy_readiness_alignment_weights",
        "question_bonuses",
        "strategy_cost_penalties",
        "strategy_minimum_scores",
    )
    if set(grid) != set(required):
        raise ValueError("transparent rule grid keys do not match the frozen contract")
    values = [list(grid[key]) for key in required]
    if any(not rows for rows in values):
        raise ValueError("transparent rule grid dimensions cannot be empty")
    return [
        TransparentRuleConfig(
            source_similarity_weight=float(row[0]),
            source_age_penalty=float(row[1]),
            source_cost_penalty=float(row[2]),
            source_minimum_score=float(row[3]),
            maximum_memory_sources=int(row[4]),
            strategy_family_similarity_weight=float(row[5]),
            strategy_readiness_alignment_weight=float(row[6]),
            question_bonus=float(row[7]),
            strategy_cost_penalty=float(row[8]),
            strategy_minimum_score=float(row[9]),
        )
        for row in product(*values)
    ]


def tune_transparent_rule_router(
    *,
    states: Sequence[PMV2State],
    labels,
    selection_config: SelectionConfig,
    candidates: Sequence[TransparentRuleConfig],
    minimum_quality: float,
    maximum_risk: float,
) -> tuple[TransparentRuleRouter, dict[str, Any]]:
    """Select rule numbers on calibration only with one frozen utility ruler."""

    rows: list[dict[str, Any]] = []
    for config in candidates:
        router = TransparentRuleRouter.create(config, selection_config)
        metrics = evaluate_policy(router, states, labels)
        eligible = (
            metrics["mean_quality"] >= minimum_quality
            and metrics["mean_risk"] <= maximum_risk
        )
        rows.append(
            {
                "config": config.model_dump(mode="json"),
                "config_sha256": config.digest(),
                "eligible": eligible,
                "mean_quality": metrics["mean_quality"],
                "mean_risk": metrics["mean_risk"],
                "mean_realized_utility": metrics["mean_realized_utility"],
                "mean_observed_input_tokens": metrics["mean_observed_input_tokens"],
                "action_distribution": metrics["action_distribution"],
            }
        )
    eligible_rows = [row for row in rows if row["eligible"]]
    if not eligible_rows:
        raise RuntimeError("no transparent rule candidate satisfies calibration guards")
    selected = max(
        eligible_rows,
        key=lambda row: (
            row["mean_realized_utility"],
            row["mean_quality"],
            -row["mean_risk"],
            -row["mean_observed_input_tokens"],
            row["config_sha256"],
        ),
    )
    selected_config = TransparentRuleConfig.model_validate(selected["config"])
    report = {
        "protocol": RULE_ROUTER_PROTOCOL,
        "selection_split": "calibration",
        "candidate_count": len(rows),
        "minimum_quality": float(minimum_quality),
        "maximum_risk": float(maximum_risk),
        "selected_config": selected_config.model_dump(mode="json"),
        "selected_config_sha256": selected_config.digest(),
        "candidates": rows,
    }
    return TransparentRuleRouter.create(selected_config, selection_config), report
