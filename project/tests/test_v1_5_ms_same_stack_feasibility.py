from __future__ import annotations

from metacom_pm.v1_5_ms_same_stack_feasibility import (
    POLICIES,
    arm_order,
    paired_seed,
    select_fixed_states,
    validate_frozen_plan,
)


def test_selection_is_four_per_group_and_order_invariant():
    rows = [
        {"state_id": f"{group}-{index}", "split_group_key": group}
        for group in ("g1", "g2")
        for index in range(6)
    ]
    selected = select_fixed_states(rows)
    reverse = select_fixed_states(list(reversed(rows)))
    assert [row["state_id"] for row in selected] == [row["state_id"] for row in reverse]
    assert len(selected) == 8


def test_seed_and_order_are_deterministic():
    assert paired_seed("s1") == paired_seed("s1")
    assert arm_order("s1") == arm_order("s1")
    assert set(arm_order("s1")) == {"ON", "OFF"}


def test_plan_validator_accepts_expected_alias_shape():
    physical = []
    aliases = []
    for index in range(68):
        state_id = f"s{index}"
        seed = paired_seed(state_id)
        ids = {}
        for action in ("M0+R0", "MS+R0"):
            call_id = f"{state_id}:{action}"
            ids[action] = call_id
            physical.append({
                "physical_call_id": call_id,
                "state_id": state_id,
                "feasible_action_id": action,
                "seed": seed,
            })
        learned_action = "MS+R0" if index % 2 else "M0+R0"
        for policy, action in (
            ("always_off", "M0+R0"),
            ("fixed_high_MS", "MS+R0"),
            ("cross_fitted_learned_MS", learned_action),
        ):
            aliases.append({
                "logical_observation_id": f"{state_id}:{policy}",
                "physical_call_id": ids[action],
                "state_id": state_id,
                "policy": policy,
            })
    result = validate_frozen_plan(physical, aliases)
    assert result["status"] == "PASS"
    assert set(result["policy_alias_counts"]) == set(POLICIES)
