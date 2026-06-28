from pathlib import Path

import pytest

from metacom_pm.artifacts import create_artifact_attestation
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


def test_train_pm_requires_m2b_attestation_before_loading_runtime(tmp_path):
    files = {}
    for name in (
        "response_pairs",
        "memory_omission",
        "memory_use",
        "strategy_use",
        "strategy_omission",
        "memory_selected_set_omission",
    ):
        path = tmp_path / f"{name}.jsonl"
        path.write_text('{"id":"placeholder"}\n', encoding="utf-8")
        files[name] = path
    full_attestation = tmp_path / "full_attestation.json"
    create_artifact_attestation(
        full_attestation,
        stage="full_judging",
        inputs={"source": files["response_pairs"]},
        outputs={
            "response_pairs": (files["response_pairs"], True),
            "memory_omission": (files["memory_omission"], True),
            "memory_use": (files["memory_use"], True),
            "strategy_use": (files["strategy_use"], True),
            "strategy_omission": (files["strategy_omission"], True),
        },
        parameters={},
    )

    with pytest.raises(RuntimeError, match="missing attestation"):
        train_pm(
            tmp_path / "missing_runtime.jsonl",
            files["response_pairs"],
            files["memory_omission"],
            files["memory_use"],
            files["strategy_use"],
            files["strategy_omission"],
            {"card_1"},
            {"card_2"},
            tmp_path / "model.joblib",
            tmp_path / "report.json",
            m2b_path=files["memory_selected_set_omission"],
            judging_attestation_path=full_attestation,
        )
