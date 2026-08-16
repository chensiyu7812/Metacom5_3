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
