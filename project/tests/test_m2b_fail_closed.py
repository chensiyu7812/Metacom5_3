from pathlib import Path

import pytest

from metacom_pm.selection import tune_validation_policies
from metacom_pm.training import train_pm


def test_train_pm_requires_m2b_before_loading_labels(tmp_path):
    missing = tmp_path / "missing.jsonl"
    with pytest.raises(RuntimeError, match="M2b selected-set omission labels are required"):
        train_pm(
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            {"card_1"},
            {"card_2"},
            tmp_path / "model.joblib",
            tmp_path / "report.json",
        )


def test_validation_selection_requires_m2b_before_loading_labels(tmp_path):
    missing = tmp_path / "missing.jsonl"
    with pytest.raises(RuntimeError, match="M2b selected-set omission labels are required"):
        tune_validation_policies(
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            missing,
            tmp_path / "model.joblib",
            {"card_1"},
            tmp_path / "selection.json",
        )
