from metacom_pm.v1_5_ms_rs_same_stack_baselines import (
    ACTIONS,
    action_for,
    choose_cost_matched_fixed,
    choose_on_rate_matched_random,
    transparent_ms_on,
)


def _costs(states):
    offsets = {"M0+R0": 0, "M0+RS": 10, "MS+R0": 20, "MS+RS": 30}
    return {(state, action): 100 + index + offsets[action] for index, state in enumerate(states) for action in ACTIONS}


def test_transparent_rule_only_blocks_explicit_nuisance_failures():
    assert transparent_ms_on(low_information_rank1=False, current_echo=False)
    assert not transparent_ms_on(low_information_rank1=True, current_echo=False)
    assert not transparent_ms_on(low_information_rank1=False, current_echo=True)


def test_action_for_preserves_two_factor_slice():
    assert action_for(ms_on=False, rs_on=False) == "M0+R0"
    assert action_for(ms_on=True, rs_on=False) == "MS+R0"
    assert action_for(ms_on=False, rs_on=True) == "M0+RS"
    assert action_for(ms_on=True, rs_on=True) == "MS+RS"


def test_cost_matched_fixed_uses_cost_only():
    states = [f"s{i}" for i in range(8)]
    learned = {state: ("MS+RS" if i < 4 else "M0+RS") for i, state in enumerate(states)}
    result = choose_cost_matched_fixed(
        state_ids=states,
        learned_actions=learned,
        estimated_input_tokens=_costs(states),
    )
    assert result["action"] in ACTIONS
    assert result["target_total_estimated_input_tokens"] > 0


def test_matched_random_preserves_on_rate_and_changes_assignment():
    states = [f"s{i}" for i in range(16)]
    learned = {state: i < 7 for i, state in enumerate(states)}
    result = choose_on_rate_matched_random(
        state_ids=states,
        learned_ms_on=learned,
        estimated_input_tokens=_costs(states),
        seed="paper1-v3-test",
    )
    assert result["learned_ms_on_count"] == 7
    assert result["random_ms_on_count"] == 7
    assert result["changed_fraction"] >= 0.25
    assert set(result["actions"].values()) <= {"M0+RS", "MS+RS"}

