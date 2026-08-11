import pytest

from metacom_pm.v1_5_v5_3_semantic_off_accounting import (
    ComponentDecisionTrace,
    OffReason,
    SemanticStatus,
    ValueStatus,
    action_id,
    summarize_decision_traces,
)


def trace(component: str, **overrides):
    values = {
        "state_id": "s1",
        "component": component,
        "candidate_present": True,
        "structurally_valid": True,
        "safety_hard_off": False,
        "semantic_status": SemanticStatus.OPEN_ELIGIBLE,
        "head_qualified": True,
        "value_status": ValueStatus.ON,
        "projected_on": True,
        "requested_on": True,
    }
    values.update(overrides)
    return ComponentDecisionTrace(**values)


def test_off_reasons_are_not_collapsed():
    assert trace(
        "MP", candidate_present=False, structurally_valid=False,
        semantic_status=SemanticStatus.NOT_REACHED, head_qualified=False,
        value_status=ValueStatus.NOT_REACHED, projected_on=False, requested_on=False,
    ).off_reason is OffReason.CANDIDATE_ABSENT
    assert trace(
        "MS", semantic_status=SemanticStatus.ABSTAIN_LOW_CONFIDENCE,
        value_status=ValueStatus.NOT_REACHED, projected_on=False, requested_on=False,
    ).off_reason is OffReason.SEMANTIC_ABSTAIN_LOW_CONFIDENCE
    assert trace(
        "ME", head_qualified=False, value_status=ValueStatus.NOT_REACHED,
        projected_on=False, requested_on=False,
    ).off_reason is OffReason.HEAD_NOT_QUALIFIED
    assert trace(
        "RS", value_status=ValueStatus.EITHER,
        projected_on=False, requested_on=False,
    ).off_reason is OffReason.JOINT_PROJECTION_COST_FRONTIER_OFF


def test_on_cannot_bypass_preceding_gates():
    with pytest.raises(ValueError):
        trace("MP", head_qualified=False)
    with pytest.raises(ValueError):
        trace("MP", projected_on=False)


def test_action_space_and_componentwise_abstention():
    assert action_id([]) == "M0+R0"
    assert action_id(["RS"]) == "M0+RS"
    assert action_id(["MP", "ME", "RS"]) == "MPE+RS"
    assert len({action_id(c for i, c in enumerate(("MP", "MS", "ME", "RS")) if mask & (1 << i)) for mask in range(16)}) == 16


def test_summary_reports_conditional_and_unconditional_rates():
    rows = [
        trace("MP", candidate_present=False, structurally_valid=False,
              semantic_status=SemanticStatus.NOT_REACHED, head_qualified=False,
              value_status=ValueStatus.NOT_REACHED, projected_on=False, requested_on=False),
        trace("MS", semantic_status=SemanticStatus.ABSTAIN_OUT_OF_SUPPORT,
              value_status=ValueStatus.NOT_REACHED, projected_on=False, requested_on=False),
        trace("ME", head_qualified=False, value_status=ValueStatus.NOT_REACHED,
              projected_on=False, requested_on=False),
        trace("RS"),
    ]
    report = summarize_decision_traces(rows)
    assert report["action_counts"] == {"M0+RS": 1}
    assert report["always_off_alias_rate"] == 0.0
    assert report["components"]["MP"]["structural_off_rate"] == 1.0
    assert report["components"]["RS"]["conditional_on_rate"] == 1.0
