import json
from pathlib import Path

import numpy as np
import pytest

from metacom_pm.v1_5_v5_3_public_learnability_analysis import (
    COMPONENTS,
    formal_oof_head_analysis,
    formal_effect_freeze,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_freeze_20260809"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_public_formal_effect_freeze_v1.json"


def _analysis_fixture():
    return {
        component: {
            "frozen_representation": f"FROZEN_{component}",
            "model_dimensions": index + 4,
            "development_engineering_signal": True,
        }
        for index, component in enumerate(COMPONENTS)
    }


def test_formal_freeze_requires_all_four_heads():
    fixture = _analysis_fixture()
    fixture.pop("RS")
    with pytest.raises(ValueError, match="all four pilot heads"):
        formal_effect_freeze(fixture)


def test_formal_freeze_is_small_and_fail_closed():
    freeze = formal_effect_freeze(_analysis_fixture())
    assert freeze["formal_groups"] == {component: 144 for component in COMPONENTS}
    assert freeze["formal_total_groups"] == 576
    assert freeze["paired_generator_seeds_per_group"] == 3
    assert "outcome-selected" in freeze["failure_rule"]
    assert "fails closed" in freeze["failure_rule"]
    assert "cannot mathematically guarantee" in freeze["guarantee_boundary"]
    assert "cost" not in freeze["target"].lower()
    assert "excluded from labels" in freeze["risk"]


def test_tracked_development_analysis_passes_only_the_prefrozen_engineering_gate():
    report = json.loads((OUT / "learnability_report.json").read_text())
    freeze = json.loads((OUT / "formal_effect_freeze.json").read_text())
    contract = json.loads(CONTRACT.read_text())
    assert report["status"] == "ALL_FOUR_DEVELOPMENT_SIGNALS_PASS_FORMAL_EXPANSION_GATE"
    assert freeze == contract
    assert freeze["formal_total_groups"] == 576
    for component in COMPONENTS:
        result = report["analysis"][component]
        assert result["development_engineering_signal"] is True
        assert result["relative_mse"] <= 0.95
        assert result["oof_spearman"] >= 0.15
        assert 4 <= result["model_dimensions"] <= 7
        assert freeze["heads"][component]["no_further_representation_selection"] is True


def _formal_mp_fixture(groups: int = 144):
    rng = np.random.default_rng(42)
    state = rng.normal(size=(groups, 12))
    candidate = rng.normal(size=(groups, 12))
    rows = []
    manifests = {}
    for index in range(groups):
        effect_id = f"effect-{index}"
        fold = index // 24 + 1
        user_id = f"user-{index // 8}"
        target = float(0.7 * state[index, 0] - 0.2 * state[index, 1])
        rows.append({
            "component": "MP",
            "effect_group_id": effect_id,
            "outer_fold": fold,
            "quality_effect": {
                "aggregate": {"mean_positive_support_contribution": target},
                "replicates": [],
            },
            "functional": {"replicates": []},
        })
        manifests[effect_id] = {
            "effect_group_id": effect_id,
            "component": "MP",
            "outer_fold": fold,
            "user_id": user_id,
            "model_features": {
                "rank1_relative_age": float(index % 8) / 7,
                "current_redundant": bool(index % 2),
                "candidate_state_bge_m3_cosine": 0.5,
            },
        }
    return rows, manifests, state, candidate


def test_formal_oof_refuses_partial_panel_before_revealing_results():
    rows, manifests, state, candidate = _formal_mp_fixture(143)
    with pytest.raises(ValueError, match="exactly 144"):
        formal_oof_head_analysis(
            component="MP",
            result_rows=rows,
            manifest_by_group=manifests,
            state_vectors=state,
            candidate_vectors=candidate,
        )


def test_formal_oof_uses_the_frozen_six_folds_and_emits_predictions():
    rows, manifests, state, candidate = _formal_mp_fixture()
    result = formal_oof_head_analysis(
        component="MP",
        result_rows=rows,
        manifest_by_group=manifests,
        state_vectors=state,
        candidate_vectors=candidate,
    )
    assert result["groups"] == 144
    assert result["fold_counts"] == {fold: 24 for fold in range(1, 7)}
    assert len(result["predictions"]) == 144
    assert result["formal_head_pass"] is True
    assert result["binary_balanced_accuracy_not_primary"] is True
