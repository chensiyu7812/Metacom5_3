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
    audit_domain_label_matrix,
    require_equal_domain_training_weight,
    training_domain_for_state,
    validate_dual_domain_training_inputs,
    validate_internal_domain_labels,
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
    fit_states, fit_labels = result.fit_and_calibration_views()
    internal_ids = {
        state.state_id
        for state in result.states_for_split(PMV2Split.INTERNAL_TEST)
    }
    assert set(fit_states) == {PMV2Split.TRAIN, PMV2Split.CALIBRATION}
    assert not {
        label.state_id for rows in fit_labels.values() for label in rows
    } & internal_ids
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


def test_dual_domain_inputs_reject_internal_outcomes_before_freeze():
    longitudinal, auxiliary, long_labels, aux_labels, config = _fixture()
    internal_state = next(
        state for state in auxiliary if state.split is PMV2Split.INTERNAL_TEST
    )
    aux_labels.append(
        _label(internal_state, "M0+R0", auxiliary=True)
    )
    with pytest.raises(ValueError, match="exact legal matrix"):
        validate_dual_domain_training_inputs(
            longitudinal_states=longitudinal,
            auxiliary_states=auxiliary,
            longitudinal_train_calibration_labels=long_labels,
            auxiliary_train_calibration_labels=aux_labels,
            pm_config=config,
        )


def test_dual_domain_inputs_reject_esconv_memory_action_space():
    longitudinal, auxiliary, long_labels, aux_labels, config = _fixture()
    auxiliary[0].allowed_actions = ["M0+R0", "ME+R0"]
    with pytest.raises(ValueError, match="non-canonical actions"):
        validate_dual_domain_training_inputs(
            longitudinal_states=longitudinal,
            auxiliary_states=auxiliary,
            longitudinal_train_calibration_labels=long_labels,
            auxiliary_train_calibration_labels=aux_labels,
            pm_config=config,
        )


def test_internal_domain_labels_reject_cross_domain_rows():
    longitudinal, auxiliary, _long_labels, _aux_labels, _config = _fixture()
    internal_aux = [
        state for state in auxiliary if state.split is PMV2Split.INTERNAL_TEST
    ]
    internal_long = next(
        state for state in longitudinal if state.split is PMV2Split.INTERNAL_TEST
    )
    labels = [
        _label(internal_aux[0], action, auxiliary=True)
        for action in internal_aux[0].allowed_actions
    ]
    labels.append(_label(internal_long, "M0+R0", auxiliary=False))
    with pytest.raises(ValueError, match="exact legal matrix"):
        validate_internal_domain_labels(
            states=internal_aux,
            labels=labels,
            domain=ESCONV_AUXILIARY_DOMAIN,
        )


def test_equal_domain_weight_guard_rejects_esconv_swamping():
    report = {
        "domain_dialogue_state_action_weighting": {
            "domain_weight": {
                LONGITUDINAL_DOMAIN: 0.5,
                ESCONV_AUXILIARY_DOMAIN: 0.5,
            }
        },
        "routing_objective": {
            "domain_dialogue_state_action_weighting": {
                "effective_weight_by_domain": {
                    LONGITUDINAL_DOMAIN: 0.25,
                    ESCONV_AUXILIARY_DOMAIN: 0.75,
                }
            }
        },
    }
    with pytest.raises(RuntimeError, match="swamp"):
        require_equal_domain_training_weight(report)


def test_equal_domain_weight_guard_accepts_both_model_stages():
    report = {
        "domain_dialogue_state_action_weighting": {
            "domain_weight": {
                LONGITUDINAL_DOMAIN: 0.5,
                ESCONV_AUXILIARY_DOMAIN: 0.5,
            }
        },
        "routing_objective": {
            "domain_dialogue_state_action_weighting": {
                "effective_weight_by_domain": {
                    LONGITUDINAL_DOMAIN: 0.5000000000000001,
                    ESCONV_AUXILIARY_DOMAIN: 0.4999999999999999,
                }
            }
        },
    }
    assert require_equal_domain_training_weight(report) == {
        LONGITUDINAL_DOMAIN: 0.5,
        ESCONV_AUXILIARY_DOMAIN: 0.5,
    }


def test_per_domain_label_audit_gates_reliability_without_dropping_rows():
    longitudinal, _auxiliary, long_labels, _aux_labels, _config = _fixture()
    train_states = [
        state for state in longitudinal if state.split is PMV2Split.TRAIN
    ]
    train_ids = {state.state_id for state in train_states}
    train_labels = [label for label in long_labels if label.state_id in train_ids]
    report = audit_domain_label_matrix(
        train_states,
        train_labels,
        domain=LONGITUDINAL_DOMAIN,
        low_mad_threshold=0.75,
        minimum_reliable_rate=0.8,
        minimum_low_mad_coverage_per_dimension=0.9,
        minimum_low_mad_coverage_per_action_dimension=0.8,
    )
    assert report["status"] == "PASS"
    assert report["label_count"] == len(train_labels)
    train_labels[0].label_reliable = False
    train_labels[1].label_reliable = False
    with pytest.raises(RuntimeError, match="label-quality gate failed"):
        audit_domain_label_matrix(
            train_states,
            train_labels,
            domain=LONGITUDINAL_DOMAIN,
            low_mad_threshold=0.75,
            minimum_reliable_rate=0.8,
            minimum_low_mad_coverage_per_dimension=0.9,
            minimum_low_mad_coverage_per_action_dimension=0.8,
        )
