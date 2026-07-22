from __future__ import annotations

import pytest

from metacom_pm.contracts import DialogueTurn, MemorySource
from metacom_pm.pm_v2_contracts import (
    ActionLabel,
    ObservableSourceSummary,
    PMV2Split,
    PMV2State,
    ResponseDimensions,
    RiskDimensions,
)
from metacom_pm.v1_5_dual_domain_training import (
    ESCONV_AUXILIARY_DOMAIN,
    LONGITUDINAL_DOMAIN,
    training_domain_for_state,
    validate_dual_domain_training_inputs,
)


def _state(
    state_id: str,
    *,
    user_id: str,
    split: PMV2Split,
    auxiliary: bool,
) -> PMV2State:
    inventory = {
        source: ObservableSourceSummary(
            available=False,
            count=0,
            estimated_tokens=0,
        )
        for source in MemorySource
    }
    return PMV2State(
        state_id=state_id,
        card_id=f"card_{state_id}",
        user_id=user_id,
        split=split,
        semantic_family=(
            "esconv_auxiliary_strategy_routing" if auxiliary else "context_only"
        ),
        surface_form_id=f"surface_{state_id}",
        current_user_text="I am having a difficult day.",
        current_session_history=[
            DialogueTurn(role="user", content="I feel tense."),
            DialogueTurn(role="assistant", content="I am listening."),
        ],
        current_session_summary="The user describes current stress.",
        session_index=1,
        inventory=inventory,
        strategy_catalog_count=10,
        strategy_estimated_tokens=120,
        allowed_actions=["M0+R0", "M0+RS"],
        provenance=(
            {"adapted_from_runtime_state": True} if auxiliary else {}
        ),
    )


def _label(state: PMV2State, action_id: str, *, auxiliary: bool) -> ActionLabel:
    response = ResponseDimensions(
        emotional_support=3,
        personalization=3,
        memory_appropriateness=3,
        factual_grounding=3,
        temporal_consistency=3,
        non_intrusiveness=3,
    )
    risk = RiskDimensions(
        selected_context_misuse=0,
        unnecessary_exposure=0,
        stale_or_conflicting_use=0,
        unsupported_personal_claim=0,
        memory_omission=0,
        strategy_overuse=0,
        strategy_omission=0,
    )
    dimensions = {
        **{f"response.{name}": 0.0 for name in ResponseDimensions.model_fields},
        **{f"risk.{name}": 0.0 for name in RiskDimensions.model_fields},
    }
    return ActionLabel(
        state_id=state.state_id,
        card_id=state.card_id,
        user_id=state.user_id,
        semantic_family=state.semantic_family,
        action_id=action_id,
        response=response,
        risk=risk,
        observed_input_tokens=100,
        retrieval_calls=0,
        judge_families=["judge_a", "judge_b"],
        judge_count=2,
        max_dimension_mad=0.0,
        dimension_mad=dimensions,
        label_reliable=True,
        composite_weights_sha256=(
            "854996e300bc0506a71679f12a179e1a0"
            "ae33b050b62eb4d77d7c8d222fcf0b2"
        ),
        provenance=(
            {"esconv_auxiliary_split": state.split.value} if auxiliary else {}
        ),
    )


def _fixture():
    split_groups = {
        PMV2Split.TRAIN: 2,
        PMV2Split.CALIBRATION: 1,
        PMV2Split.INTERNAL_TEST: 1,
    }
    longitudinal = []
    auxiliary = []
    for split, groups in split_groups.items():
        for index in range(groups):
            longitudinal.append(
                _state(
                    f"long_{split.value}_{index}",
                    user_id=f"long_user_{split.value}_{index}",
                    split=split,
                    auxiliary=False,
                )
            )
            auxiliary.append(
                _state(
                    f"aux_{split.value}_{index}",
                    user_id=f"aux_dialogue_{split.value}_{index}",
                    split=split,
                    auxiliary=True,
                )
            )
    long_labels = [
        _label(state, action, auxiliary=False)
        for state in longitudinal
        if state.split is not PMV2Split.INTERNAL_TEST
        for action in state.allowed_actions
    ]
    aux_labels = [
        _label(state, action, auxiliary=True)
        for state in auxiliary
        if state.split is not PMV2Split.INTERNAL_TEST
        for action in state.allowed_actions
    ]
    config = {
        "data_generation": {
            "train_users": 2,
            "calibration_users": 1,
            "internal_test_users": 1,
            "cases_per_user": 1,
        },
        "esconv_auxiliary_training": {
            "protocol": (
                "pm-v1.5-esconv-auxiliary-bank-disjoint-seed-training-support-v1"
            ),
            "split_dialogue_counts": {
                "train": 2,
                "calibration": 1,
                "internal_test": 1,
            },
            "expected_state_counts": {
                "train": 2,
                "calibration": 1,
                "internal_test": 1,
            },
            "expected_total_states": 4,
        },
    }
    return longitudinal, auxiliary, long_labels, aux_labels, config


def test_dual_domain_inputs_are_exact_balanced_and_do_not_open_internal_labels():
    longitudinal, auxiliary, long_labels, aux_labels, config = _fixture()
    result = validate_dual_domain_training_inputs(
        longitudinal_states=longitudinal,
        auxiliary_states=auxiliary,
        longitudinal_train_calibration_labels=long_labels,
        auxiliary_train_calibration_labels=aux_labels,
        pm_config=config,
    )
    assert result.report["status"] == "PASS"
    assert result.report["internal_labels_opened"] is False
    assert result.report["top_level_domain_weight"] == {
        LONGITUDINAL_DOMAIN: 0.5,
        ESCONV_AUXILIARY_DOMAIN: 0.5,
    }
    assert len(result.states_for_split(PMV2Split.TRAIN)) == 4
    assert len(result.labels_for_split(PMV2Split.INTERNAL_TEST)) == 0
    assert training_domain_for_state(auxiliary[0]) == ESCONV_AUXILIARY_DOMAIN
    assert training_domain_for_state(longitudinal[0]) == LONGITUDINAL_DOMAIN


def test_dual_domain_inputs_reject_missing_auxiliary_action_label():
    longitudinal, auxiliary, long_labels, aux_labels, config = _fixture()
    with pytest.raises(ValueError, match="exact legal matrix"):
        validate_dual_domain_training_inputs(
            longitudinal_states=longitudinal,
            auxiliary_states=auxiliary,
            longitudinal_train_calibration_labels=long_labels,
            auxiliary_train_calibration_labels=aux_labels[:-1],
            pm_config=config,
        )


def test_dual_domain_inputs_reject_dialogue_crossing_splits():
    longitudinal, auxiliary, long_labels, aux_labels, config = _fixture()
    auxiliary[0].user_id = auxiliary[-1].user_id
    with pytest.raises(ValueError, match="cross splits"):
        validate_dual_domain_training_inputs(
            longitudinal_states=longitudinal,
            auxiliary_states=auxiliary,
            longitudinal_train_calibration_labels=long_labels,
            auxiliary_train_calibration_labels=aux_labels,
            pm_config=config,
        )


def test_dual_domain_inputs_reject_memory_available_in_esconv_auxiliary():
    longitudinal, auxiliary, long_labels, aux_labels, config = _fixture()
    auxiliary[0].inventory[MemorySource.MP].available = True
    auxiliary[0].inventory[MemorySource.MP].count = 1
    auxiliary[0].inventory[MemorySource.MP].estimated_tokens = 10
    with pytest.raises(ValueError, match="exposes MP"):
        validate_dual_domain_training_inputs(
            longitudinal_states=longitudinal,
            auxiliary_states=auxiliary,
            longitudinal_train_calibration_labels=long_labels,
            auxiliary_train_calibration_labels=aux_labels,
            pm_config=config,
        )
