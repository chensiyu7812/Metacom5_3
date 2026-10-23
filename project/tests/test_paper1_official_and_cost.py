import pytest

from metacom_pm.paper1.contracts import ExperimentArm, TaskType
from metacom_pm.paper1.evaluation.cost import TokenPricing, build_cost_record
from metacom_pm.paper1.evaluation.official import (
    build_official_outcome,
    normalized_official_primary_quality,
)


def test_cost_keeps_resource_tokens_as_a_non_additive_input_subset():
    cost = build_cost_record(
        generator_input_tokens=100,
        resource_injected_tokens=20,
        output_tokens=30,
        latency_ms=25.0,
        pricing=TokenPricing(input_usd_per_million=2.0, output_usd_per_million=4.0),
    )
    assert cost.total_tokens == 130
    assert cost.recoverable_api_cost_usd == pytest.approx(0.00032)
    with pytest.raises(ValueError):
        build_cost_record(
            generator_input_tokens=10,
            resource_injected_tokens=11,
            output_tokens=1,
            latency_ms=1.0,
        )


def test_esc_adapter_requires_the_complete_official_seven_dimensions():
    values = {
        "Fluency": 1,
        "Expression": 2,
        "Empathy": 3,
        "Information": 4,
        "Skillful": 5,
        "Humanoid": 6,
        "Overall": 7,
    }
    outcome = build_official_outcome(
        benchmark="ESC-Eval",
        task_type=TaskType.ESC_RESPONSE,
        target_id="card-1",
        arm=ExperimentArm.R0,
        metrics=values,
        official_scorer_id="esc-rank@frozen",
        diagnostic_only_metrics={"internal_pairwise_agreement": 0.9},
    )
    assert tuple(outcome.metrics) == tuple(values)
    assert "internal_pairwise_agreement" not in outcome.metrics


def test_official_adapter_rejects_partial_or_invented_metric_surfaces():
    with pytest.raises(ValueError, match="missing"):
        build_official_outcome(
            benchmark="ES-MemEval",
            task_type=TaskType.DIALOGUE_GENERATION,
            target_id="topic-1",
            arm=ExperimentArm.NO_MEMORY,
            metrics={"Weighted_Score": 1.0},
            official_scorer_id="es-memeval@frozen",
        )

    complete = {
        "Observation_Recall": 1,
        "Weighted_Score": 2,
        "LT_Memory": 3,
        "Personalization": 4,
        "Emotional_Support": 5,
        "quality": 6,
    }
    with pytest.raises(ValueError, match="extra"):
        build_official_outcome(
            benchmark="ES-MemEval",
            task_type=TaskType.DIALOGUE_GENERATION,
            target_id="topic-1",
            arm=ExperimentArm.NO_MEMORY,
            metrics=complete,
            official_scorer_id="es-memeval@frozen",
        )


def test_threshold_primary_quality_uses_the_task_specific_official_anchor():
    outcome = build_official_outcome(
        benchmark="ES-MemEval",
        task_type=TaskType.QA,
        target_id="qa-1",
        arm=ExperimentArm.NO_MEMORY,
        metrics={
            "F1": 0.1,
            "BERTScore": 0.9,
            "LLM_as_Judge": 1,
            "Recall_at_k": 0.2,
            "nDCG_at_k": 0.3,
        },
        official_scorer_id="es-memeval@frozen",
    )
    assert normalized_official_primary_quality(outcome) == (
        "ES-MemEval:LLM_as_Judge/2",
        0.5,
    )
