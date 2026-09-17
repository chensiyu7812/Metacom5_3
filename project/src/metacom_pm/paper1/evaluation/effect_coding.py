"""Deterministic paired-effect coding over already-computed official outcomes.

This module performs no generation, scorer calls, training, or threshold
selection.  It preserves the five raw outcomes required by the Paper-1
authority: ON better, OFF better, equivalent, uncertain, and invalid.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum
from fractions import Fraction

from pydantic import Field, model_validator

from ..contracts import PairedOutcome, StrictContract, TaskType


class MechanicalInvalidReason(StrEnum):
    """Closed integrity set from the highest-precedence reconciliation."""

    COMPILER_OR_SCHEMA_FAILURE = "compiler_or_schema_failure"
    RESOURCE_NOT_DELIVERED_OR_WRONGLY_BOUND = "assigned_resource_not_delivered_or_wrongly_bound"
    WRONG_OWNER = "wrong_owner"
    FUTURE_LEAKAGE = "future_leakage"
    GOLD_REFERENCE_LEAKAGE = "gold_reference_leakage"
    IDENTITY_MISMATCH = "arm_seed_prompt_candidate_identity_mismatch"
    GENERATION_FAILURE = "empty_or_terminal_generation_failure"
    SCORER_UNPARSEABLE = "official_scorer_unparseable"


class PairedEffectDecision(StrictContract):
    task_type: TaskType
    outcome: PairedOutcome
    reason_code: str
    anchor_deltas: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def invalid_outcomes_use_only_closed_mechanical_reasons(self) -> "PairedEffectDecision":
        prefix = "mechanically_invalid:"
        if self.outcome is not PairedOutcome.INVALID:
            if self.reason_code.startswith(prefix):
                raise ValueError("only invalid outcomes may carry mechanical invalid reasons")
            return self
        if not self.reason_code.startswith(prefix):
            raise ValueError("invalid outcomes require closed mechanical invalid reasons")
        values = self.reason_code.removeprefix(prefix).split(",")
        allowed = {reason.value for reason in MechanicalInvalidReason}
        if not values or any(value not in allowed for value in values):
            raise ValueError("invalid outcome contains a non-mechanical reason")
        return self

    @property
    def enters_training_likelihood(self) -> bool:
        return self.outcome in {
            PairedOutcome.ON_BETTER,
            PairedOutcome.OFF_BETTER,
            PairedOutcome.EQUIVALENT,
        }

    @property
    def binary_target(self) -> float | None:
        if self.outcome is PairedOutcome.ON_BETTER:
            return 1.0
        if self.outcome in {PairedOutcome.OFF_BETTER, PairedOutcome.EQUIVALENT}:
            return 0.0
        return None


class EscEffectSurface(StrictContract):
    """Raw seven-dimension ESC-RANK surface (all ordinal 0--4)."""

    empathy: int = Field(ge=0, le=4)
    information: int = Field(ge=0, le=4)
    expression: int = Field(ge=0, le=4)
    fluency: int = Field(ge=0, le=4)
    skillful: int = Field(ge=0, le=4)
    humanoid: int = Field(ge=0, le=4)
    overall: int = Field(ge=0, le=4)


class QaEffectSurface(StrictContract):
    llm_as_judge: int = Field(ge=0, le=2)
    f1: float = Field(ge=0.0, le=1.0)
    bert_score: float = Field(ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def metrics_are_finite(self) -> "QaEffectSurface":
        if not math.isfinite(self.f1) or not math.isfinite(self.bert_score):
            raise ValueError("QA effect metrics must be finite")
        return self


class SummaryEffectSurface(StrictContract):
    rouge_1: float = Field(ge=0.0, le=1.0)
    rouge_2: float = Field(ge=0.0, le=1.0)
    rouge_l: float = Field(ge=0.0, le=1.0)
    reference_events: int = Field(ge=0)
    generated_events: int = Field(ge=0)
    recalled_events: int = Field(ge=0)
    llm_score: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def recalled_events_are_bounded(self) -> "SummaryEffectSurface":
        if not all(math.isfinite(value) for value in (self.rouge_1, self.rouge_2, self.rouge_l)):
            raise ValueError("Summary ROUGE metrics must be finite")
        if self.recalled_events > self.reference_events:
            raise ValueError("recalled events cannot exceed reference events")
        if self.recalled_events > self.generated_events:
            raise ValueError("recalled events cannot exceed generated events")
        return self

    @property
    def event_precision(self) -> Fraction:
        if self.generated_events == 0:
            return Fraction(0, 1)
        return Fraction(self.recalled_events, self.generated_events)

    @property
    def event_recall(self) -> Fraction:
        if self.reference_events == 0:
            return Fraction(0, 1)
        return Fraction(self.recalled_events, self.reference_events)

    @property
    def event_f1(self) -> Fraction:
        denominator = self.reference_events + self.generated_events
        if denominator == 0:
            return Fraction(0, 1)
        return Fraction(2 * self.recalled_events, denominator)


class DgObservationJudgement(StrictContract):
    observation_id: str = Field(min_length=1, description="Audit identity only")
    turn: int = Field(ge=1, le=10)
    relevance: int = Field(ge=1, le=3)
    used: bool


class DgEffectSurface(StrictContract):
    scored_observation_count: int = Field(ge=0)
    used_observation_count: int = Field(ge=0)
    fully_relevant_total: int = Field(ge=0)
    fully_relevant_used: int = Field(ge=0)
    relevance_weight_total: int = Field(ge=0)
    relevance_weight_used: int = Field(ge=0)
    long_term_memory: int = Field(ge=1, le=5)
    personalization: int = Field(ge=1, le=5)
    emotional_support: int = Field(ge=1, le=5)
    observation_metric_turns: int = Field(default=5)

    @model_validator(mode="after")
    def observation_counts_are_bounded(self) -> "DgEffectSurface":
        if self.observation_metric_turns != 5:
            raise ValueError("official observation aggregation is frozen to turns 1-5")
        if self.fully_relevant_used > self.fully_relevant_total:
            raise ValueError("used fully-relevant observations exceed total")
        if self.used_observation_count > self.scored_observation_count:
            raise ValueError("used observations exceed scored observations")
        if self.fully_relevant_total > self.scored_observation_count:
            raise ValueError("fully-relevant observations exceed scored observations")
        if self.fully_relevant_used > self.used_observation_count:
            raise ValueError("used fully-relevant observations exceed used observations")
        if self.relevance_weight_used > self.relevance_weight_total:
            raise ValueError("used relevance weight exceeds total")
        if not (
            2 * self.fully_relevant_total
            <= self.relevance_weight_total
            <= self.scored_observation_count + self.fully_relevant_total
        ):
            raise ValueError("total relevance weight is inconsistent with observation counts")
        if not (
            2 * self.fully_relevant_used
            <= self.relevance_weight_used
            <= self.used_observation_count + self.fully_relevant_used
        ):
            raise ValueError("used relevance weight is inconsistent with observation counts")
        partial_total = self.relevance_weight_total - 2 * self.fully_relevant_total
        partial_used = self.relevance_weight_used - 2 * self.fully_relevant_used
        if not 0 <= partial_used <= partial_total:
            raise ValueError("used partially-relevant observations are not a subset of total")
        irrelevant_total = (
            self.scored_observation_count - self.fully_relevant_total - partial_total
        )
        irrelevant_used = (
            self.used_observation_count - self.fully_relevant_used - partial_used
        )
        if not 0 <= irrelevant_used <= irrelevant_total:
            raise ValueError("used irrelevant observations are not a subset of total")
        return self

    @property
    def observation_recall(self) -> Fraction:
        if self.fully_relevant_total == 0:
            return Fraction(0, 1)
        return Fraction(self.fully_relevant_used, self.fully_relevant_total)

    @property
    def weighted_score(self) -> Fraction:
        if self.relevance_weight_total == 0:
            return Fraction(0, 1)
        return Fraction(self.relevance_weight_used, self.relevance_weight_total)


def build_dg_effect_surface(
    observations: Sequence[DgObservationJudgement],
    *,
    expected_observation_ids: Sequence[str],
    long_term_memory: int,
    personalization: int,
    emotional_support: int,
) -> DgEffectSurface:
    """Reproduce the official first-five-turn observation aggregation."""

    if len(expected_observation_ids) != len(set(expected_observation_ids)):
        raise ValueError("expected observation ids must be unique")
    identities = [(item.turn, item.observation_id) for item in observations]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate dialogue-generation observation judgement")

    scored = [item for item in observations if item.turn <= 5]
    expected_scored = {
        (turn, observation_id)
        for turn in range(1, 6)
        for observation_id in expected_observation_ids
    }
    observed_scored = {(item.turn, item.observation_id) for item in scored}
    if observed_scored != expected_scored:
        missing = sorted(expected_scored - observed_scored)
        extra = sorted(observed_scored - expected_scored)
        raise ValueError(f"incomplete DG observation grid: missing={missing}, extra={extra}")
    fully_relevant = [item for item in scored if item.relevance == 3]
    relevance_weights = [item.relevance - 1 for item in scored]
    used_weights = [
        item.relevance - 1 for item in scored if item.used
    ]
    return DgEffectSurface(
        scored_observation_count=len(scored),
        used_observation_count=sum(item.used for item in scored),
        fully_relevant_total=len(fully_relevant),
        fully_relevant_used=sum(item.used for item in fully_relevant),
        relevance_weight_total=sum(relevance_weights),
        relevance_weight_used=sum(used_weights),
        long_term_memory=long_term_memory,
        personalization=personalization,
        emotional_support=emotional_support,
    )


def _sign(value: int | float | Fraction) -> int:
    return (value > 0) - (value < 0)


def _invalid(
    task_type: TaskType,
    invalid_reasons: Sequence[MechanicalInvalidReason],
) -> PairedEffectDecision:
    if not invalid_reasons or any(
        not isinstance(reason, MechanicalInvalidReason) for reason in invalid_reasons
    ):
        raise ValueError("invalid reasons must come from the closed mechanical integrity enum")
    return PairedEffectDecision(
        task_type=task_type,
        outcome=PairedOutcome.INVALID,
        reason_code="mechanically_invalid:"
        + ",".join(sorted({reason.value for reason in invalid_reasons})),
    )


def _directed(
    task_type: TaskType,
    direction: int,
    reason_code: str,
    anchor_deltas: dict[str, float],
) -> PairedEffectDecision:
    if direction not in {-1, 1}:
        raise ValueError("directed paired effect requires a nonzero direction")
    return PairedEffectDecision(
        task_type=task_type,
        outcome=(
            PairedOutcome.ON_BETTER if direction > 0 else PairedOutcome.OFF_BETTER
        ),
        reason_code=reason_code,
        anchor_deltas=anchor_deltas,
    )


def _pairwise_direction(verdict: PairedOutcome | None) -> int | None:
    if verdict is None or verdict is PairedOutcome.UNCERTAIN:
        return None
    if verdict is PairedOutcome.INVALID:
        raise ValueError("an invalid pairwise verdict requires a mechanical invalid reason")
    if verdict is PairedOutcome.ON_BETTER:
        return 1
    if verdict is PairedOutcome.OFF_BETTER:
        return -1
    return 0


def _uncertain(
    task_type: TaskType,
    reason_code: str,
    deltas: dict[str, float],
) -> PairedEffectDecision:
    return PairedEffectDecision(
        task_type=task_type,
        outcome=PairedOutcome.UNCERTAIN,
        reason_code=reason_code,
        anchor_deltas=deltas,
    )


def _equivalent(
    task_type: TaskType,
    reason_code: str,
    deltas: dict[str, float],
) -> PairedEffectDecision:
    return PairedEffectDecision(
        task_type=task_type,
        outcome=PairedOutcome.EQUIVALENT,
        reason_code=reason_code,
        anchor_deltas=deltas,
    )


def code_esc_pairwise_effect(
    on: EscEffectSurface,
    off: EscEffectSurface,
    *,
    pairwise_verdict: PairedOutcome | None,
    invalid_reasons: Sequence[MechanicalInvalidReason] = (),
) -> PairedEffectDecision:
    """Use Overall as the discrete primary and retain all other dimensions.

    Empathy and Information remain reported diagnostics.  A one-step change in
    either is not, by itself, a material-harm veto.  When a qualified pairwise
    judgement is supplied, an explicit equivalent verdict means that the
    realized pair has no discernible material advantage.
    """

    if invalid_reasons:
        return _invalid(TaskType.ESC_RESPONSE, invalid_reasons)
    pairwise = _pairwise_direction(pairwise_verdict)
    deltas = {
        "Overall": float(on.overall - off.overall),
        "Empathy": float(on.empathy - off.empathy),
        "Information": float(on.information - off.information),
        "Expression": float(on.expression - off.expression),
        "Fluency": float(on.fluency - off.fluency),
        "Skillful": float(on.skillful - off.skillful),
        "Humanoid": float(on.humanoid - off.humanoid),
    }
    primary = _sign(deltas["Overall"])
    if primary:
        if pairwise == 0:
            return _equivalent(
                TaskType.ESC_RESPONSE,
                "esc_pairwise_material_equivalence_overrides_ordinal_direction",
                deltas,
            )
        if pairwise is not None and pairwise != primary:
            return _uncertain(TaskType.ESC_RESPONSE, "esc_primary_pairwise_conflict", deltas)
        return _directed(
            TaskType.ESC_RESPONSE,
            primary,
            "esc_overall_ordinal_material_direction",
            deltas,
        )
    if pairwise is None:
        return _uncertain(TaskType.ESC_RESPONSE, "esc_overall_tie_pairwise_unresolved", deltas)
    if pairwise == 0:
        return _equivalent(TaskType.ESC_RESPONSE, "esc_pairwise_equivalent", deltas)
    return _directed(
        TaskType.ESC_RESPONSE,
        pairwise,
        "esc_tied_overall_resolved_by_pairwise_teacher",
        deltas,
    )


def code_qa_effect(
    on: QaEffectSurface,
    off: QaEffectSurface,
    *,
    pairwise_verdict: PairedOutcome | None,
    invalid_reasons: Sequence[MechanicalInvalidReason] = (),
) -> PairedEffectDecision:
    if invalid_reasons:
        return _invalid(TaskType.QA, invalid_reasons)

    deltas = {
        "LLM_as_Judge": float(on.llm_as_judge - off.llm_as_judge),
        "F1": on.f1 - off.f1,
        "BERTScore": on.bert_score - off.bert_score,
    }
    primary = _sign(deltas["LLM_as_Judge"])
    pairwise = _pairwise_direction(pairwise_verdict)
    if primary:
        if pairwise == 0:
            return _equivalent(
                TaskType.QA,
                "qa_pairwise_material_equivalence_overrides_ordinal_direction",
                deltas,
            )
        if pairwise is not None and pairwise != primary:
            return _uncertain(TaskType.QA, "qa_primary_pairwise_conflict", deltas)
        return _directed(
            TaskType.QA,
            primary,
            "qa_semantic_correctness_primary_direction",
            deltas,
        )
    if pairwise is None:
        return _uncertain(TaskType.QA, "qa_primary_tie_pairwise_unresolved", deltas)
    if pairwise == 0:
        return _equivalent(TaskType.QA, "qa_pairwise_equivalent", deltas)
    return _directed(
        TaskType.QA,
        pairwise,
        "qa_primary_tie_resolved_by_gold_pairwise_teacher",
        deltas,
    )


def code_summary_effect(
    on: SummaryEffectSurface,
    off: SummaryEffectSurface,
    *,
    pairwise_verdict: PairedOutcome | None,
    invalid_reasons: Sequence[MechanicalInvalidReason] = (),
) -> PairedEffectDecision:
    if invalid_reasons:
        return _invalid(TaskType.SUMMARY, invalid_reasons)

    deltas = {
        "ROUGE_1": on.rouge_1 - off.rouge_1,
        "ROUGE_2": on.rouge_2 - off.rouge_2,
        "ROUGE_L": on.rouge_l - off.rouge_l,
        "Event_Precision": float(on.event_precision - off.event_precision),
        "Event_Recall": float(on.event_recall - off.event_recall),
        "Event_F1": float(on.event_f1 - off.event_f1),
        "LLM_Score": float(on.llm_score - off.llm_score),
    }
    if on.reference_events != off.reference_events:
        return PairedEffectDecision(
            task_type=TaskType.SUMMARY,
            outcome=PairedOutcome.UNCERTAIN,
            reason_code="summary_reference_event_extraction_disagrees",
            anchor_deltas=deltas,
        )

    primary = _sign(on.event_f1 - off.event_f1)
    llm = _sign(deltas["LLM_Score"])
    pairwise = _pairwise_direction(pairwise_verdict)
    # V2: qualified material equivalence takes precedence over mere metric
    # directions, including an Event-F1 tie with a non-tied LLM Score. Keep the
    # raw deltas and the earlier integrity/reference-inventory checks intact.
    if pairwise == 0:
        return _equivalent(
            TaskType.SUMMARY,
            "summary_pairwise_material_equivalence" if primary else "summary_semantic_equivalent",
            deltas,
        )
    if primary:
        if llm == -primary or pairwise == -primary:
            return _uncertain(TaskType.SUMMARY, "summary_event_semantic_conflict", deltas)
        if pairwise is None:
            return _uncertain(
                TaskType.SUMMARY,
                "summary_continuous_primary_materiality_unresolved",
                deltas,
            )
        return _directed(
            TaskType.SUMMARY,
            primary,
            "summary_event_f1_primary_direction",
            deltas,
        )
    if llm and pairwise == llm:
        return _directed(
            TaskType.SUMMARY,
            llm,
            "summary_event_f1_tie_llm_pairwise_agreement",
            deltas,
        )
    return _uncertain(TaskType.SUMMARY, "summary_event_f1_tie_semantic_unresolved", deltas)


def code_dg_effect(
    on: DgEffectSurface,
    off: DgEffectSurface,
    *,
    pairwise_verdict: PairedOutcome | None,
    invalid_reasons: Sequence[MechanicalInvalidReason] = (),
) -> PairedEffectDecision:
    if invalid_reasons:
        return _invalid(TaskType.DIALOGUE_GENERATION, invalid_reasons)

    deltas = {
        "Observation_Recall": float(on.observation_recall - off.observation_recall),
        "Weighted_Score": float(on.weighted_score - off.weighted_score),
        "LT_Memory": float(on.long_term_memory - off.long_term_memory),
        "Personalization": float(on.personalization - off.personalization),
        "Emotional_Support": float(on.emotional_support - off.emotional_support),
    }
    primary = _sign(on.weighted_score - off.weighted_score)
    pairwise = _pairwise_direction(pairwise_verdict)
    if primary:
        if pairwise is None:
            return _uncertain(
                TaskType.DIALOGUE_GENERATION,
                "dg_pairwise_guard_unresolved",
                deltas,
            )
        if pairwise == 0:
            return _equivalent(
                TaskType.DIALOGUE_GENERATION,
                "dg_pairwise_material_equivalence",
                deltas,
            )
        if pairwise == -primary:
            return _uncertain(
                TaskType.DIALOGUE_GENERATION,
                "dg_utilization_pairwise_conflict",
                deltas,
            )
        return _directed(
            TaskType.DIALOGUE_GENERATION,
            primary,
            "dg_relevant_observation_utilization_direction",
            deltas,
        )
    if pairwise is None:
        return _uncertain(
            TaskType.DIALOGUE_GENERATION,
            "dg_utilization_tie_pairwise_unresolved",
            deltas,
        )
    if pairwise == 0:
        return _equivalent(
            TaskType.DIALOGUE_GENERATION,
            "dg_utilization_and_pairwise_equivalent",
            deltas,
        )
    return _directed(
        TaskType.DIALOGUE_GENERATION,
        pairwise,
        "dg_utilization_tie_resolved_by_pairwise_teacher",
        deltas,
    )


__all__ = [
    "DgEffectSurface",
    "DgObservationJudgement",
    "EscEffectSurface",
    "MechanicalInvalidReason",
    "PairedEffectDecision",
    "QaEffectSurface",
    "SummaryEffectSurface",
    "build_dg_effect_surface",
    "code_dg_effect",
    "code_esc_pairwise_effect",
    "code_qa_effect",
    "code_summary_effect",
]
