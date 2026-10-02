import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import TreatmentAssignment
from metacom_pm.paper1.rs.matched_random import RandomizationUnit, build_matched_random_schedule


def _units():
    return [
        RandomizationUnit(
            unit_id=f"u-{index}",
            eligible=True,
            stratum="primary::short" if index < 5 else "primary::long",
            injected_tokens_if_on=10 + index,
            learned_assignment=(
                TreatmentAssignment.ON if index in {0, 1, 5} else TreatmentAssignment.OFF
            ),
        )
        for index in range(10)
    ]


def test_matched_random_is_deterministic_and_matches_on_count_per_stratum():
    left = build_matched_random_schedule(_units(), seed=19, proposals=128)
    right = build_matched_random_schedule(_units(), seed=19, proposals=128)
    assert left == right
    assert left.learned_on_count_by_stratum == left.random_on_count_by_stratum
    assert sum(row.assignment is TreatmentAssignment.ON for row in left.assignments) == 3
    assert left.absolute_token_budget_difference == abs(
        left.random_injected_token_budget - left.learned_injected_token_budget
    )
    assert left.exact_token_budget_matched is True


def test_ineligible_units_are_always_random_off():
    units = _units()
    units[4] = RandomizationUnit(
        unit_id="u-4",
        eligible=False,
        stratum="primary::short",
        injected_tokens_if_on=14,
        learned_assignment=TreatmentAssignment.OFF,
    )
    schedule = build_matched_random_schedule(units, seed=2, proposals=32)
    assignment = {row.unit_id: row.assignment for row in schedule.assignments}
    assert assignment["u-4"] is TreatmentAssignment.OFF


def test_ineligible_learned_on_is_rejected():
    with pytest.raises(ValidationError):
        RandomizationUnit(
            unit_id="bad",
            eligible=False,
            stratum="primary",
            injected_tokens_if_on=10,
            learned_assignment=TreatmentAssignment.ON,
        )


def test_formal_default_rejects_a_control_that_only_matches_on_rate():
    units = [
        RandomizationUnit(
            unit_id="learned",
            eligible=True,
            stratum="primary",
            injected_tokens_if_on=10,
            learned_assignment=TreatmentAssignment.ON,
        ),
        RandomizationUnit(
            unit_id="alternative",
            eligible=True,
            stratum="primary",
            injected_tokens_if_on=99,
            learned_assignment=TreatmentAssignment.OFF,
        ),
    ]
    with pytest.raises(ValueError, match="exactly token-matched"):
        build_matched_random_schedule(units, seed=3, proposals=1)
