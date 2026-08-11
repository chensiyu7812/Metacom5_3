import pytest

from metacom_pm.v1_5_head_semantic_abstention import (
    HeadAbstentionThresholds,
    HeadRoutingDecision,
    compile_independent_head_decisions,
    decide_head,
)
from metacom_pm.v1_5_v5_3_semantic_off_accounting import SemanticStatus


SHA = "a" * 64


def threshold(component: str) -> HeadAbstentionThresholds:
    return HeadAbstentionThresholds(
        component=component,
        off_max=0.35,
        on_min=0.65,
        calibration_scope="OUTER_TRAIN_ONLY",
        calibration_artifact_sha256=SHA,
    )


def test_uncertain_is_off_for_only_that_head() -> None:
    action, decisions = compile_independent_head_decisions(
        probabilities={"MP": 0.8, "MS": 0.5, "ME": 0.2, "RS": 0.9},
        thresholds={component: threshold(component) for component in ("MP", "MS", "ME", "RS")},
    )
    assert action == "MP+RS"
    assert decisions["MS"].routing_decision is HeadRoutingDecision.UNCERTAIN_AS_OFF
    assert decisions["MS"].semantic_status is SemanticStatus.ABSTAIN_LOW_CONFIDENCE
    assert decisions["MP"].requested_on is True
    assert decisions["RS"].requested_on is True


def test_all_heads_can_remain_on() -> None:
    action, decisions = compile_independent_head_decisions(
        probabilities={component: 0.9 for component in ("MP", "MS", "ME", "RS")},
        thresholds={component: threshold(component) for component in ("MP", "MS", "ME", "RS")},
    )
    assert action == "MPMSME+RS"
    assert all(row.requested_on for row in decisions.values())


def test_thresholds_must_come_from_outer_train() -> None:
    with pytest.raises(ValueError, match="outer-train"):
        HeadAbstentionThresholds(
            component="MS",
            off_max=0.4,
            on_min=0.6,
            calibration_scope="FULL_DATA",
            calibration_artifact_sha256=SHA,
        )


def test_probability_gap_has_three_distinct_results() -> None:
    t = threshold("MS")
    assert decide_head(0.2, t).routing_decision is HeadRoutingDecision.OFF
    assert decide_head(0.5, t).routing_decision is HeadRoutingDecision.UNCERTAIN_AS_OFF
    assert decide_head(0.8, t).routing_decision is HeadRoutingDecision.ON
