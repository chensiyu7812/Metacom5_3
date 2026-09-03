"""Fail-closed adapters for prior-work official metric surfaces.

This module validates already-produced scorer output.  It does not invoke a
scorer and therefore remains safe while the pre-outcome lock is active.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from ..contracts import ExperimentArm, OfficialOutcomeRecord, TaskType

_ESC_METRICS = (
    "Fluency",
    "Expression",
    "Empathy",
    "Information",
    "Skillful",
    "Humanoid",
    "Overall",
)
_MEMORY_METRICS: dict[TaskType, tuple[str, ...]] = {
    TaskType.QA: ("F1", "BERTScore", "LLM_as_Judge", "Recall_at_k", "nDCG_at_k"),
    TaskType.SUMMARY: (
        "ROUGE_1",
        "ROUGE_2",
        "ROUGE_L",
        "Event_Precision",
        "Event_Recall",
        "Event_F1",
        "LLM_Score",
    ),
    TaskType.DIALOGUE_GENERATION: (
        "Observation_Recall",
        "Weighted_Score",
        "LT_Memory",
        "Personalization",
        "Emotional_Support",
    ),
}


def official_metric_names(*, benchmark: str, task_type: TaskType) -> tuple[str, ...]:
    if benchmark == "ESC-Eval" and task_type is TaskType.ESC_RESPONSE:
        return _ESC_METRICS
    if benchmark == "ES-MemEval" and task_type in _MEMORY_METRICS:
        return _MEMORY_METRICS[task_type]
    raise ValueError(f"unsupported official benchmark/task pair: {benchmark}/{task_type.value}")


def build_official_outcome(
    *,
    benchmark: str,
    task_type: TaskType,
    target_id: str,
    arm: ExperimentArm,
    metrics: Mapping[str, float],
    official_scorer_id: str,
    diagnostic_only_metrics: Mapping[str, float] | None = None,
) -> OfficialOutcomeRecord:
    expected = official_metric_names(benchmark=benchmark, task_type=task_type)
    received = tuple(metrics)
    missing = sorted(set(expected) - set(received))
    extra = sorted(set(received) - set(expected))
    if missing or extra:
        raise ValueError(f"official metric surface mismatch: missing={missing}, extra={extra}")

    numeric = {name: float(metrics[name]) for name in expected}
    if not all(math.isfinite(value) for value in numeric.values()):
        raise ValueError("official metrics must be finite")

    return OfficialOutcomeRecord(
        benchmark=benchmark,
        task_type=task_type,
        target_id=target_id,
        arm=arm,
        metrics=numeric,
        official_scorer_id=official_scorer_id,
        diagnostic_only_metrics=dict(diagnostic_only_metrics or {}),
    )


def normalized_official_primary_quality(
    outcome: OfficialOutcomeRecord,
) -> tuple[str, float]:
    """Return the frozen task-specific primary anchor on a unit scale.

    Positive affine normalization does not change a within-task best/one-SE
    choice, but makes the threshold contract explicit and range-checkable.
    It does not create a cross-task composite.
    """

    if outcome.benchmark == "ESC-Eval" and outcome.task_type is TaskType.ESC_RESPONSE:
        metric_id, value = "ESC-RANK:Overall/4", outcome.metrics["Overall"] / 4.0
    elif outcome.benchmark == "ES-MemEval" and outcome.task_type is TaskType.QA:
        metric_id, value = (
            "ES-MemEval:LLM_as_Judge/2",
            outcome.metrics["LLM_as_Judge"] / 2.0,
        )
    elif outcome.benchmark == "ES-MemEval" and outcome.task_type is TaskType.SUMMARY:
        metric_id, value = "ES-MemEval:Event_F1", outcome.metrics["Event_F1"]
    elif (
        outcome.benchmark == "ES-MemEval"
        and outcome.task_type is TaskType.DIALOGUE_GENERATION
    ):
        metric_id, value = (
            "ES-MemEval:Weighted_Score",
            outcome.metrics["Weighted_Score"],
        )
    else:
        raise ValueError("unsupported official outcome for primary-quality normalization")
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"official primary quality is outside its frozen scale: {metric_id}={value}"
        )
    return metric_id, value
