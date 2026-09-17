from pathlib import Path

import pytest

from metacom_pm.paper1.outcome_lock import (
    assert_calibration_outcome_locked,
    assert_confirmatory_outcome_locked,
    assert_pre_outcome_locked,
    load_public_only_config,
    require_formal_outcome_unlock,
)


ROOT = Path(__file__).resolve().parents[1]


def test_formal_outcomes_are_fail_closed_before_zero_outcome_freeze():
    config = load_public_only_config(ROOT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    assert_calibration_outcome_locked(config)
    assert_confirmatory_outcome_locked(config)
    with pytest.raises(RuntimeError, match="Formal Paper-1 outcome access is locked"):
        require_formal_outcome_unlock(config, freeze_manifest=None)


@pytest.mark.parametrize(
    "key",
    (
        "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
        "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
        "RQ1_CONFIRMATORY_OUTCOME_LOCK",
        "RQ2_CONFIRMATORY_OUTCOME_LOCK",
    ),
)
def test_four_scoped_outcome_locks_fail_closed_independently(key):
    config = load_public_only_config(ROOT / "configs/paper1_public_only.yaml")
    drifted = {**config, key: {"status": "OPEN"}}
    with pytest.raises(RuntimeError, match=key):
        assert_pre_outcome_locked(drifted)


def test_config_has_no_empirical_pass_gate_or_cost_label():
    config = load_public_only_config(ROOT / "configs/paper1_public_only.yaml")
    assert config["learning"]["empirical_pass_gates"] is False
    assert config["learning"]["cost_in_label_or_loss"] is False
    assert config["formal_evaluation"]["binary_paper_pass_fail"] is False
