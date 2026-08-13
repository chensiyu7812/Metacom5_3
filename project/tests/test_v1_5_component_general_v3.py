from __future__ import annotations

import pytest

from metacom_pm.v1_5_component_general_v3 import (
    PAIR_KEYS,
    V3Candidate,
    all_sixteen_action_ids,
    build_component_general_plan_v3,
)
from metacom_pm.v1_5b_policy_runtime import COMPONENTS, action_component_bits, compile_component_bits


def _candidate(component: str, *, eligible: bool = True) -> V3Candidate:
    return V3Candidate(
        component=component,
        evidence_id=f"evidence-{component.lower()}",
        meaning_cue=f"bounded meaning for {component}",
        exact_source=f"auditable source for {component}",
        owner_id=None if component == "RS" else "owner-1",
        time_status="CURRENT_CARD" if component == "RS" else "STRICTLY_PAST",
        allowed_response_change=f"change allowed for {component}",
        forbidden_inference="no unsupported current fact",
        structurally_eligible=eligible,
        structural_failure=None if eligible else "OWNER_INVALID",
    )


def _all_candidates():
    return {component: _candidate(component) for component in COMPONENTS}


def test_all_sixteen_requested_actions_remain_planned_when_structurally_eligible():
    actions = all_sixteen_action_ids()
    assert len(actions) == 16
    assert len(set(actions)) == 16
    for action in actions:
        plan = build_component_general_plan_v3(
            requested_action_id=action,
            current_user_id="owner-1",
            candidates=_all_candidates(),
        )
        assert plan.requested_action_id == action
        assert plan.structurally_eligible_action_id == action
        assert plan.jointly_planned_action_id == action
        assert plan.accounting.requested == action_component_bits(action)
        assert plan.accounting.jointly_planned == action_component_bits(action)


def test_full_action_keeps_mp_ms_me_rs_and_covers_all_six_pairs():
    action = compile_component_bits({component: True for component in COMPONENTS})
    plan = build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="owner-1",
        candidates=_all_candidates(),
        pair_relations={pair: "CONFLICT" for pair in PAIR_KEYS},
    )
    assert plan.jointly_planned_action_id == action
    assert {resource.component for resource in plan.resources} == set(COMPONENTS)
    assert {pair.pair for pair in plan.pair_plans} == set(PAIR_KEYS)
    assert all(pair.relation == "CONFLICT" for pair in plan.pair_plans)
    assert all(pair.suppresses_component is False for pair in plan.pair_plans)


def test_only_structural_invalidity_projects_a_requested_bit_off():
    action = compile_component_bits({component: True for component in COMPONENTS})
    candidates = _all_candidates()
    candidates["MS"] = _candidate("MS", eligible=False)
    plan = build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="owner-1",
        candidates=candidates,
        pair_relations={"MP-ME": "REDUNDANT", "ME-RS": "UNKNOWN"},
    )
    assert plan.accounting.requested["MS"] is True
    assert plan.accounting.structurally_eligible["MS"] is False
    assert plan.accounting.jointly_planned["MS"] is False
    assert plan.projection_reasons["MS"] == "OWNER_INVALID"
    assert plan.accounting.jointly_planned["MP"] is True
    assert plan.accounting.jointly_planned["ME"] is True
    assert plan.accounting.jointly_planned["RS"] is True


def test_claimed_and_verified_layers_never_overwrite_the_plan():
    action = compile_component_bits({component: True for component in COMPONENTS})
    plan = build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="owner-1",
        candidates=_all_candidates(),
    )
    claimed = plan.accounting.with_generator_claimed({"MS": True, "RS": True})
    verified = claimed.with_offline_verified_functional({"ME": True, "RS": True})
    assert verified.requested == plan.accounting.requested
    assert verified.structurally_eligible == plan.accounting.structurally_eligible
    assert verified.jointly_planned == plan.accounting.jointly_planned
    assert verified.generator_claimed["MS"] is True
    assert verified.generator_claimed["ME"] is False
    assert verified.offline_verified_functional["MS"] is False
    assert verified.offline_verified_functional["ME"] is True


def test_unplanned_component_cannot_be_added_by_telemetry_or_review():
    action = compile_component_bits({component: False for component in COMPONENTS})
    plan = build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="owner-1",
        candidates=_all_candidates(),
    )
    with pytest.raises(ValueError):
        plan.accounting.with_generator_claimed({"MS": True})
    with pytest.raises(ValueError):
        plan.accounting.with_offline_verified_functional({"ME": True})


def test_resources_never_require_literal_mention_or_lexical_overlap():
    action = compile_component_bits({component: True for component in COMPONENTS})
    plan = build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="owner-1",
        candidates=_all_candidates(),
    )
    assert all(resource.literal_mention_required is False for resource in plan.resources)
    assert all(resource.lexical_overlap_required is False for resource in plan.resources)


def test_legacy_preference_surface_is_not_part_of_v3_candidate_schema():
    with pytest.raises(TypeError):
        V3Candidate(
            component="MP",
            evidence_id="mp-1",
            meaning_cue="profile-based constraint",
            exact_source="source",
            owner_id="owner-1",
            time_status="CURRENT",
            allowed_response_change="burden",
            forbidden_inference="stereotype",
            candidate_is_preference=True,  # type: ignore[call-arg]
        )


def test_owner_mismatch_is_a_structural_projection_not_a_semantic_negative():
    action = compile_component_bits({component: True for component in COMPONENTS})
    plan = build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="different-owner",
        candidates=_all_candidates(),
    )
    assert plan.accounting.requested["MP"] is True
    assert plan.accounting.structurally_eligible["MP"] is False
    assert plan.accounting.structurally_eligible["MS"] is False
    assert plan.accounting.structurally_eligible["ME"] is False
    assert plan.accounting.structurally_eligible["RS"] is True
    assert plan.projection_reasons["MS"] == "OWNER_INVALID"
